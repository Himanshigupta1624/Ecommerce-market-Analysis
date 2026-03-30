# processing/powerbi_prep.py
"""
Exports PowerBI-ready flat CSVs from processed data.
PowerBI doesn't handle nested dicts/lists, so this flattens everything.

Usage:
    python powerbi_prep.py --query "laptops"
    python powerbi_prep.py --query "smartphones"
"""

import argparse
import re
import json
import pandas as pd
from pathlib import Path


def flatten_for_powerbi(query: str, data_dir: str = None):
    if data_dir is None:
        data_dir = Path(__file__).parent / "data" / "processed"
    else:
        data_dir = Path(data_dir)
    
    safe_q   = re.sub(r'[^\w]', '_', query.lower())
    src_path = (data_dir / f"final_{safe_q}.csv").resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Run pipeline.py first: {src_path}")

    df = pd.read_csv(src_path)

    # ── Main Products table ───────────────────────────────────────────────
    output_dir = src_path.parent
    
    products_cols = [
        "asin","title","brand","category","price","original_price",
        "discount_amount","discount_pct","rating","review_count",
        "rating_category","price_segment","value_score","popularity",
        "sold_by","availability","main_image","url",
    ]
    products_cols = [c for c in products_cols if c in df.columns]
    products_df   = df[products_cols].copy()
    products_df.to_csv(output_dir / f"pbi_products_{safe_q}.csv", index=False)
    print(f"✅ Products table: {len(products_df)} rows → pbi_products_{safe_q}.csv")

    # ── Brand Summary table ───────────────────────────────────────────────
    brand_df = df.groupby("brand").agg(
        product_count  = ("asin",          "count"),
        avg_price      = ("price",         "mean"),
        min_price      = ("price",         "min"),
        max_price      = ("price",         "max"),
        avg_rating     = ("rating",        "mean"),
        total_reviews  = ("review_count",  "sum"),
        avg_value_score= ("value_score",   "mean"),
    ).round(2).reset_index()
    brand_df.to_csv(output_dir / f"pbi_brands_{safe_q}.csv", index=False)
    print(f"✅ Brands table: {len(brand_df)} rows → pbi_brands_{safe_q}.csv")

    # ── Segment Summary table ─────────────────────────────────────────────
    seg_df = df.groupby("price_segment", observed=True).agg(
        product_count = ("asin",   "count"),
        avg_price     = ("price",  "mean"),
        avg_rating    = ("rating", "mean"),
        min_price     = ("price",  "min"),
        max_price     = ("price",  "max"),
    ).round(2).reset_index()
    seg_df.to_csv(output_dir / f"pbi_segments_{safe_q}.csv", index=False)
    print(f"✅ Segments table: {len(seg_df)} rows → pbi_segments_{safe_q}.csv")

    # ── Seller Summary table ──────────────────────────────────────────────
    seller_df = df.groupby("sold_by").agg(
        product_count = ("asin",          "count"),
        avg_price     = ("price",         "mean"),
        avg_rating    = ("rating",        "mean"),
        total_reviews = ("review_count",  "sum"),
    ).round(2).reset_index().sort_values("product_count", ascending=False)
    seller_df.to_csv(output_dir / f"pbi_sellers_{safe_q}.csv", index=False)
    print(f"✅ Sellers table: {len(seller_df)} rows → pbi_sellers_{safe_q}.csv")

    # ── Category-specific feature table (if columns exist) ───────────────
    cat_feature_cols = [
        "ram_gb","storage_gb","display_inch","processor_clean",   # laptops
        "battery_mah","camera_mp","connectivity","has_anc",       # phones / headphones
        "screen_inch","resolution","refresh_hz","smart_tv",       # TVs
        "capacity_l","capacity_kg","door_type","type","star_rating", # appliances
    ]
    cat_cols = ["asin"] + [c for c in cat_feature_cols if c in df.columns]
    if len(cat_cols) > 1:
        feat_df = df[cat_cols].dropna(how="all", subset=cat_cols[1:])
        feat_df.to_csv(output_dir / f"pbi_features_{safe_q}.csv", index=False)
        print(f"✅ Features table: {len(feat_df)} rows → pbi_features_{safe_q}.csv")

    print(f"\n📊 PowerBI import guide:")
    print(f"  1. Open PowerBI Desktop")
    print(f"  2. Get Data → Text/CSV → select pbi_products_{safe_q}.csv")
    print(f"  3. Repeat for brands, segments, sellers, features tables")
    print(f"  4. In Model view, link all tables on 'asin' or 'brand' column")
    print(f"  5. Recommended visuals:")
    print(f"     - Card: total products, avg price, avg rating")
    print(f"     - Bar chart: avg price by brand")
    print(f"     - Pie/Donut: price_segment distribution")
    print(f"     - Scatter: price vs rating (bubble = review_count)")
    print(f"     - Table: top products by value_score")
    print(f"     - Slicer: brand, price_segment, rating_category")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query",    required=True)
    parser.add_argument("--data_dir", default=None)
    args = parser.parse_args()
    flatten_for_powerbi(args.query, args.data_dir)
