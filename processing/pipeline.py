# processing/pipeline.py
"""
Dynamic product data pipeline — works for ANY Amazon product category.
Merges listing + product JSONs, auto-detects category-specific features,
engineers universal features, and outputs:
  - final_dataset.csv        → for PowerBI
  - final_dataset.json       → for Streamlit / API

Usage:
    python pipeline.py --query "laptops"
    python pipeline.py --query "smartphones"
    python pipeline.py --query "headphones"
    python pipeline.py --query "washing machines"
"""

import argparse
import json
import re
import os
import pandas as pd
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY CONFIGS
# Each category defines what to auto-extract from title/features text.
# Add new categories here — no changes needed anywhere else.
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_CONFIGS = {
    "laptops": {
        "price_bins":   [0, 30000, 60000, 100000, 200000, 9999999],
        "price_labels": ["Budget", "Mid-Range", "Upper Mid", "Premium", "Ultra Premium"],
        "extractors": {
            "ram_gb": lambda t: _re_int(t, r'(\d+)\s?GB\s?(?:DDR\d?\s?)?RAM'),
            "storage_gb": lambda t: _re_int(t, r'(\d+)\s?(?:GB|TB)\s?SSD') or
                                    (_re_int(t, r'(\d+)\s?TB\s?(?:SSD|HDD)') or 0) * 1024,
            "display_inch": lambda t: _re_float(t, r'(\d+\.?\d*)\s?(?:inch|"|\'\'|cm)'),
            "processor": lambda t: _re_str(t, r'(Core\s?i[3579][\s\-]\d+|Ryzen\s?\d[\s\-]?\d+\w*|'
                                              r'M[123]\s?(?:Pro|Max)?|Snapdragon\s?\d+)'),
        },
        "normalize": {
            "processor": {
                "i3": ["i3"], "i5": ["i5"], "i7": ["i7"], "i9": ["i9"],
                "Ryzen 5": ["ryzen 5", "ryzen5"],
                "Ryzen 7": ["ryzen 7", "ryzen7"],
                "Ryzen 9": ["ryzen 9", "ryzen9"],
                "Apple M": ["m1", "m2", "m3"],
            }
        }
    },

    "smartphones": {
        "price_bins":   [0, 10000, 20000, 40000, 70000, 9999999],
        "price_labels": ["Budget", "Mid-Range", "Upper Mid", "Premium", "Flagship"],
        "extractors": {
            "ram_gb":      lambda t: _re_int(t, r'(\d+)\s?GB\s?RAM'),
            "storage_gb":  lambda t: _re_int(t, r'(\d+)\s?GB\s?(?:ROM|Storage|Internal)'),
            "battery_mah": lambda t: _re_int(t, r'(\d{3,5})\s?mAh'),
            "camera_mp":   lambda t: _re_int(t, r'(\d+)\s?MP'),
            "display_inch":lambda t: _re_float(t, r'(\d+\.?\d*)\s?(?:inch|")'),
            "processor":   lambda t: _re_str(t, r'(Snapdragon\s?\d+\w*|Dimensity\s?\d+\w*|'
                                               r'Exynos\s?\d+\w*|Helio\s?\w+|A\d+\s?Bionic|'
                                               r'G\d+\s?(?:Express)?|Tensor\s?G?\d*)'),
        },
        "normalize": {
            "processor": {
                "Snapdragon 8xx": ["snapdragon 8"],
                "Snapdragon 7xx": ["snapdragon 7"],
                "Snapdragon 6xx": ["snapdragon 6"],
                "Dimensity 9xxx": ["dimensity 9"],
                "Dimensity 8xxx": ["dimensity 8"],
                "Apple A-series": ["a15", "a16", "a17", "a18"],
                "Tensor":         ["tensor"],
            }
        }
    },

    "headphones": {
        "price_bins":   [0, 1000, 3000, 8000, 20000, 9999999],
        "price_labels": ["Budget", "Mid", "Upper Mid", "Premium", "Audiophile"],
        "extractors": {
            "connectivity": lambda t: "Wireless" if re.search(r'wireless|bluetooth|bt', t, re.I) else "Wired",
            "has_anc":      lambda t: bool(re.search(r'\bANC\b|noise cancel', t, re.I)),
            "driver_mm":    lambda t: _re_int(t, r'(\d+)\s?mm\s?driver'),
            "battery_hrs":  lambda t: _re_int(t, r'(\d+)\s?(?:hrs?|hours?)\s?(?:battery|playback|music)'),
        },
        "normalize": {}
    },

    "televisions": {
        "price_bins":   [0, 15000, 30000, 60000, 150000, 9999999],
        "price_labels": ["Budget", "Mid", "Upper Mid", "Premium", "OLED/QLED"],
        "extractors": {
            "screen_inch":  lambda t: _re_int(t, r'(\d{2,3})\s?(?:inch|cm|")'),
            "resolution":   lambda t: _re_str(t, r'(4K|8K|Full HD|HD Ready|FHD|QHD|QLED|OLED|AMOLED)'),
            "refresh_hz":   lambda t: _re_int(t, r'(\d+)\s?Hz'),
            "smart_tv":     lambda t: bool(re.search(r'smart\s?tv|android\s?tv|webos|tizen', t, re.I)),
        },
        "normalize": {
            "resolution": {
                "4K UHD": ["4k", "uhd"],
                "Full HD": ["full hd", "fhd", "1080"],
                "HD Ready": ["hd ready", "720"],
                "8K":       ["8k"],
                "QLED":     ["qled"],
                "OLED":     ["oled"],
            }
        }
    },

    "refrigerators": {
        "price_bins":   [0, 15000, 25000, 40000, 70000, 9999999],
        "price_labels": ["Budget", "Mid", "Upper Mid", "Premium", "Luxury"],
        "extractors": {
            "capacity_l":   lambda t: _re_int(t, r'(\d{2,4})\s?(?:L|Litres?|Liters?)'),
            "door_type":    lambda t: _re_str(t, r'(Single Door|Double Door|Side.by.Side|French Door|Triple Door)'),
            "star_rating":  lambda t: _re_int(t, r'(\d)\s?Star'),
            "frost_free":   lambda t: bool(re.search(r'frost.free|no.frost', t, re.I)),
        },
        "normalize": {}
    },

    "washing_machines": {
        "price_bins":   [0, 10000, 20000, 35000, 60000, 9999999],
        "price_labels": ["Budget", "Mid", "Upper Mid", "Premium", "Luxury"],
        "extractors": {
            "capacity_kg":  lambda t: _re_float(t, r'(\d+\.?\d*)\s?Kg'),
            "type":         lambda t: _re_str(t, r'(Front Load|Top Load|Semi.Automatic|Fully.Automatic)'),
            "rpm":          lambda t: _re_int(t, r'(\d{3,4})\s?RPM'),
            "star_rating":  lambda t: _re_int(t, r'(\d)\s?Star'),
        },
        "normalize": {}
    },

    # ── Generic fallback (used for any unknown category) ──────────────────
    "_generic": {
        "price_bins":   [0, 1000, 5000, 15000, 50000, 9999999],
        "price_labels": ["Very Budget", "Budget", "Mid", "Premium", "Luxury"],
        "extractors": {},
        "normalize": {}
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# REGEX HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _re_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, str(text or ""), re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            pass
    return None

def _re_float(text: str, pattern: str) -> float | None:
    m = re.search(pattern, str(text or ""), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    return None

def _re_str(text: str, pattern: str) -> str | None:
    m = re.search(pattern, str(text or ""), re.IGNORECASE)
    return m.group(1).strip() if m else None


# ─────────────────────────────────────────────────────────────────────────────
# DETECT CATEGORY
# ─────────────────────────────────────────────────────────────────────────────

def detect_category(query: str) -> str:
    """Map a free-form query to a known category key."""
    q = query.lower().replace("-", " ").replace("_", " ")
    mapping = {
        "laptops":         ["laptop", "notebook", "ultrabook", "gaming laptop"],
        "smartphones":     ["phone", "smartphone", "mobile", "iphone", "android"],
        "headphones":      ["headphone", "earphone", "earbuds", "tws", "headset"],
        "televisions":     ["tv", "television", "smart tv", "oled", "qled"],
        "refrigerators":   ["fridge", "refrigerator", "double door", "single door"],
        "washing_machines":["washing machine", "washer", "front load", "top load"],
    }
    for key, keywords in mapping.items():
        if any(kw in q for kw in keywords):
            return key
    return "_generic"


# ─────────────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────────────

def load_json_as_df(path: str) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    # Flatten tech_specs dict column if present
    if "tech_specs" in df.columns:
        specs = df["tech_specs"].apply(
            lambda x: x if isinstance(x, dict) else {}
        )
        specs_df = pd.json_normalize(specs).add_prefix("spec_")
        df = pd.concat([df.drop(columns=["tech_specs"]), specs_df], axis=1)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# PRICE CLEANING
# ─────────────────────────────────────────────────────────────────────────────

def clean_price(price) -> int | None:
    if pd.isna(price) or str(price).strip() in ["", "N/A", "None"]:
        return None
    cleaned = re.sub(r"[₹,\s]", "", str(price))
    try:
        return int(float(cleaned))
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# BRAND EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_BRANDS = [
    "Dell", "HP", "Lenovo", "Asus", "Acer", "Apple", "MSI", "Samsung",
    "LG", "Sony", "Xiaomi", "Redmi", "OnePlus", "Realme", "Vivo", "Oppo",
    "Motorola", "Nokia", "Nothing", "Boat", "JBL", "Bose", "Sennheiser",
    "Whirlpool", "IFB", "Bosch", "Haier", "Godrej", "Panasonic", "Toshiba",
    "TCL", "Hisense", "Vu", "Mi", "Google", "Poco", "iQOO",
]

def extract_brand(row) -> str:
    brand = str(row.get("brand", "") or "").strip()
    if brand and len(brand) > 1:
        return brand
    title = str(row.get("title", "") or "")
    # Try known brands first
    for b in KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(b) + r'\b', title, re.IGNORECASE):
            return b
    # Fallback: first word of title
    words = title.split()
    return words[0] if words else "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZE EXTRACTED FEATURE
# ─────────────────────────────────────────────────────────────────────────────

def normalize_field(value: str | None, norm_map: dict) -> str:
    if not value:
        return "Other"
    v = str(value).lower()
    for label, keywords in norm_map.items():
        if any(kw in v for kw in keywords):
            return label
    return str(value).strip()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(query: str, data_dir: str = "../scraper", out_dir: str = "../data/processed"):
    safe_q   = re.sub(r'[^\w]', '_', query.lower())
    category = detect_category(query)
    config   = CATEGORY_CONFIGS.get(category, CATEGORY_CONFIGS["_generic"])

    print(f"\n{'='*60}")
    print(f"📦 Query    : {query}")
    print(f"📂 Category : {category}")
    print(f"{'='*60}\n")

    # ── Load files ──────────────────────────────────────────────────────
    listing_path = Path(data_dir) / f"amazon_listing_{safe_q}.json"
    product_path = Path(data_dir) / f"amazon_products_amazon_listing_{safe_q}.json"

    if not listing_path.exists():
        raise FileNotFoundError(f"Listing file not found: {listing_path}")
    if not product_path.exists():
        raise FileNotFoundError(f"Product file not found: {product_path}")

    listing_df = load_json_as_df(str(listing_path))
    product_df = load_json_as_df(str(product_path))
    print(f"  Listing  : {len(listing_df)} rows")
    print(f"  Products : {len(product_df)} rows")

    # ── Clean prices ────────────────────────────────────────────────────
    listing_df["price"] = listing_df["price"].apply(clean_price)
    product_df["price"] = product_df["price"].apply(clean_price)

    # ── Merge ───────────────────────────────────────────────────────────
    df = pd.merge(
        product_df,
        listing_df[["asin", "price"]].rename(columns={"price": "price_listing"}),
        on="asin",
        how="left",
    )
    df["price"] = df["price"].combine_first(df["price_listing"])
    df = df.drop(columns=["price_listing"], errors="ignore")

    # ── Numeric fields ───────────────────────────────────────────────────
    df["rating"]       = pd.to_numeric(df.get("rating"),       errors="coerce")
    df["review_count"] = pd.to_numeric(df.get("review_count"), errors="coerce").fillna(0)

    # ── Text fields ──────────────────────────────────────────────────────
    text_cols = ["brand", "category", "sold_by", "availability", "title",
                 "description", "features", "main_image", "url", "asin"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
        else:
            df[col] = ""

    df["description"] = df["description"].str[:500]
    df["features"]    = df["features"].str[:400]

    # ── Brand ────────────────────────────────────────────────────────────
    df["brand"] = df.apply(extract_brand, axis=1)

    # ── Category-specific feature extraction ─────────────────────────────
    # We search both `features` and `title` combined for maximum coverage
    df["_search_text"] = (df["title"] + " " + df["features"]).str.lower()

    for field, extractor in config["extractors"].items():
        df[field] = df["_search_text"].apply(extractor)
        # Normalize if a norm_map exists for this field
        norm_map = config["normalize"].get(field)
        if norm_map:
            df[f"{field}_clean"] = df[field].apply(
                lambda v: normalize_field(v, norm_map)
            )

    df = df.drop(columns=["_search_text"], errors="ignore")

    # ── Remove invalid rows ───────────────────────────────────────────────
    before = len(df)
    df = df[df["price"].notna() & (df["price"] > 0)]
    df = df[df["rating"].notna()]
    df = df.drop_duplicates(subset=["asin"])
    print(f"\n  Rows before cleaning : {before}")
    print(f"  Rows after cleaning  : {len(df)}")

    # ── Universal feature engineering ─────────────────────────────────────
    # Price segments (dynamic per category)
    df["price_segment"] = pd.cut(
        df["price"],
        bins=config["price_bins"],
        labels=config["price_labels"],
        right=True,
    ).astype(str)

    # Rating category
    df["rating_category"] = df["rating"].apply(
        lambda x: "Excellent" if x >= 4.5 else ("Good" if x >= 4.0 else
                  ("Average" if x >= 3.0 else "Poor"))
    )

    # Value score: rating × log(review_count+1) / price × 100000
    # Log-scaled so 10k reviews isn't 1000x better than 10 reviews
    import numpy as np
    df["value_score"] = (
        df["rating"] * np.log1p(df["review_count"]) / df["price"] * 100000
    ).round(4)

    # Popularity tier
    rc_33 = df["review_count"].quantile(0.33)
    rc_66 = df["review_count"].quantile(0.66)
    df["popularity"] = df["review_count"].apply(
        lambda x: "High" if x > rc_66 else ("Medium" if x > rc_33 else "Low")
    )

    # Discount amount (if original_price available)
    if "original_price" in df.columns:
        df["original_price_clean"] = df["original_price"].apply(clean_price)
        df["discount_amount"] = (
            df["original_price_clean"] - df["price"]
        ).clip(lower=0)
        df["discount_pct"] = (
            df["discount_amount"] / df["original_price_clean"].replace(0, pd.NA) * 100
        ).round(1)
    else:
        df["discount_amount"] = 0
        df["discount_pct"]    = 0

    # Prime eligible as bool
    if "prime" in df.columns:
        df["prime"] = df["prime"].astype(str).str.lower().isin(["true", "1", "yes"])

    # ── Final column selection ─────────────────────────────────────────────
    # Start with universal cols, then add any category-specific ones
    universal_cols = [
        "asin", "url", "title", "brand", "category",
        "price", "original_price_clean", "discount_amount", "discount_pct",
        "rating", "review_count", "rating_category",
        "price_segment", "value_score", "popularity",
        "sold_by", "availability",
        "features", "description", "main_image",
    ]
    # Add category-specific extracted columns
    extracted_cols = list(config["extractors"].keys())
    normalized_cols = [f"{f}_clean" for f in config["normalize"].keys()
                       if f"{f}_clean" in df.columns]
    # Add spec_ columns from tech_specs dict
    spec_cols = [c for c in df.columns if c.startswith("spec_")]

    all_cols = universal_cols + extracted_cols + normalized_cols + spec_cols
    final_cols = [c for c in all_cols if c in df.columns]
    final_df   = df[final_cols].copy()

    # ── Rename original_price_clean → original_price ──────────────────────
    final_df = final_df.rename(columns={"original_price_clean": "original_price"})

    # ── Save ──────────────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    csv_path  = Path(out_dir) / f"final_{safe_q}.csv"
    json_path = Path(out_dir) / f"final_{safe_q}.json"

    final_df.to_csv(csv_path, index=False)
    final_df.to_json(json_path, orient="records", indent=2, force_ascii=False)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n✅ Pipeline complete!")
    print(f"  Products   : {len(final_df)}")
    print(f"  Brands     : {final_df['brand'].nunique()}")
    print(f"  Price range: ₹{int(final_df['price'].min()):,} – ₹{int(final_df['price'].max()):,}")
    print(f"  Avg rating : {final_df['rating'].mean():.2f}")
    print(f"  Columns    : {list(final_df.columns)}")
    print(f"\n  📁 CSV  → {csv_path}")
    print(f"  📁 JSON → {json_path}")

    return final_df, category, config


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamic Amazon product pipeline")
    parser.add_argument("--query",    required=True, help="Product query (e.g. 'laptops')")
    parser.add_argument("--data_dir", default="../scraper",          help="Folder with scraped JSONs")
    parser.add_argument("--out_dir",  default="../data/processed",   help="Output folder")
    args = parser.parse_args()

    run_pipeline(args.query, args.data_dir, args.out_dir)
