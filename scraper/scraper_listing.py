"""
scraper_listing.py
==================
Scrapes Amazon India search result pages for any query.
Outputs: amazon_listing_<query>.json

Usage:
    python scraper_listing.py
    python scraper_listing.py --query "gaming laptops" --pages 5
"""

import asyncio
import argparse
import json
import re
from pathlib import Path
from crawl4ai import AsyncWebCrawler, JsonCssExtractionStrategy
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig


# ── Schema ───────────────────────────────────────────────────────────────────

LISTING_SCHEMA = {
    "name": "Amazon Search Results",
    "baseSelector": "[data-component-type='s-search-result']",
    "fields": [
        {"name": "title",
         "selector": "a h2 span",
         "type": "text"},

        {"name": "url",
         "selector": "a.a-link-normal.s-underline-text, a.a-link-normal",
         "type": "attribute", "attribute": "href"},

        {"name": "asin",
         "selector": "div[data-asin]",
         "type": "attribute", "attribute": "data-asin"},

        {"name": "image",
         "selector": ".s-image",
         "type": "attribute", "attribute": "src"},

        {"name": "rating",
         "selector": ".a-icon-star-small .a-icon-alt, .a-icon-alt",
         "type": "text"},

        {"name": "review_count",
         "selector": ".a-size-base.s-underline-text",
         "type": "text"},

        {"name": "price",
         "selector": ".a-price .a-offscreen",
         "type": "text"},

        {"name": "original_price",
         "selector": ".a-price.a-text-price .a-offscreen",
         "type": "text"},

        {"name": "discount",
         "selector": ".a-letter-space + span, .s-color-discount-price",
         "type": "text"},

        {"name": "sponsored",
         "selector": ".puis-sponsored-label-text",
         "type": "text"},

        {"name": "delivery",
         "selector": "[data-cy='delivery-recipe'] span, .a-color-base.a-text-bold",
         "type": "text"},

        {"name": "badge",
         "selector": ".a-badge-text, .s-badge-text",
         "type": "text"},
    ]
}

SCROLL_JS = """
(async () => {
    for (const pct of [0.25, 0.5, 0.75, 1.0]) {
        window.scrollTo(0, document.body.scrollHeight * pct);
        await new Promise(r => setTimeout(r, 500));
    }
})();
"""


# ── Cleaning ──────────────────────────────────────────────────────────────────

def resolve_url(raw_url: str) -> str:
    """Turn relative/tracking URL into a clean /dp/ URL."""
    if not raw_url:
        return ""
    # Extract ASIN from encoded tracking URLs
    dp_encoded = re.search(r'%2Fdp%2F([A-Z0-9]{10})', raw_url)
    dp_direct  = re.search(r'/dp/([A-Z0-9]{10})', raw_url)
    if dp_encoded:
        return f"https://www.amazon.in/dp/{dp_encoded.group(1)}"
    elif dp_direct:
        return f"https://www.amazon.in/dp/{dp_direct.group(1)}"
    elif raw_url.startswith("/"):
        return "https://www.amazon.in" + raw_url
    return raw_url


def clean_listing(p: dict) -> dict | None:
    title = (p.get("title") or "").strip()
    if not title:
        return None  # skip banner/widget rows

    out = {}
    out["title"]    = title
    out["asin"]     = (p.get("asin") or "").strip()
    out["url"]      = resolve_url(p.get("url") or "")

    # If ASIN still missing, extract from URL
    if not out["asin"] and out["url"]:
        m = re.search(r'/dp/([A-Z0-9]{10})', out["url"])
        if m:
            out["asin"] = m.group(1)

    out["image"]    = (p.get("image") or "").strip()

    # Rating: "4.2 out of 5 stars" → "4.2"
    rating_raw = p.get("rating") or ""
    m = re.search(r'[\d.]+', rating_raw)
    out["rating"]   = m.group() if m else ""

    # Review count: "1,234" → "1234"
    rc = re.sub(r'[^\d]', '', p.get("review_count") or "")
    out["review_count"] = rc

    # Price: keep first ₹ value found
    price_raw = p.get("price") or ""
    prices = re.findall(r'₹[\d,]+', price_raw)
    out["price"] = prices[0].replace(",", "") if prices else ""

    orig = p.get("original_price") or ""
    out["original_price"] = orig.replace(",", "").strip()

    out["discount"]  = (p.get("discount") or "").strip()
    out["sponsored"] = "Sponsored" if (p.get("sponsored") or "") else ""
    out["delivery"]  = (p.get("delivery") or "").strip()
    out["badge"]     = (p.get("badge") or "").strip()

    return out


# ── Scraper ───────────────────────────────────────────────────────────────────

# ── Resume helpers ────────────────────────────────────────────────────────────

def load_listing_progress(out_file: Path, progress_file: Path) -> tuple[list[dict], set[str], set[int]]:
    """
    Load existing listing data + which pages have already been scraped.
    Returns (products, seen_asins, done_pages).
    """
    products:   list[dict] = []
    seen_asins: set[str]   = set()
    done_pages: set[int]   = set()

    if out_file.exists():
        try:
            products   = json.loads(out_file.read_text(encoding="utf-8"))
            seen_asins = {p["asin"] for p in products if p.get("asin")}
            print(f"📂 Resuming listing — {len(products)} products already in {out_file.name}")
        except Exception as e:
            print(f"⚠️  Could not read {out_file.name} ({e}), starting fresh.")

    if progress_file.exists():
        try:
            done_pages = set(json.loads(progress_file.read_text()))
            print(f"📄 Pages already scraped: {sorted(done_pages)}")
        except Exception:
            pass

    return products, seen_asins, done_pages


def save_listing(out_file: Path, progress_file: Path, products: list[dict], done_pages: set[int]) -> None:
    out_file.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    progress_file.write_text(json.dumps(sorted(done_pages)), encoding="utf-8")


# ── Scraper ───────────────────────────────────────────────────────────────────

async def scrape_listing(
    query: str,
    pages: int = 3,
    headless: bool = True,
    out_file: Path = None,
) -> list[dict]:

    safe_query    = re.sub(r'[^\w]', '_', query)
    out_file      = out_file or Path(f"amazon_listing_{safe_query}.json")
    progress_file = out_file.with_suffix(".pages.json")  # tracks done page numbers

    # ── Resume: load existing data ────────────────────────────────────────
    all_products, seen_asins, done_pages = load_listing_progress(out_file, progress_file)

    pages_to_scrape = [p for p in range(1, pages + 1) if p not in done_pages]
    if not pages_to_scrape:
        print(f"✅ All {pages} pages already scraped — nothing to do.")
        return all_products
    print(f"🔄 Pages to scrape: {pages_to_scrape}\n")

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=headless,
        headers={"Accept-Language": "en-IN,en;q=0.9"},
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for page in pages_to_scrape:
            url = (
                f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
                f"&page={page}&language=en_IN"
            )
            print(f"\n📄 Page {page}/{pages}: {url}")

            config = CrawlerRunConfig(
                extraction_strategy=JsonCssExtractionStrategy(LISTING_SCHEMA),
                wait_for="[data-component-type='s-search-result']",
                delay_before_return_html=3.0,
                js_code=SCROLL_JS,
            )

            result = await crawler.arun(url=url, config=config)

            if not result.success or not result.extracted_content:
                print(f"  ❌ Failed: {result.error_message}  (will retry on next run)")
                await asyncio.sleep(3)
                continue  # don't mark as done — will retry next run

            raw_items     = json.loads(result.extracted_content)
            page_products = []

            for raw in raw_items:
                cleaned = clean_listing(raw)
                if not cleaned:
                    continue
                asin = cleaned["asin"]
                if asin and asin in seen_asins:
                    continue  # deduplicate across pages
                if asin:
                    seen_asins.add(asin)
                page_products.append(cleaned)

            all_products.extend(page_products)
            done_pages.add(page)

            # ── Save after every page — crash-safe ───────────────────────
            save_listing(out_file, progress_file, all_products, done_pages)
            print(f"  ✅ {len(page_products)} new  |  total: {len(all_products)}  |  saved ✓")

            await asyncio.sleep(2)

    return all_products


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Amazon listing scraper (with resume)")
    parser.add_argument("--query",    default="phone", help="Search query")
    parser.add_argument("--pages",    default=3, type=int, help="Number of pages to scrape")
    parser.add_argument("--output",   default="",  help="Override output filename")
    parser.add_argument("--headless", default=True, action=argparse.BooleanOptionalAction)
    args = parser.parse_args()

    safe_query = re.sub(r'[^\w]', '_', args.query)
    out_file   = Path(args.output) if args.output else Path(f"amazon_listing_{safe_query}.json")

    print(f"\n🔍 Amazon listing scraper  (resume-enabled)")
    print(f"   query  : '{args.query}'  |  pages: {args.pages}")
    print(f"   output : {out_file}")
    print("=" * 60)

    products = await scrape_listing(
        args.query,
        pages=args.pages,
        headless=args.headless,
        out_file=out_file,
    )

    print(f"\n{'='*60}")
    print(f"✅ Total unique products : {len(products)}")
    print(f"📁 Saved to             : {out_file}")
    print(f"\n── Sample (first 3) ──")
    for p in products[:3]:
        print(f"\n  📦 {p['title'][:60]}")
        print(f"     ASIN  : {p['asin']}")
        print(f"     Price : {p['price']}  (was {p['original_price']})  {p['discount']}")
        print(f"     Rating: {p['rating']} ⭐ ({p['review_count']} reviews)")
        print(f"     URL   : {p['url']}")


if __name__ == "__main__":
    asyncio.run(main())
