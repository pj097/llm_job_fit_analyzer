import streamlit as st
import ast
import ollama

from config.settings import settings
from services.scraping import JobScraper
from services.scoring import JobScorer 

def clean_list(value):
    if isinstance(value, list): return value
    if isinstance(value, str) and value.strip().startswith('['):
        try: return ast.literal_eval(value)
        except: return [value]
    return [value] if value and str(value).lower() != 'nan' else []

st.set_page_config(
    page_title="Vector Foundry | Analyzer",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("[ Vector_Pathfinder ]")
st.caption("SYSTEM_STATUS: ALL_SYSTEMS_OPERATIONAL // ARCHITECTURE: END_TO_END_DEPLOYMENT")

st.sidebar.header("⚙️ CORE_SETTINGS")

with st.sidebar.expander("🔍 DATA_ENGINE"):
    use_last_scrape = st.checkbox("Use last aggregation", value=settings.use_last_scrape)
    search_n_pages = st.slider("Search pages", 1, 20, settings.default_search_pages)

with st.sidebar.expander("💡 MODEL_GUIDE"):
    st.markdown("""
    **VRAM Optimizations:**
    * **4GB:** `gemma3:4b`
    * **12GB:** `gemma3:12b` / `mistral`
    * **24GB:** `llama3.3:70b`
    """)

with st.sidebar.expander("🧠 NEURAL_RUNTIME"):
    provider = st.selectbox("Provider", options=["ollama", "gemini"])
    
    if provider == "ollama":
        available_models = [m['model'] for m in ollama.list().get('models', [])]
        display_options = available_models if available_models else ["No models found"]
        model = st.selectbox("Model Selection", display_options, accept_new_options=True)

        if model not in available_models and model != "No models found":
            if st.button(f"Initialize {model}"):
                with st.status(f"Downloading...", expanded=True):
                    ollama.pull(model)
                st.rerun()
            st.stop()
        use_cache, use_batch, gemini_api_key = False, False, None
    else:
        model = st.sidebar.selectbox("Model", ["gemini-3-flash-preview"])
        gemini_api_key = st.text_input("API Key", type="password")
        use_cache = st.checkbox("Context Caching", value=True)
        use_batch = st.checkbox("Batch Mode", value=False)

    temperature = st.slider("Temperature", 0.0, 1.5, 0.1)

st.divider()
col1, col2 = st.columns(2)

scraper = JobScraper()
with col1:
    if st.button("AGGREGATE_DATA", width='stretch'):
        with st.spinner("QUERYING_REMOTE_SERVERS..."):
            st.session_state.scraping = scraper.run(search_n_pages=search_n_pages, use_last_scrape=use_last_scrape)
        st.success("Data aggregation complete")
with col2:
    if st.button("INITIALIZE_SCORING", width='stretch'):
        if "scraping" not in st.session_state:
            st.error("ERROR: NO_DATA_SOURCE_FOUND")
        else:
            progress = st.progress(0.0)
            scorer = JobScorer(provider=provider, model=model, temperature=temperature, api_key=gemini_api_key, use_cache=use_cache)
            
            with st.spinner("NEURAL_PROCESSING_IN_PROGRESS..."):
                results_df = scorer.score(st.session_state.scraping, use_batch=use_batch, progress_cb=lambda p: progress.progress(p))
                st.session_state.df = results_df
            progress.empty()

if "df" in st.session_state:
    df = st.session_state.df.copy()
    
    if "original_url" in df.columns:
        df = df.drop(columns=["original_url"])
    
    df_sorted = df.sort_values(by="overall_fit", ascending=False)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("TOTAL_ENTRIES", len(df))
    m2.metric("HIGH_MATCH", len(df[df["overall_fit"] >= 8]))
    m3.metric("AVG_SCORE", f"{df['overall_fit'].mean():.1f}")
    m4.metric("CORP_DIVERSITY", df["company"].nunique())

    st.subheader("[ HIGH_PRIORITY_MATCHES ]")
    
    st.dataframe(
        df_sorted,
        column_config={
            "overall_fit": st.column_config.ProgressColumn("MATCH_%", min_value=0, max_value=10, format="%d"),
            "job_url": st.column_config.LinkColumn("SOURCE_URL"),
            # --- TRUNCATION LOGIC ---
            "job_title": st.column_config.TextColumn("JOB_TITLE", width="medium"), 
            "company": st.column_config.TextColumn("COMPANY", width="small"),
            "salary": st.column_config.TextColumn("SALARY"),
        },
        width='stretch',
        hide_index=True
    )

    st.subheader("[ TECHNICAL_ANALYSIS_LOG ]")
    for _, row in df_sorted.head(5).iterrows():
        with st.expander(f"MATCH_{row['overall_fit']} // {row['job_title']} // {row['company']}"):
            st.markdown(f"**SUMMARY:** {row.get('triage_summary', 'N/A')}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### + TECHNICAL_PROS")
                for p in clean_list(row.get('technical_pros')): st.caption(f"MOD_PRM // {p}")
            with c2:
                st.markdown("### - RISK_FACTORS")
                for r in clean_list(row.get('risk_factors')): st.caption(f"MOD_WRN // {r}")