import streamlit as st
import ast

from config.settings import settings
from services.scraping import JobScraper
from services.scoring import JobScorer 

import ollama


def clean_list(value):
    """
    Safely converts string representations of lists (e.g., from CSV/JSON) 
    back into actual Python lists for the UI.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith('['):
        try:
            # Safely parse the string "[...]" into a list
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [value]
    return [value] if value and str(value).lower() != 'nan' else []

st.set_page_config(
    page_title=settings.app_name,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 LLM Job Fit Analyzer")
st.caption("Scrape, score, and triage jobs efficiently using local LLMs or Gemini 3.")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("⚙️ Settings")

# Scraping Section
with st.sidebar.expander("🔍 Scraping"):
    use_last_scrape = st.checkbox("Use last scrape", value=settings.use_last_scrape)
    search_n_pages = st.slider("Search pages", 1, 20, settings.default_search_pages)

# Add the Help Section
with st.sidebar.expander("💡 Which model should I choose?"):
    st.markdown("""
    **Match your GPU VRAM, e.g.:**
    * **4GB:** `gemma3:4b`
    * **6GB:** `llama3.1:8b`
    * **12GB:** `mistral-small`, `gemma2:9b`, `gemma3:12b-it-q4_K_M`
    * **24GB:** `llama3.3:70b` or `deepseek-v3`
    
    *Type any name from [ollama.com/library](https://ollama.com/library) to download it.*
    """
    )

# LLM Section
with st.sidebar.expander("🧠 Model"):
    provider = st.selectbox(
        "Provider",
        options=["ollama", "gemini"],
        index=0 if settings.default_provider == "ollama" else 1,
    )

    # Dynamic options based on provider
    if provider == "ollama":
        # 1. Fetch models with a safety fallback
        available_models = [m['model'] for m in ollama.list().get('models', [])]

        # 2. Handle the "Empty List" for the selectbox
        # If empty, we provide a dummy option so the selectbox doesn't crash
        display_options = available_models if available_models else ["No models found"]
        
        model = st.selectbox(
            "Choose or Type Model", 
            display_options,
            accept_new_options=True,
            index=0 if available_models else None,
            placeholder="Type a model to download..."
        )

        # 3. Download Logic
        if model not in available_models:
            if model and model != "No models found":
                st.warning(f"⚠️ {model} is not installed.")
                if st.button(f"Download {model}"):
                    with st.status(f"Downloading {model}...", expanded=True) as status:
                        ollama.pull(model)
                        status.update(label="Download Complete!", state="complete")
                    st.rerun()
            
            # 4. THE GRACEFUL PAUSE
            # If we reach here and the model is still not in the available list,
            # we stop the script so the rest of your app doesn't load.
            print("Please select or download a model to continue.")
            st.info("Please select or download a model to continue.")
            st.stop()

        # --- Rest of your app (Chat, API Keys, etc.) runs only if a model exists ---
        st.success(f"Successfully loaded {model}")
        gemini_api_key = None
        use_cache = False
        use_batch = False
    else:
        model = st.sidebar.selectbox("Model", ["gemini-3-flash-preview"], index=0)
        gemini_api_key = st.text_input(
            "Gemini API key",
            value=settings.gemini_api_key or "",
            type="password"
        )
        # Gemini 3 Specific Features
        st.sidebar.info("✨ Gemini 3 Features")
        use_cache = st.checkbox("Use Context Caching", value=True, help="Caches your profile to save 75% on tokens.")
        use_batch = st.checkbox("Use Batch Mode", value=False, help="Runs all jobs at once for 50% cost reduction. Results take ~1hr.")

    temperature = st.slider("Temperature", 0.0, 1.5, 0.1)

# Filters
with st.sidebar.expander("🚫 Filters"):
    exclude_title_keys = st.text_area(
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

if "scraping" in st.session_state and st.session_state.scraping:
    total_jobs = 0
    for where in st.session_state.scraping:
        total_jobs += st.session_state.scraping[where]['results'].shape[0]

    with st.sidebar:
        st.header("Session Stats")
        st.metric(label="Scraped Jobs", value=total_jobs)
        st.divider()
    

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

    # --- TOP METRICS ---
    cols = st.columns(4)
    with cols[0]:
        st.metric("Total Jobs Found", len(df))
    with cols[1]:
        high_fit = len(df[df["overall_fit"] >= 8])
        st.metric("High Fit (8+)", high_fit, delta=f"{high_fit} new")
    with cols[2]:
        avg_score = df["overall_fit"].mean()
        st.metric("Avg. Match Score", f"{avg_score:.1f}/10")
    with cols[3]:
        # Count unique companies to see market diversity
        st.metric("Unique Companies", df["company"].nunique())


    # --- ENHANCED DATAFRAME ---
    st.subheader("🚀 High-Priority Matches")

    # Configure specific columns for better UX
    config = {
        "job_title": st.column_config.TextColumn("Role", width="large", help="The title of the position"),
        "overall_fit": st.column_config.ProgressColumn(
            "Match Quality",
            help="LLM-derived fit score based on your RSE/HPC profile",
            min_value=0,
            max_value=10,
            format="%d/10"
        ),
        "company": st.column_config.TextColumn("Organization"),
        "job_url": st.column_config.LinkColumn("Apply", display_text="Open Job ↗"),
        "where": st.column_config.TextColumn("Platform", width="small"),
    }

    cols_at_front = ["job_title", "overall_fit", "company", "job_url"]
    all_cols = df.columns.tolist()
    remaining_cols = [c for c in all_cols if c not in cols_at_front]
    ordered_list = cols_at_front + remaining_cols

    # Hide internal columns that clutter the view (like IDs, raw JSON, etc)
    # This assumes you have columns like 'raw_reasoning' or 'id'
    display_df = df[ordered_list].copy()

    st.dataframe(
        display_df,
        column_config=config,
        width='stretch',
        hide_index=True,
        height=400
    )
    
    # --- LAYER 3: DEEP TRIAGE CARDS ---
    st.subheader("🔍 Technical Match Analysis")
    for i, row in df.head(5).iterrows():
        color = "green" if row['overall_fit'] >= 8 else "orange"
        with st.expander(f":{color}[**{row['overall_fit']}/10**] — **{row['job_title']}** ({row.get('engagement_type', 'N/A')})"):
            st.write(f"**The Gist:** {row.get('triage_summary', '...')}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("✅ **Technical Pros**")
                for p in clean_list(row.get('technical_pros')): st.caption(f"• {p}")
            with c2:
                st.markdown("⚠️ **Risks / Red Flags**")
                st.caption(row.get('red_flags', 'None identified'))
                for r in clean_list(row.get('risk_factors')): st.caption(f"• {r}")