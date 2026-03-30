# 📦 Amazon Ecommerce Market Analysis

A comprehensive data pipeline for scraping, processing, and analyzing Amazon product data across multiple categories (laptops, smartphones, headphones, TVs, appliances, etc.). Includes automated feature extraction, PowerBI integration, and an interactive Streamlit dashboard with AI-powered insights.

---

## ✨ Features

- **🕷️ Smart Web Scraping** — Resume-enabled scrapers using Crawl4AI for listings and product details
- **🔄 Dynamic Pipeline** — Auto-detects product categories and extracts category-specific features
- **📊 PowerBI Export** — Flattened CSVs ready for business intelligence dashboards
- **📈 Interactive Dashboard** — Streamlit app with 10+ visualizations and filtering
- **🤖 AI Insights** — Claude API integration for natural language market analysis
- **💾 Feature Engineering** — Automatic extraction of specs (RAM, storage, processor, battery, etc.)
- **✅ Multi-Category Support** — Laptops, smartphones, headphones, TVs, refrigerators, washing machines, + generic fallback

---

## 📁 Project Structure

```
Ecommerce market Analysis/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── scraper/                           # Web scraping modules
│   ├── scraper_listing.py            # Scrapes search result listings
│   ├── scraper_product.py            # Scrapes full product details
│   ├── amazon_listing_*.json         # Listing data (output)
│   └── amazon_products_*.json        # Product details (output)
├── processing/                        # Data pipeline
│   └── pipeline.py                   # Merges, cleans, engineers features
├── data/                              # Data storage
│   ├── raw/                          # Raw scraped files
│   └── processed/                    # Final datasets
│       ├── final_*.csv               # Processed data for PowerBI
│       ├── final_*.json              # Data for Streamlit
│       └── pbi_*.csv                 # PowerBI-ready tables
├── powerbi_prep.py                   # Exports PowerBI tables
├── app/                               # Streamlit dashboard
│   └── streamlit_app.py              # Interactive market analysis dashboard

```

---

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Navigate to project
cd "e:\projects\Ecommerce market Analysis"

# Create virtual environment (if needed)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies from requirements.txt
pip install -r requirements.txt
```

### 2. Scrape Amazon Data

```bash
cd scraper

# Scrape listings (search results)
python scraper_listing.py --query "smartphones" --pages 3

# Scrape product details for each listing
python scraper_product.py --input ../data/amazon_listing_smartphones.json --limit 50
```

**Output**: JSON files saved to `../data/` folder

**Resume Logic**: Both scrapers support automatic resume — if interrupted, just re-run and they'll skip already-scraped items.

### 3. Process Data

```bash
cd processing

# Run pipeline (auto-detects category)
python pipeline.py --query "smartphones"

# Output: final_smartphones.csv, final_smartphones.json
```

### 4. Export for PowerBI

```bash
cd ..

# Generate PowerBI tables
python powerbi_prep.py --query "smartphones"

# Output: pbi_products_smartphones.csv, pbi_brands_smartphones.csv, etc.
```

### 5. Launch Dashboard

```bash
cd app

# Start Streamlit app
streamlit run streamlit_app.py

# Open http://localhost:8501 in browser
```

---

## 📊 Data Flow

```
Search Query
    ↓
scraper_listing.py → ../data/amazon_listing_*.json (57 listings)
    ↓
scraper_product.py → ../data/amazon_products_*.json (10 full details)
    ↓
pipeline.py → Merge, clean, extract features, engineer metrics
    ↓
final_*.csv / final_*.json
    ↓
powerbi_prep.py ──→ pbi_products_*.csv (PowerBI)
                    pbi_brands_*.csv
                    pbi_segments_*.csv
                    pbi_sellers_*.csv
                    pbi_features_*.csv
    ↓
    ├─→ PowerBI Desktop (import CSVs)
    └─→ streamlit_app.py (interactive dashboard)
```

---

## 🔧 Command Reference

### Scraper: Listings

```bash
python scraper_listing.py --query "laptops" --pages 5 --output ../data/my_laptops.json
```

| Argument  | Default | Description |
|-----------|---------|-------------|
| `--query` | "phone" | Search query for Amazon |
| `--pages` | 3 | Number of pages to scrape |
| `--output` | auto (../data/amazon_listing_*.json) | Output filename |
| `--headless` | True | Run browser headless |

### Scraper: Products

```bash
python scraper_product.py --input ../data/amazon_listing_laptops.json --limit 50
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | - | Input listing JSON file path |
| `--limit` | None | Max products to scrape |
| `--url` | - | Scrape single URL directly |
| `--headless` | True | Run browser headless |

### Pipeline

```bash
python pipeline.py --query "smartphones" --data_dir ../data --out_dir ../data/processed
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--query` | - | Product query (e.g., "laptops") |
| `--data_dir` | ../data | Folder with scraped JSONs |
| `--out_dir` | ../data/processed | Output folder for CSVs |

### PowerBI Prep

```bash
python powerbi_prep.py --query "smartphones" --data_dir ../data/processed
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--query` | - | Product query (e.g., "laptops") |
| `--data_dir` | auto | Processed data directory |

---

## 🏷️ Supported Categories & Features

The pipeline auto-detects category keywords and extracts relevant features:

### 📱 Smartphones
- RAM, Storage, Battery (mAh), Camera (MP), Display (inch)
- Processor: Snapdragon, Dimensity, Exynos, etc.
- **Price bins**: Budget, Mid-Range, Upper Mid, Premium, Flagship

### 💻 Laptops
- RAM, Storage (SSD/HDD), Display (inch)
- Processor: Core i3/i5/i7/i9, Ryzen, Apple M-series
- **Price bins**: Budget, Mid-Range, Upper Mid, Premium, Ultra Premium

### 🎧 Headphones
- Connectivity (Wireless/Wired), ANC, Driver Size, Battery Life
- **Price bins**: Budget, Mid, Upper Mid, Premium, Audiophile

### 📺 Televisions
- Screen Size (inch), Resolution (4K/8K/FHD), Refresh Rate (Hz)
- Type: Smart TV, OLED, QLED, etc.
- **Price bins**: Budget, Mid, Upper Mid, Premium, OLED/QLED

### ❄️ Refrigerators
- Capacity (Liters), Door Type, Star Rating
- Frost-Free indication
- **Price bins**: Budget, Mid, Upper Mid, Premium, Luxury

### 🧺 Washing Machines
- Capacity (Kg), Type (Front/Top Load), RPM, Star Rating
- **Price bins**: Budget, Mid, Upper Mid, Premium, Luxury

### 🎯 Generic Fallback
For unsupported categories, uses generic price bins and basic extraction.

---

## 📊 Output Data Structure

### `final_*.csv` Columns
```
asin                 : Amazon Standard ID
url                  : Product URL
title                : Product title
brand                : Brand name
category             : Product category
price                : Current price (₹)
original_price       : Original/MRP (₹)
discount_amount      : Discount in ₹
discount_pct         : Discount percentage
rating               : Customer rating (0-5)
review_count         : Number of reviews
rating_category      : High/Low (4+ or <4)
price_segment        : Budget/Mid/Premium/etc.
value_score          : rating × reviews / price
popularity           : High/Medium/Low (review-based)
sold_by              : Seller name
availability         : In stock/Out of stock/etc.
[category-specific]  : ram_gb, storage_gb, battery_mah, processor_clean, etc.
```

### PowerBI Tables
- **pbi_products_*.csv** — Main product table with all columns
- **pbi_brands_*.csv** — Brand aggregates (count, avg price, rating)
- **pbi_segments_*.csv** — Price segment analysis
- **pbi_sellers_*.csv** — Seller rankings
- **pbi_features_*.csv** — Category-specific technical specs

---

## 📈 Streamlit Dashboard Features

### Visualizations
1. **Price Distribution** — Histogram of product prices
2. **Brand Analysis** — Avg price, ratings by brand
3. **Price vs Rating** — Scatter plot with brand colors
4. **Market Segments** — Donut chart of price segments
5. **Brand Landscape** — Bubble chart (price, rating, review volume)
6. **Rating Distribution** — Histogram of customer ratings
7. **Best Value Products** — Top 10 by value score
8. **Category-Specific** — Dynamic charts based on extracted features
9. **KPI Cards** — Total products, brands, price range, avg rating
10. **Filter Controls** — Brand, price segment, rating category

### AI Insights
- Ask questions about the data in natural language
- Google Gemini API analyzes data and provides market insights
- Requires `GOOGLE_API_KEY` environment variable (get free key at https://aistudio.google.com/app/apikey)

### Filters (Optional)
- **Brand** — Single or multiple selection
- **Price Segment** — Budget, Mid, Premium, etc.
- **Rating Category** — High (4+), Low (<4)

---

## 🔑 Environment Variables

### For AI Insights (Required)

```bash
# Set your Google Gemini API key
set GOOGLE_API_KEY=sk-...
```

Or add to `.env` file:
```
GOOGLE_API_KEY=sk-...
```

Get your free API key at: https://aistudio.google.com/app/apikey

---

## 📝 Example Workflows

### Workflow 1: Scrape & Analyze Laptops

```bash
# 1. Scrape listings
cd scraper
python scraper_listing.py --query "gaming laptops" --pages 5

# 2. Scrape product details
python scraper_product.py --input ../data/amazon_listing_gaming_laptops.json

# 3. Process data
cd ../processing
python pipeline.py --query "gaming laptops"

# 4. Export to PowerBI
cd ..
python powerbi_prep.py --query "gaming laptops"

# 5. View dashboard
cd app
streamlit run streamlit_app.py
```

### Workflow 2: PowerBI Analysis

```bash
# After running pipeline.py...
python powerbi_prep.py --query "smartphones"

# Import in PowerBI Desktop:
# 1. Get Data → Text/CSV
# 2. Select: pbi_products_smartphones.csv
# 3. Repeat for: brands, segments, sellers, features tables
# 4. Model View: Create relationships on 'brand' or 'asin'
# 5. Create visualizations
```

### Workflow 3: Quick Market Insights

```bash
# Run pipeline for multiple categories
python processing/pipeline.py --query "smartphones"
python processing/pipeline.py --query "laptops"

# Launch dashboard
cd app && streamlit run streamlit_app.py

# Select dataset from sidebar
# Ask AI questions about market trends
```

---

## 🐛 Troubleshooting

### Browser/Scraper Issues

**Problem**: `timeout` or `Connection refused` during scraping

**Solution**:
- Check internet connection
- Increase `delay_before_return_html` in scraper config
- Reduce `--pages` or `--limit`
- Re-run (resume logic will skip completed pages)

---

### Missing JSON Files

**Problem**: `FileNotFoundError: amazon_listing_*.json`

**Solution**:
```bash
# Ensure you're in scraper/ directory
cd scraper
python scraper_listing.py --query "your-query"

# Output will be saved to ../data/amazon_listing_your_query.json
```

---

### Pipeline Fails on Missing Columns

**Problem**: `KeyError` during pipeline

**Solution**:
- Check that scraper ran successfully
- Verify JSON files exist: `ls scraper/amazon_*.json`
- Try re-running pipeline with `--query` that matches your JSON filename

---

### Streamlit Won't Start

**Problem**: ModuleNotFoundError

**Solution**:
```bash
pip install -r requirements.txt
```

---

### PowerBI CSV Has Wrong Data

**Problem**: Exported CSV is empty or has wrong query

**Solution**:
```bash
# Ensure final_*.csv exists (case-sensitive)
# Check it was created by pipeline
python processing/pipeline.py --query "your-query"

# Then try PowerBI prep
python powerbi_prep.py --query "your-query"
```

---

## 📋 Requirements

All project dependencies are listed in `requirements.txt`.

**Core packages:**
- **Python 3.10+**
- **pandas** — Data manipulation
- **crawl4ai** — Web scraping with AI-powered extraction
- **streamlit** — Interactive dashboard
- **plotly** — Visualizations
- **anthropic** — Claude API (optional, for AI insights)
- **beautifulsoup4** — HTML parsing
- **lxml** — XML/HTML processing
- Plus 50+ supporting libraries (see [requirements.txt](requirements.txt) for complete list)

**Install all dependencies:**
```bash
pip install -r requirements.txt
```

**Or install minimal core packages:**
```bash
pip install pandas crawl4ai streamlit plotly anthropic beautifulsoup4
```

---

## 🔄 Resume & Crash Recovery

Both scrapers support automatic resume:

- **Listings**: Tracks pages in `../data/amazon_listing_*.pages.json`
- **Products**: Skips already-scraped ASINs based on output JSON in `../data/`

If stopped/crashed:
```bash
# Just re-run — it picks up where it left off
python scraper_product.py --input ../data/amazon_listing_smartphones.json
```

---

## 📦 Generating requirements.txt

To generate or update `requirements.txt` from your current environment:

```bash
# Freeze all installed packages
pip freeze > requirements.txt

# Or use pip-tools for better management
pip install pip-tools
pip-compile requirements.in  # if using requirements.in
```

The provided `requirements.txt` includes 60+ packages with pinned versions for reproducibility.

---

## 📚 API Reference

### Key Classes/Functions

#### `scraper_listing.py`
- `scrape_listing(query, pages, headless, out_file)` — Main listing scraper
- `load_listing_progress(out_file, progress_file)` — Resume helper
- `clean_listing(p)` — Normalize product fields

#### `scraper_product.py`
- `scrape_product_details(products, limit, headless)` — Full product scraper
- `extract_rating_histogram(raw)` — Parse rating distribution

#### `pipeline.py`
- `run_pipeline(query, data_dir, out_dir)` — Main processing pipeline
- `detect_category(query)` — Auto-detect product category
- `extract_features(df, config)` — Extract category-specific specs
- `engineer_features(df, price_bins)` — Create value_score, segments, etc.

#### `powerbi_prep.py`
- `flatten_for_powerbi(query, data_dir)` — Export PowerBI tables

#### `streamlit_app.py`
- `load_data(path)` — Cached CSV loader
- `find_processed_files(data_dir)` — Discover available datasets
- `get_ai_insights(df, question, api_key)` — Query Claude API

---


