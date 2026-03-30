"""
scraper_product.py
==================
Takes a listing JSON (output of scraper_listing.py) and scrapes
full product details for each URL.

RESUME LOGIC: Already-scraped ASINs are skipped automatically.
New results are appended to the output file after every item —
so if the script crashes, you lose nothing and can just re-run.

Outputs: ../data/amazon_products_<query>.json

Usage:
    # Scrape all products from a listing file
    python scraper_product.py --input ../data/amazon_listing_laptops.json

    # Scrape with a limit (e.g. first 50)
    python scraper_product.py --input ../data/amazon_listing_laptops.json --limit 50

    # Scrape a single URL directly
    python scraper_product.py --url "https://www.amazon.in/dp/B0CRKXDX83"

    # Re-run anytime — already scraped items are skipped instantly
    python scraper_product.py --input ../data/amazon_listing_laptops.json --limit 50
"""

import asyncio
import argparse
import json
import re
from pathlib import Path
from crawl4ai import AsyncWebCrawler, JsonCssExtractionStrategy
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig


# ── Schema ────────────────────────────────────────────────────────────────────

PRODUCT_SCHEMA = {
    "name": "Amazon Product Detail",
    "baseSelector": "body",
    "fields": [

        # Identity
        {"name": "title",
         "selector": "#productTitle",
         "type": "text"},

        {"name": "brand",
         "selector": "#bylineInfo",
         "type": "text"},

        {"name": "asin",
         "selector": "#ASIN",
         "type": "attribute", "attribute": "value"},

        {"name": "category",
         "selector": "#wayfinding-breadcrumbs_feature_div ul li a",
         "type": "text"},

        # Pricing — multiple fallback selectors for different page layouts
        {"name": "price",
         "selector": (
             "span.priceToPay span.a-offscreen,"
             "#apex_desktop span.a-price span.a-offscreen,"
             "#corePrice_feature_div span.a-price span.a-offscreen,"
             ".a-price.apexPriceToPay span.a-offscreen"
         ),
         "type": "text"},

        {"name": "original_price",
         "selector": (
             "span.a-price.a-text-price span.a-offscreen,"
             ".basisPrice span.a-offscreen"
         ),
         "type": "text"},

        {"name": "discount_percent",
         "selector": "span.savingsPercentage",
         "type": "text"},

        # Ratings
        {"name": "rating",
         "selector": "#acrPopover .a-icon-alt",
         "type": "text"},

        {"name": "review_count",
         "selector": "#acrCustomerReviewText",
         "type": "text"},

        {"name": "questions_count",
         "selector": "#askATFLink span",
         "type": "text"},

        # Rating histogram — each li contains all star labels + percentages
        # We grab the full li text and parse it in post-processing
        {"name": "rating_histogram_raw",
         "selector": "#histogramTable li",
         "type": "text"},

        # Availability & seller
        {"name": "availability",
         "selector": "#availability span",
         "type": "text"},

        {"name": "sold_by",
         "selector": "#sellerProfileTriggerId",
         "type": "text"},

        {"name": "fulfilled_by",
         "selector": "#merchant-info",
         "type": "text"},

        # Prime: grab the aria-label from the badge img
        {"name": "prime_badge",
         "selector": "#isPrimeBadge img, .a-icon-prime",
         "type": "attribute", "attribute": "aria-label"},

        # Delivery
        {"name": "delivery_primary",
         "selector": (
             "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE,"
             "#ddmDeliveryMessage"
         ),
         "type": "text"},

        {"name": "delivery_secondary",
         "selector": "#mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE",
         "type": "text"},

        # Images
        # data-old-hires = full resolution URL
        {"name": "main_image_hires",
         "selector": "#landingImage",
         "type": "attribute", "attribute": "data-old-hires"},

        {"name": "main_image_src",
         "selector": "#landingImage",
         "type": "attribute", "attribute": "src"},

        # data-a-dynamic-image is a JSON map {url: [w,h]} for all gallery images
        {"name": "gallery_json",
         "selector": "#landingImage",
         "type": "attribute", "attribute": "data-a-dynamic-image"},

        # Variants
        {"name": "variant_options",
         "selector": (
             "#variation_color_name .a-button-text,"
             "#variation_ram_size .a-button-text,"
             "#variation_hard_disk_size .a-button-text,"
             "#variation_configuration .a-button-text"
         ),
         "type": "text"},

        # Features
        {"name": "feature_bullets",
         "selector": "#feature-bullets ul li span.a-list-item",
         "type": "text"},

        # Tech specs — Amazon uses different table IDs on different product types
        {"name": "tech_specs_1",
         "selector": "#productDetails_techSpec_section_1 tr",
         "type": "text"},

        {"name": "tech_specs_2",
         "selector": "#productDetails_techSpec_section_2 tr",
         "type": "text"},

        {"name": "tech_specs_db",
         "selector": "#productDetails_db_sections tr",
         "type": "text"},

        # Detail bullets (used when specs table is not present)
        {"name": "detail_bullets",
         "selector": "#detailBulletsWrapper_feature_div li span.a-list-item",
         "type": "text"},

        {"name": "description",
         "selector": "#productDescription",
         "type": "text"},

        # Metadata
        {"name": "bestseller_rank",
         "selector": (
             "#detailBulletsWrapper_feature_div li:-soup-contains('Best Sellers Rank'),"
             "#SalesRank"
         ),
         "type": "text"},

        {"name": "date_first_available",
         "selector": (
             "#detailBulletsWrapper_feature_div "
             "li:-soup-contains('Date First Available') span.a-list-item"
         ),
         "type": "text"},

        # Top reviews
        {"name": "review_titles",
         "selector": "[data-hook='review-title'] span:not([class*='icon'])",
         "type": "text"},

        {"name": "review_ratings",
         "selector": "[data-hook='review-star-rating'] .a-icon-alt",
         "type": "text"},

        {"name": "review_dates",
         "selector": "[data-hook='review-date']",
         "type": "text"},

        {"name": "review_bodies",
         "selector": "[data-hook='review-body'] span",
         "type": "text"},

        {"name": "review_verified",
         "selector": "[data-hook='avp-badge']",
         "type": "text"},
    ]
}

# Scroll page in steps to trigger lazy loading of specs, images, reviews
SCROLL_JS = """
(async () => {
    const delay = ms => new Promise(r => setTimeout(r, ms));
    // Scroll down in steps
    for (const pct of [0.15, 0.3, 0.5, 0.7, 0.85, 1.0]) {
        window.scrollTo(0, document.body.scrollHeight * pct);
        await delay(400);
    }
    // Pause mid-page (specs table zone)
    window.scrollTo(0, document.body.scrollHeight * 0.45);
    await delay(700);
    // Final scroll to bottom for reviews
    window.scrollTo(0, document.body.scrollHeight);
    await delay(500);
})();
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def s(d: dict, key: str) -> str:
    return (d.get(key) or "").strip()


def parse_price(raw: str) -> str:
    """Extract first ₹ value and remove commas."""
    prices = re.findall(r'₹[\d,]+', raw or "")
    return prices[0].replace(",", "") if prices else ""


def parse_rating(raw: str) -> str:
    m = re.search(r'[\d.]+', raw or "")
    return m.group() if m else ""


def parse_delivery(raw: str) -> str:
    """Extract just the date from noisy delivery strings."""
    if not raw:
        return ""
    m = re.search(
        r'(Today|Tomorrow|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+\d+\s+\w+)',
        raw
    )
    return m.group(0).strip() if m else raw.strip()[:80]


def parse_gallery(raw_json: str, thumb_src: str = "") -> list[str]:
    """
    Parse data-a-dynamic-image JSON → list of unique full-res image URLs.
    Falls back to upscaling the thumbnail src.
    """
    images: set[str] = set()

    if raw_json:
        try:
            img_map = json.loads(raw_json)
            for url in img_map:
                # Upscale to highest available resolution
                clean = re.sub(r'\._[A-Z]{2}\d+_', '._SL1500_', url)
                images.add(clean)
        except Exception:
            pass

    if not images and thumb_src:
        clean = re.sub(r'\._[A-Z_0-9]+_\.', '._SL500_.', thumb_src)
        images.add(clean)

    return sorted(images)


def parse_histogram(raw: str) -> dict:
    """
    Amazon histogram text looks like:
    '5 star4 star3 star2 star1 star5 star56%22%6%2%14%56%'
    Extract the percentages in order: 5★ 4★ 3★ 2★ 1★
    """
    percentages = re.findall(r'(\d+)%', raw or "")
    # Amazon repeats the full set per row — take the last 5 unique values
    if len(percentages) >= 5:
        # The last 5 are the actual per-star %
        pcts = percentages[-5:]
        return {
            "5star": pcts[0] + "%",
            "4star": pcts[1] + "%",
            "3star": pcts[2] + "%",
            "2star": pcts[3] + "%",
            "1star": pcts[4] + "%",
        }
    return {"5star": "", "4star": "", "3star": "", "2star": "", "1star": ""}


def parse_tech_specs(raw: str) -> dict:
    """
    Convert raw table row text like:
    'Processor\nIntel Core i5\nRAM\n16 GB'
    into a clean dict.
    """
    if not raw:
        return {}
    specs = {}
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    # Rows come as pairs: key, value, key, value ...
    i = 0
    while i < len(lines) - 1:
        key   = lines[i]
        value = lines[i + 1]
        # Skip if both look like headers or both look like values
        if key and value and len(key) < 60:
            specs[key] = value
        i += 2
    return specs


def parse_reviews(raw: dict) -> list[dict]:
    def split(key):
        return [x.strip() for x in (raw.get(key) or "").split("\n") if x.strip()]

    titles   = split("review_titles")
    ratings  = split("review_ratings")
    dates    = split("review_dates")
    bodies   = split("review_bodies")
    verified = split("review_verified")

    count = max(len(titles), len(bodies))
    if count == 0:
        return []

    reviews = []
    for i in range(count):
        reviews.append({
            "title":    titles[i]   if i < len(titles)   else "",
            "rating":   parse_rating(ratings[i] if i < len(ratings) else ""),
            "date":     dates[i]    if i < len(dates)    else "",
            "body":     bodies[i]   if i < len(bodies)   else "",
            "verified": bool(verified[i]) if i < len(verified) else False,
        })
    return reviews


def clean_product(raw: dict, source_url: str = "") -> dict:
    p = {}

    # Identity
    p["url"]      = source_url
    p["asin"]     = s(raw, "asin")
    p["title"]    = s(raw, "title")
    p["brand"]    = re.sub(r'Visit the|Store|Brand:', '', s(raw, "brand")).strip()
    p["category"] = s(raw, "category")

    # Pricing
    price_raw = s(raw, "price")
    p["price"]          = parse_price(price_raw) or "N/A"
    p["original_price"] = parse_price(s(raw, "original_price")) or "N/A"
    p["discount"]       = s(raw, "discount_percent")

    # Ratings
    p["rating"]         = parse_rating(s(raw, "rating"))
    p["review_count"]   = re.sub(r'[^\d]', '', s(raw, "review_count")) or "0"
    p["questions"]      = re.sub(r'[^\d]', '', s(raw, "questions_count")) or "0"

    # Histogram — only need first li which has all data
    hist_raw = s(raw, "rating_histogram_raw")
    p["rating_breakdown"] = parse_histogram(hist_raw)

    # Purchase info
    p["availability"]  = s(raw, "availability")
    p["sold_by"]       = s(raw, "sold_by")
    p["fulfilled_by"]  = s(raw, "fulfilled_by")
    p["prime"]         = "Prime" in (s(raw, "prime_badge") or "")
    p["delivery"]      = parse_delivery(s(raw, "delivery_primary"))
    p["delivery_alt"]  = parse_delivery(s(raw, "delivery_secondary"))

    # Images
    main = s(raw, "main_image_hires") or s(raw, "main_image_src")
    p["main_image"]    = re.sub(r'\._[A-Z]{2}\d+_', '._SL1500_', main) if main else ""
    p["gallery"]       = parse_gallery(s(raw, "gallery_json"), s(raw, "main_image_src"))

    # Variants
    p["variants"]      = s(raw, "variant_options")

    # Features & specs
    p["features"]      = s(raw, "feature_bullets")

    specs_raw = (
        s(raw, "tech_specs_1")
        or s(raw, "tech_specs_2")
        or s(raw, "tech_specs_db")
        or s(raw, "detail_bullets")
    )
    p["tech_specs"]    = parse_tech_specs(specs_raw)

    p["description"]   = s(raw, "description")

    # Metadata
    p["bestseller_rank"]      = s(raw, "bestseller_rank")
    p["date_first_available"] = s(raw, "date_first_available")

    # Reviews
    p["reviews"] = parse_reviews(raw)

    return p


# ── Scraper ───────────────────────────────────────────────────────────────────

async def scrape_one(url: str, crawler) -> dict:
    config = CrawlerRunConfig(
        extraction_strategy=JsonCssExtractionStrategy(PRODUCT_SCHEMA),
        wait_for="#productTitle",
        delay_before_return_html=4.0,
        js_code=SCROLL_JS,
    )
    result = await crawler.arun(url=url, config=config)

    if result.success and result.extracted_content:
        raw_list = json.loads(result.extracted_content)
        raw      = raw_list[0] if raw_list else {}
        return clean_product(raw, source_url=url)

    return {
        "url":   url,
        "error": result.error_message or "Unknown error",
        "asin":  re.search(r'/dp/([A-Z0-9]{10})', url).group(1)
                 if re.search(r'/dp/([A-Z0-9]{10})', url) else "",
    }


# ── Resume helpers ────────────────────────────────────────────────────────────

def load_existing(out_file: Path) -> tuple[list[dict], set[str]]:
    """
    Load already-scraped products from the output file.
    Returns (products_list, set_of_done_asins).
    """
    if not out_file.exists():
        return [], set()
    try:
        data = json.loads(out_file.read_text(encoding="utf-8"))
        done = {p["asin"] for p in data if p.get("asin")}
        print(f"📂 Resuming — {len(done)} ASINs already in {out_file.name}")
        return data, done
    except Exception as e:
        print(f"⚠️  Could not read existing file ({e}), starting fresh.")
        return [], set()


def append_to_file(out_file: Path, all_products: list[dict]) -> None:
    """Overwrite output file with the full list (called after every item)."""
    out_file.write_text(
        json.dumps(all_products, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# ── Scraper ───────────────────────────────────────────────────────────────────

async def scrape_products(
    urls: list[str],
    out_file: Path,
    headless: bool = True,
    delay: float = 2.5,
) -> list[dict]:

    # ── Resume: load what's already done ─────────────────────────────────
    all_products, done_asins = load_existing(out_file)

    # Filter out URLs whose ASIN is already scraped
    pending = []
    skipped = 0
    for url in urls:
        m = re.search(r'/dp/([A-Z0-9]{10})', url)
        asin = m.group(1) if m else ""
        if asin and asin in done_asins:
            skipped += 1
        else:
            pending.append(url)

    if skipped:
        print(f"⏭️  Skipping {skipped} already-scraped products")
    print(f"🔄 {len(pending)} products left to scrape\n")

    if not pending:
        print("✅ Nothing new to scrape — all done!")
        return all_products

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=headless,
        headers={"Accept-Language": "en-IN,en;q=0.9"},
    )

    total = len(pending)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, url in enumerate(pending, 1):
            print(f"  [{i}/{total}] {url}")
            product = await scrape_one(url, crawler)

            if "error" in product:
                print(f"    ❌ {product['error']}")
            else:
                print(
                    f"    ✅ {product.get('title', '')[:55]}  |  "
                    f"{product.get('price')}  |  "
                    f"⭐{product.get('rating')} ({product.get('review_count')} reviews)  |  "
                    f"{len(product.get('reviews', []))} reviews scraped"
                )

            # Only add if not already present (safety check)
            asin = product.get("asin", "")
            if not asin or asin not in done_asins:
                all_products.append(product)
                if asin:
                    done_asins.add(asin)

            # ── Write after every item — crash-safe ──────────────────────
            append_to_file(out_file, all_products)

            # Staggered delay — vary to avoid bot detection
            jitter = delay + (i % 3) * 0.4   # cycles: 2.5 / 2.9 / 3.3s
            await asyncio.sleep(jitter)

    return all_products


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Amazon product detail scraper (with resume)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input",  help="Path to listing JSON from scraper_listing.py")
    group.add_argument("--url",    help="Single product URL to scrape")
    parser.add_argument("--limit",    default=50,   type=int,   help="Max products to scrape (default 50)")
    parser.add_argument("--delay",    default=2.5,  type=float, help="Base delay between requests (default 2.5s)")
    parser.add_argument("--output",   default="",               help="Override output filename")
    parser.add_argument("--headless", default=True, action=argparse.BooleanOptionalAction)
    args = parser.parse_args()

    # ── Build URL list ────────────────────────────────────────────────────
    if args.url:
        urls     = [args.url]
        out_stem = "../data/amazon_product_single"
    else:
        listing_path = Path(args.input)
        if not listing_path.exists():
            print(f"❌ File not found: {args.input}")
            return
        listing = json.loads(listing_path.read_text(encoding="utf-8"))

        # Deduplicate by ASIN within the listing itself
        seen_in_listing: set[str] = set()
        urls: list[str] = []
        for item in listing:
            url  = item.get("url", "")
            asin = item.get("asin", "")
            if "/dp/" in url and asin not in seen_in_listing:
                seen_in_listing.add(asin)
                urls.append(url)

        urls     = urls[:args.limit]
        out_stem = "../data/amazon_products_" + re.sub(r'[^\w]', '_', listing_path.stem)

    # Allow output override
    out_file = Path(args.output) if args.output else Path(f"{out_stem}.json")

    print(f"\n🛒 Amazon product scraper  (resume-enabled)")
    print(f"   output   : {out_file}")
    print(f"   total    : {len(urls)} URLs from listing")
    print(f"   headless : {args.headless}  |  delay: {args.delay}s")
    print("=" * 60)

    products = await scrape_products(
        urls,
        out_file=out_file,
        headless=args.headless,
        delay=args.delay,
    )

    success = [p for p in products if "error" not in p]
    failed  = [p for p in products if "error" in p]

    print(f"\n{'='*60}")
    print(f"✅ Total in file : {len(products)}")
    print(f"   Success       : {len(success)}")
    print(f"   Failed        : {len(failed)}")
    print(f"📁 Output        : {out_file}")

    if failed:
        print(f"\n── Failed URLs ──")
        for p in failed:
            print(f"  {p.get('url')}  →  {p.get('error', '')}")


if __name__ == "__main__":
    asyncio.run(main())
