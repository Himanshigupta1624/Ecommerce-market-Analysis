"""
Dynamic Amazon Market Analysis Dashboard
Works for ANY product category.
Includes AI-powered insights via Google Gemini API.

Install:
    pip install streamlit pandas plotly google-generativeai

Run:
    streamlit run streamlit_app.py
"""

import re
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Amazon Market Analyser",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        border-left: 4px solid #ff9900;
    }
    .ai-box {
        background: linear-gradient(135deg, #667eea22, #764ba222);
        border: 1px solid #667eea55;
        border-radius: 10px;
        padding: 1.2rem;
    }
    .stPlotlyChart { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADER
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return pd.DataFrame(json.load(f))
    return pd.read_csv(path)


def find_processed_files(data_dir: str = "../data/processed") -> dict[str, str]:
    """Return {query_label: file_path} for all processed files."""
    p = Path(data_dir)
    files = {}
    for f in p.glob("final_*.csv"):
        label = f.stem.replace("final_", "").replace("_", " ").title()
        files[label] = str(f)
    return files


# ─────────────────────────────────────────────────────────────────────────────
# AI INSIGHTS (Claude)
# ─────────────────────────────────────────────────────────────────────────────

def get_ai_insights(df: pd.DataFrame, question: str, api_key: str) -> str:
    """Call Gemini API with a summary of the data + user question."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        # Build a compact data summary (don't send full dataset)
        summary = {
            "total_products": len(df),
            "brands": df["brand"].value_counts().head(8).to_dict(),
            "price_stats": {
                "min": int(df["price"].min()),
                "max": int(df["price"].max()),
                "mean": int(df["price"].mean()),
                "median": int(df["price"].median()),
            },
            "rating_stats": {
                "mean": round(df["rating"].mean(), 2),
                "top_rated": df.nlargest(3, "rating")[["brand","title","price","rating"]].to_dict("records"),
            },
            "price_segments": df["price_segment"].value_counts().to_dict(),
            "best_value": df.nlargest(5, "value_score")[
                ["brand", "title", "price", "rating", "review_count", "value_score"]
            ].to_dict("records"),
            "top_sellers": df["sold_by"].value_counts().head(5).to_dict(),
        }
        # Add any category-specific columns
        extra_cols = [c for c in df.columns if c not in [
            "asin","url","title","brand","category","price","original_price",
            "discount_amount","discount_pct","rating","review_count",
            "rating_category","price_segment","value_score","popularity",
            "sold_by","availability","features","description","main_image"
        ]]
        for col in extra_cols[:5]:
            try:
                summary[col + "_distribution"] = df[col].value_counts().head(6).to_dict()
            except Exception:
                pass

        system_prompt = (
            "You are an expert e-commerce market analyst specialising in Amazon India. "
            "You receive a structured JSON summary of scraped product data and answer "
            "the user's question with specific, data-backed insights. "
            "Be concise (max 200 words), insightful, and use bullet points. "
            "Format numbers with Indian rupee symbol ₹ and use commas for thousands."
        )

        user_msg = (
            f"{system_prompt}\n\n"
            f"Here is the market data summary:\n```json\n{json.dumps(summary, indent=2)}\n```\n\n"
            f"Question: {question}"
        )

        response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_msg
)

        return response.text

    except ImportError:
        return "❌ `google-generativeai` package not installed. Run: `pip install google-generativeai`"
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower():
            return (
                "⏸️ **Free tier quota exceeded**\n\n"
                "The free tier Gemini API has hit its daily limit. You can:\n"
                "1. **Wait 24 hours** for the free tier to reset\n"
                "2. **Upgrade to paid** at https://ai.google.dev/pricing\n"
                "3. **Use cached results** from previous sessions\n\n"
                "*Paid tier has much higher limits and better performance.*"
            )
        return f"❌ AI error: {error_str[:200]}"


# ─────────────────────────────────────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────────────────────────────────────

COLORS = px.colors.qualitative.Bold

def price_histogram(df):
    fig = px.histogram(
        df, x="price", nbins=40,
        title="Price Distribution",
        labels={"price": "Price (₹)"},
        color_discrete_sequence=["#ff9900"],
    )
    fig.update_layout(bargap=0.05, showlegend=False)
    return fig


def brand_avg_price(df):
    bd = df.groupby("brand")["price"].mean().sort_values(ascending=False).head(12).reset_index()
    fig = px.bar(
        bd, x="brand", y="price",
        title="Average Price by Brand",
        labels={"price": "Avg Price (₹)", "brand": "Brand"},
        color="price",
        color_continuous_scale="Oranges",
    )
    fig.update_layout(showlegend=False)
    return fig


def price_vs_rating(df):
    fig = px.scatter(
        df, x="price", y="rating",
        color="brand",
        hover_data=["title", "review_count"],
        title="Price vs Rating",
        labels={"price": "Price (₹)", "rating": "Rating"},
        color_discrete_sequence=COLORS,
        opacity=0.75,
    )
    return fig


def segment_donut(df):
    seg = df["price_segment"].value_counts().reset_index()
    seg.columns = ["segment", "count"]
    fig = px.pie(
        seg, values="count", names="segment",
        title="Market Segment Distribution",
        hole=0.45,
        color_discrete_sequence=px.colors.sequential.Oranges_r,
    )
    return fig


def brand_review_bubble(df):
    bd = df.groupby("brand").agg(
        avg_price=("price","mean"),
        avg_rating=("rating","mean"),
        total_reviews=("review_count","sum"),
        products=("asin","count"),
    ).reset_index()
    fig = px.scatter(
        bd, x="avg_price", y="avg_rating",
        size="total_reviews",
        color="brand",
        hover_data=["products","total_reviews"],
        title="Brand Landscape: Price vs Rating (size = reviews)",
        labels={"avg_price":"Avg Price (₹)","avg_rating":"Avg Rating"},
        color_discrete_sequence=COLORS,
    )
    return fig


def rating_dist(df):
    fig = px.histogram(
        df, x="rating", nbins=20,
        title="Rating Distribution",
        color_discrete_sequence=["#667eea"],
    )
    return fig


def top_value_products(df, n=10):
    top = df.nlargest(n, "value_score")[
        ["title","brand","price","rating","review_count","value_score"]
    ].copy()
    top["title_short"] = top["title"].str[:45] + "…"
    top["price_fmt"] = top["price"].apply(lambda x: f"₹{x:,.0f}")
    fig = px.bar(
        top, x="value_score", y="title_short",
        orientation="h",
        title=f"Top {n} Best Value Products",
        labels={"value_score":"Value Score","title_short":""},
        color="value_score",
        color_continuous_scale="Teal",
        hover_data=["brand","price_fmt","rating","review_count"],
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return fig


def category_specific_chart(df: pd.DataFrame) -> go.Figure | None:
    """
    Auto-detect a category-specific numeric column and plot it vs price.
    Returns None if nothing interesting found.
    """
    cat_cols = {
        "ram_gb":       ("RAM (GB)", "RAM vs Price"),
        "storage_gb":   ("Storage (GB)", "Storage vs Price"),
        "battery_mah":  ("Battery (mAh)", "Battery vs Price"),
        "screen_inch":  ("Screen (inch)", "Screen Size vs Price"),
        "capacity_l":   ("Capacity (L)", "Capacity vs Price"),
        "capacity_kg":  ("Capacity (Kg)", "Load Capacity vs Price"),
        "driver_mm":    ("Driver (mm)", "Driver Size vs Price"),
        "battery_hrs":  ("Battery Life (hrs)", "Battery Life vs Price"),
    }
    for col, (label, title) in cat_cols.items():
        if col in df.columns and df[col].notna().sum() > 3:
            sub = df[df[col].notna()]
            fig = px.scatter(
                sub, x=col, y="price",
                color="brand",
                hover_data=["title","rating"],
                title=title,
                labels={col: label, "price": "Price (₹)"},
                color_discrete_sequence=COLORS,
                opacity=0.75,
            )
            return fig
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg", width=120)
        st.title("Market Analyser")
        st.markdown("---")

        # Data source
        st.subheader("📂 Data Source")
        data_dir = st.text_input("Processed data folder", value="../data/processed")
        processed = find_processed_files(data_dir)

        if processed:
            selected_label = st.selectbox("Select dataset", list(processed.keys()))
            data_path = processed[selected_label]
        else:
            st.warning("No processed files found. Run pipeline.py first.")
            data_path = st.text_input("Or enter file path directly", value="")

        st.markdown("---")

        # Filters (populated after load)
        st.subheader("🔍 Filters")
        apply_filters = st.checkbox("Apply filters", value=False)

        st.markdown("---")

        # AI settings
        st.subheader("🤖 AI Insights")
        api_key = st.text_input(
            "Google Gemini API Key",
            type="password",
            value=os.environ.get("GOOGLE_API_KEY", ""),
            help="Get yours at https://aistudio.google.com/app/apikey",
        )

    if not data_path or not Path(data_path).exists():
        st.info("👈 Select or enter a processed dataset file to begin.")
        return

    # ── Load data ─────────────────────────────────────────────────────────
    df = load_data(data_path)
    product_name = Path(data_path).stem.replace("final_", "").replace("_", " ").title()

    st.title(f"📦 {product_name} — Market Analysis")
    st.caption(f"Data: {len(df)} products · {df['brand'].nunique()} brands · {data_path}")

    # ── Sidebar filters ───────────────────────────────────────────────────
    if apply_filters:
        with st.sidebar:
            brands = st.multiselect(
                "Brands", sorted(df["brand"].unique()),
                default=sorted(df["brand"].unique())[:10],
            )
            price_range = st.slider(
                "Price range (₹)",
                int(df["price"].min()), int(df["price"].max()),
                (int(df["price"].min()), int(df["price"].max())),
                step=1000,
            )
            min_rating = st.slider("Minimum rating", 1.0, 5.0, 3.0, 0.1)

        df = df[
            df["brand"].isin(brands) &
            df["price"].between(*price_range) &
            (df["rating"] >= min_rating)
        ]

    # ── KPI Row ───────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Products", f"{len(df):,}")
    with col2:
        st.metric("Avg Price", f"₹{df['price'].mean():,.0f}")
    with col3:
        st.metric("Avg Rating", f"{df['rating'].mean():.2f} ⭐")
    with col4:
        st.metric("Brands", df["brand"].nunique())
    with col5:
        best = df.loc[df["value_score"].idxmax()]
        st.metric("Best Value Brand", best["brand"])

    st.markdown("---")

    # ── Tab layout ────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", "🏷️ Brands", "💎 Value", "🔍 Products", "🤖 AI Insights"
    ])

    # ── TAB 1: Overview ───────────────────────────────────────────────────
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(price_histogram(df), width='stretch')
        with c2:
            st.plotly_chart(segment_donut(df), width='stretch')

        c3, c4 = st.columns(2)
        with c3:
            st.plotly_chart(price_vs_rating(df), width='stretch')
        with c4:
            st.plotly_chart(rating_dist(df), width='stretch')

        # Category-specific chart
        cat_fig = category_specific_chart(df)
        if cat_fig:
            st.plotly_chart(cat_fig, width='stretch')

    # ── TAB 2: Brands ─────────────────────────────────────────────────────
    with tab2:
        st.plotly_chart(brand_avg_price(df), width='stretch')
        st.plotly_chart(brand_review_bubble(df), width='stretch')

        st.subheader("Brand Summary Table")
        brand_table = df.groupby("brand").agg(
            products    = ("asin",         "count"),
            avg_price   = ("price",        "mean"),
            min_price   = ("price",        "min"),
            max_price   = ("price",        "max"),
            avg_rating  = ("rating",       "mean"),
            total_reviews=("review_count", "sum"),
        ).round(2).reset_index().sort_values("products", ascending=False)
        brand_table["avg_price"] = brand_table["avg_price"].apply(lambda x: f"₹{x:,.0f}")
        brand_table["min_price"] = brand_table["min_price"].apply(lambda x: f"₹{x:,.0f}")
        brand_table["max_price"] = brand_table["max_price"].apply(lambda x: f"₹{x:,.0f}")
        st.dataframe(brand_table, width='stretch')

    # ── TAB 3: Value ──────────────────────────────────────────────────────
    with tab3:
        n = st.slider("Top N products", 5, 20, 10)
        st.plotly_chart(top_value_products(df, n), width='stretch')

        st.subheader(f"Top {n} Best Value Products")
        top = df.nlargest(n, "value_score")[[
            "title","brand","price","rating","review_count","value_score","url"
        ]].copy()
        top["price"] = top["price"].apply(lambda x: f"₹{x:,.0f}")
        top["value_score"] = top["value_score"].round(4)
        top["title"] = top["title"].str[:60]
        st.dataframe(top, width='stretch')

        # Segment breakdown
        st.subheader("Segment Breakdown")
        seg_stats = df.groupby("price_segment", observed=True).agg(
            count      = ("asin",  "count"),
            avg_price  = ("price", "mean"),
            avg_rating = ("rating","mean"),
        ).round(2).reset_index()
        st.dataframe(seg_stats, width='stretch')

    # ── TAB 4: Products ───────────────────────────────────────────────────
    with tab4:
        st.subheader("Product Explorer")
        search = st.text_input("Search title / brand", "")
        sort_by = st.selectbox("Sort by", ["value_score","price","rating","review_count"])
        sort_asc = st.checkbox("Ascending", value=False)

        view_df = df.copy()
        if search:
            mask = (
                view_df["title"].str.contains(search, case=False, na=False) |
                view_df["brand"].str.contains(search, case=False, na=False)
            )
            view_df = view_df[mask]

        view_df = view_df.sort_values(sort_by, ascending=sort_asc)

        display_cols = ["title","brand","price","rating","review_count",
                        "price_segment","value_score","sold_by","availability"]
        display_cols = [c for c in display_cols if c in view_df.columns]

        st.caption(f"Showing {len(view_df)} products")
        st.dataframe(
            view_df[display_cols].head(100).assign(
                price=lambda d: d["price"].apply(lambda x: f"₹{x:,.0f}")
            ),
            width='stretch',
        )

        # Download button
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️  Download full dataset (CSV)",
            data=csv_bytes,
            file_name=f"{product_name.replace(' ','_')}_analysis.csv",
            mime="text/csv",
        )

    # ── TAB 5: AI Insights ────────────────────────────────────────────────
    with tab5:
        st.subheader("🤖 AI-Powered Market Insights")

        if not api_key:
            st.warning("Enter your Google Gemini API key in the sidebar to enable AI insights.")
        else:
            # Preset questions
            preset_questions = [
                "What are the key market trends and opportunities in this product category?",
                "Which brands offer the best value for money and why?",
                "What price segments are most competitive? Where are the gaps?",
                "What are the top 5 products I should recommend to a budget-conscious buyer?",
                "Which sellers dominate this market and what does that mean for buyers?",
                "What patterns do you see in ratings vs price?",
                "Custom question...",
            ]
            selected_q = st.selectbox("Quick questions", preset_questions)

            if selected_q == "Custom question...":
                question = st.text_area("Your question", placeholder="Ask anything about this market data...")
            else:
                question = selected_q

            if st.button("🔍 Get AI Analysis", type="primary"):
                with st.spinner("Analysing market data…"):
                    response = get_ai_insights(df, question, api_key)
                st.markdown(f'<div class="ai-box">\n\n{response}\n\n</div>', unsafe_allow_html=True)

            # Auto-insights section
            st.markdown("---")
            st.subheader("📌 Auto Insights")
            if st.button("Generate full market report"):
                with st.spinner("Generating report…"):
                    report_q = (
                        "Give me a comprehensive market analysis covering: "
                        "1) Market overview and size, "
                        "2) Brand competition analysis, "
                        "3) Price segment insights, "
                        "4) Best value recommendations, "
                        "5) Key market gaps or opportunities."
                    )
                    report = get_ai_insights(df, report_q, api_key)
                st.markdown(f'<div class="ai-box">\n\n{report}\n\n</div>', unsafe_allow_html=True)

            # Quick stats for AI context
            with st.expander("📊 Data summary sent to AI"):
                st.json({
                    "total_products": len(df),
                    "brands": df["brand"].value_counts().head(8).to_dict(),
                    "price_range": {"min": int(df["price"].min()), "max": int(df["price"].max())},
                    "avg_rating": round(df["rating"].mean(), 2),
                    "segments": df["price_segment"].value_counts().to_dict(),
                })


if __name__ == "__main__":
    main()
