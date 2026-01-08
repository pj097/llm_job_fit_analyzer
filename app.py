import streamlit as st
import pandas as pd
import webbrowser
from time import sleep

from config.settings import settings
from services.scraping import JobScraper
from services.scoring import JobScorer 

st.set_page_config(
    page_title=settings.app_name,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 LLM Job Fit Analyzer")
st.caption("Scrape, score, and triage jobs efficiently using Gemini 3's advanced features.")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("⚙️ Settings")

# 1. Scraping Section
st.sidebar.subheader("🔍 Scraping")
use_last_scrape = st.sidebar.checkbox("Use last scrape", value=settings.use_last_scrape)
search_n_pages = st.sidebar.slider("Search pages", 1, 20, settings.default_search_pages)

# 2. LLM Section
st.sidebar.subheader("🧠 Model")
provider = st.sidebar.selectbox(
    "Provider",
    options=["ollama", "gemini"],
    index=0 if settings.default_provider == "ollama" else 1,
)

# Dynamic options based on provider
if provider == "ollama":
    model = st.sidebar.selectbox("Model", ["llama3.1:8b"], index=0)
    gemini_api_key = None
    use_cache = False
    use_batch = False
else:
    model = st.sidebar.selectbox("Model", ["gemini-3-flash-preview"], index=0)
    gemini_api_key = st.sidebar.text_input(
        "Gemini API key",
        value=settings.gemini_api_key or "",
        type="password"
    )
    # Gemini 3 Specific Features
    st.sidebar.info("✨ Gemini 3 Features")
    use_cache = st.sidebar.checkbox("Use Context Caching", value=True, help="Caches your profile to save 75% on tokens.")
    use_batch = st.sidebar.checkbox("Use Batch Mode", value=False, help="Runs all jobs at once for 50% cost reduction. Results take ~1hr.")

temperature = st.sidebar.slider("Temperature", 0.0, 1.5, 0.1)

# 3. Filters
st.sidebar.subheader("🚫 Filters")
exclude_title_keys = st.sidebar.text_area(
    "Exclude keywords", 
    value="\n".join(settings.exclude_title_keywords)
).splitlines()

# --- MAIN ACTION BUTTONS ---
col1, col2 = st.columns(2)

scraper = JobScraper()
with col1:
    if st.button("🔍 Scrape jobs", width='stretch'):
        with st.spinner("Scraping job adverts..."):
            st.session_state.scraping = scraper.run(
                search_n_pages=search_n_pages,
                use_last_scrape=use_last_scrape
            )
        st.success("Scraping complete")

with col2:
    if st.button("🧠 Score jobs", width='stretch'):
        if "scraping" not in st.session_state:
            st.error("Please scrape jobs first.")
        else:
            progress = st.progress(0.0)

            with st.spinner("Initializing Scorer & Context Cache..."):
                # Initialize the class (This sets up the cache if enabled)
                scorer = JobScorer(
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    api_key=gemini_api_key or None,
                    use_cache=use_cache
                )

            with st.spinner("Scoring jobs..."):
                results_df = scorer.score(
                    scraping=st.session_state.scraping,
                    use_batch=use_batch,
                    progress_cb=lambda p: progress.progress(p)
                )
                
                # Check if we triggered a Batch Job
                if "status" in results_df.columns and results_df.iloc[0]["status"] == "BATCH_SUBMITTED":
                    st.warning(f"🚀 Batch Job Submitted! ID: {results_df.iloc[0]['id']}. Check back in an hour.")
                    st.session_state.batch_active = True
                else:
                    st.session_state.df = results_df
                    st.success("Scoring complete")
            
            progress.empty()

# --- RESULTS DISPLAY ---
if "df" in st.session_state:
    df = st.session_state.df.copy()
    
    # Clean and sort
    for col in df.columns:
        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (dict, list)) else x)
    
    if "overall_fit" in df.columns:
        df = df.sort_values("overall_fit", ascending=False)

    # Filter keywords
    if exclude_title_keys:
        pattern = "|".join(k.lower() for k in exclude_title_keys if k.strip())

        df = df[~df["job_title"].str.lower().str.contains(pattern, na=False)]

    st.subheader("📊 Ranked Jobs")
    st.dataframe(df, width='stretch', height=600)

    # Browser Tool
    if not df.empty:
        st.divider()
        st.subheader("🌐 Action Center")
        n_open = st.number_input("Open top N jobs", 1, 50, 5)
        if st.button("Open in browser"):
            for link in df.head(n_open)["job_url"]:
                webbrowser.open_new_tab(link)
                sleep(0.5)