import ast
import base64
import json
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

from config.settings import settings
from services import recorder
from services.scoring import JobScorer
from services.scraping import JobScraper

LOGO_PATH = Path(__file__).parent / "static" / "logo.svg"
FLOW_MMD = Path(__file__).parent / "static" / "flow.mmd"

st.set_page_config(
    page_title="Vector Foundry | Analyzer",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# One-paragraph plain-English summary, reused in the README. Deliberately
# generic (no provider names) so it stays accurate as scrapers/models change.
HOW_IT_WORKS = (
    "**Vector_Pathfinder** turns a wall of job adverts into a ranked shortlist. "
    "It fetches listings for your search, scores each one against a profile/prompt "
    "you control using a local or cloud LLM, and surfaces the best matches with a "
    "short technical analysis per role. Scores are cached locally so re-runs are "
    "instant, and a self-contained demo mode replays recorded data — no API keys "
    "or network required."
)


def _flow_html() -> str | None:
    """HTML that draws static/flow.mmd client-side via mermaid.js.

    Rendered live (no build step, no mermaid-cli/Chromium). The app applies NO
    styling: every colour, fill, and the transparent background come from the
    theme block in flow.mmd, which is the single source of truth. st.html can't
    run the script, so this is fed to components.html. None if the file is gone.
    """
    if not FLOW_MMD.exists():
        return None
    return f"""
    <div class="mermaid">{FLOW_MMD.read_text()}</div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true }});
    </script>
    """


@st.dialog("HOW_IT_WORKS", width="large")
def _flow_dialog() -> None:
    st.markdown(HOW_IT_WORKS)
    html = _flow_html()
    if html:
        components.html(html, height=640, scrolling=True)


def render_flow_diagram(height: int = 340) -> None:
    """Inline diagram plus an Expand button.

    Streamlit's native image fullscreen renders SVGs blank, so instead of that
    we draw the diagram live and offer a large st.dialog view via Expand.
    """
    html = _flow_html()
    if not html:
        return
    components.html(html, height=height, scrolling=True)
    if st.button("⛶  Expand diagram", width="stretch", key="flow_expand"):
        _flow_dialog()


def clean_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            return ast.literal_eval(value)
        except ValueError, SyntaxError:
            return [value]
    return [value] if value and str(value).lower() != "nan" else []


# The shortlist table shows these known columns first, in this order, skipping
# any the LLM omitted. Verbose fields get their own analysis-log section below,
# so they're kept out of the grid even though they're present in the data.
TABLE_PRIORITY_COLUMNS = [
    "overall_fit",
    "job_title",
    "company",
    "engagement_type",
    "salary",
    "job_url",
]
TABLE_EXCLUDED_COLUMNS = {
    "triage_summary",
    "technical_pros",
    "risk_factors",
    "red_flags",
    "where",
    "original_url",
}


def order_table_columns(available) -> list[str]:
    """Priority columns first (in fixed order), then any extra fields a custom
    prompt produced, appended in their existing order.

    Lets users surface their own JSON fields in the table just by adding them to
    the scoring prompt, without touching the app. The verbose/internal fields in
    TABLE_EXCLUDED_COLUMNS are never auto-appended.
    """
    available = list(available)
    priority = [c for c in TABLE_PRIORITY_COLUMNS if c in available]
    extras = [
        c
        for c in available
        if c not in TABLE_PRIORITY_COLUMNS and c not in TABLE_EXCLUDED_COLUMNS
    ]
    return priority + extras


def grad(text: str) -> str:
    """Wrap *text* in a sky-blue gradient span (left: sky-400 → right: sky-200).

    Safe to embed inside any ``st.*`` call that accepts
    ``unsafe_allow_html=True``.
    """
    return (
        f'<span style="'
        f"background: linear-gradient(90deg, #38bdf8, #7dd3fc);"
        f"-webkit-background-clip: text;"
        f"-webkit-text-fill-color: transparent;"
        f'background-clip: text;">'
        f"{text}</span>"
    )


@st.cache_data(show_spinner=False)
def fetch_locations(term: str, limit: int = 15) -> list[str]:
    """Return canonical SerpApi location names matching *term*.

    Uses SerpApi's public Locations API (no key required). Returns [] on any
    failure or empty term so the caller can fall back to free-text entry.
    """
    term = term.strip()
    if not term:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/locations.json",
            params={"q": term, "limit": limit},
            timeout=5,
        )
        resp.raise_for_status()
        return [loc["canonical_name"] for loc in resp.json() if loc.get("canonical_name")]
    except requests.RequestException, ValueError, KeyError:
        return []


# Global CSS: apply the sky-blue gradient to expander headers and button labels.
# These components don't accept unsafe_allow_html in their label args, so we
# target Streamlit's internal data-testid selectors instead.
_GRADIENT = "linear-gradient(90deg, #38bdf8, #7dd3fc)"
st.markdown(
    f"""
    <style>
    /* Expander toggle labels */
    [data-testid="stExpander"] summary p {{
        background: {_GRADIENT};
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    /* Primary and secondary button labels */
    [data-testid="stBaseButton-primary"] p,
    [data-testid="stBaseButton-secondary"] p {{
        background: {_GRADIENT};
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    /* Logo glow — matches website .animate-data + @keyframes data-pulse */
    @keyframes data-pulse {{
        0%, 100% {{
            filter: drop-shadow(0 0 2px #0ea5e9) drop-shadow(0 0 5px rgba(14, 165, 233, 0.3));
            opacity: 0.8;
        }}
        50% {{
            filter: drop-shadow(0 0 15px #0ea5e9) drop-shadow(0 0 30px rgba(14, 165, 233, 0.2));
            opacity: 1;
        }}
    }}
    .logo-glow {{
        animation: data-pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Load recording metadata so the demo UI can show provider, model, and fetch date.
if settings.demo_mode:
    try:
        _raw = recorder.load_fixture("scored_jobs")
    except FileNotFoundError:
        st.error(
            "DEMO_FIXTURE_MISSING // scored_jobs.json not found. Re-record with `scripts/record_demo.py`."
        )
        st.stop()
    _meta = _raw.get("_meta")
    if not _meta:
        st.error(
            "FIXTURE_METADATA_MISSING // scored_jobs.json has no _meta block. Re-record with `scripts/record_demo.py`."
        )
        st.stop()
    _demo_provider = _meta["provider"]
    _demo_model = _meta["model"]
    try:
        _demo_query = _meta["query"]
        _demo_location = _meta["location"]
        _demo_prompt = _meta["prompt"]
    except KeyError as e:
        st.error(
            f"FIXTURE_METADATA_INCOMPLETE // {e} missing from _meta. "
            "Re-record with `scripts/record_demo.py`."
        )
        st.stop()
    try:
        import datetime as _dt

        _demo_date = _dt.datetime.fromisoformat(_meta["recorded_at"]).strftime("%-d %b '%y")
    except (KeyError, ValueError, TypeError) as e:
        st.error(f"FIXTURE_DATE_INVALID // recorded_at could not be parsed: {e}")
        st.stop()
else:
    _demo_provider = _demo_model = _demo_date = None
    _demo_query = _demo_location = _demo_prompt = None

if LOGO_PATH.exists():
    _logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    st.sidebar.markdown(
        f'<a href="https://vectorfoundry.co.uk" target="_blank">'
        f'<img src="data:image/svg+xml;base64,{_logo_b64}" width="100"'
        f' class="logo-glow" style="transform: scaleX(-1);"/>'
        f'</a>',
        unsafe_allow_html=True,
    )

st.markdown(f"# <span style='color:#38bdf8;opacity:0.8;'>[</span> {grad('Vector_Pathfinder')} <span style='color:#38bdf8;opacity:0.8;'>]</span>", unsafe_allow_html=True)
if settings.demo_mode:
    st.caption(
        f"System_Status: {grad('Demo_Mode')} // Data_Source: recorded_fixtures",
        unsafe_allow_html=True,
    )
    st.info(
        f"**DEMO_MODE** // This is a recorded demonstration: the job listings were fetched "
        f"on {_demo_date}; the fit analyses are curated sample output. "
        f"Live fetching and LLM scoring are disabled."
    )
else:
    st.caption(
        f"System_Status: {grad('All_Systems_Operational')} // Architecture: End_To_End_Deployment",
        unsafe_allow_html=True,
    )

with st.sidebar.expander("HOW_IT_WORKS"):
    st.markdown(HOW_IT_WORKS)
    render_flow_diagram()

st.sidebar.markdown(f"### {grad('CORE_SETTINGS')}", unsafe_allow_html=True)

with st.sidebar.expander("DATA_ENGINE"):
    use_last_scrape = st.checkbox(
        "Use last aggregation",
        value=True if settings.demo_mode else settings.use_last_scrape,
        disabled=settings.demo_mode,
        help="Re-use the most recent job listings already on disk instead of running a new search.",
    )
    search_n_pages = st.slider(
        "Search pages",
        1,
        20,
        settings.default_search_pages,
        disabled=settings.demo_mode,
        help="How many pages of results to fetch per search query. More pages = more jobs, but slower.",
    )

    if settings.demo_mode:
        st.text_input("Search query", value=_demo_query, disabled=True)
        st.text_input("Location", value=_demo_location, disabled=True)
        st.text_input("Exclude title keywords", value="", disabled=True)
        search_query = search_location = None
        exclude_keywords = None
    else:
        try:
            _params = json.loads(settings.google_search_params)
        except json.JSONDecodeError:
            _params = {}
        default_query = _params.get("q") or "Machine Learning"
        default_location = _params.get("location") or "London,England,United Kingdom"

        search_query = st.text_input(
            "Search query",
            value=default_query,
            help="The job title or keywords to search Google Jobs for.",
        )

        # Location typeahead: the google_jobs engine only accepts canonical
        # location strings, so resolve the user's term against SerpApi's public
        # Locations API and let them pick a valid match instead of free-typing.
        loc_term = st.text_input(
            "Location",
            value=default_location.split(",")[0],
            help="Type a city or region and press Enter, then pick the official "
            "match below. The list only refreshes once you commit the field.",
        )
        loc_matches = fetch_locations(loc_term)
        if loc_matches:
            search_location = st.selectbox(
                "Matched location",
                loc_matches,
                help="Official SerpApi locations for your term, most populous first.",
            )
        else:
            if loc_term.strip():
                st.caption("LOCATION_LOOKUP_UNAVAILABLE // sending your text as-is")
            search_location = loc_term.strip() or None

        exclude_raw = st.text_input(
            "Exclude title keywords",
            value="",
            help="Comma-separated. Jobs whose title contains any of these are "
            "dropped before scoring (case-insensitive).",
        )
        exclude_keywords = [k.strip() for k in exclude_raw.split(",") if k.strip()]

with st.sidebar.expander("MODEL_GUIDE"):
    st.markdown("""
    **Local — VRAM guide:**
    * **4GB:** `qwen3.5:2b`
    * **12GB:** `gemma4:12b`
    * **24GB:** `qwen3.6:27b`

    **Cloud providers:**
    Queries are sent to your provider's servers. Results are only saved locally on your machine — nothing is saved in demo mode.
    """)

with st.sidebar.expander("NEURAL_RUNTIME"):
    if settings.demo_mode:
        st.text_input("Endpoint", value=_demo_provider, disabled=True)
        st.selectbox("Model", options=[_demo_model], disabled=True)
        st.slider("Temperature", 0.0, 1.5, 0.1, disabled=True)
        model = api_key = temperature = None
    else:
        from llm.openai_compat import list_models

        # One OpenAI-compatible endpoint (LLM_BASE_URL): llama.cpp/llama-swap, Ollama,
        # or any cloud API. Switching engine is config, not a provider toggle.
        st.caption(f"Endpoint: {settings.llm_base_url}")
        api_key = (
            st.text_input(
                "API Key",
                type="password",
                help="Blank uses LLM_API_KEY from the environment (or none for local servers).",
            )
            or None
        )
        key = api_key or (
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        )

        # /v1/models lists what the endpoint actually serves, so the picker mirrors
        # the catalogue uniformly (llama-swap's config.yaml, Ollama's installs, ...).
        try:
            available_models = list_models(settings.llm_base_url, key)
        except Exception as e:
            st.warning(f"LLM_OFFLINE // {e}")
            available_models = []

        if available_models:
            model = st.selectbox(
                "Model",
                available_models,
                accept_new_options=True,
                help="Models served at the endpoint (/v1/models). Type one to override.",
            )
        else:
            # Endpoint unreachable — free text so the sidebar still works offline.
            model = st.text_input("Model", value=settings.llm_model)

        temperature = st.slider("Temperature", 0.0, 1.5, settings.default_temperature)

with st.sidebar.expander("ANALYSIS_PROMPT"):
    if settings.demo_mode:
        # The uploader is shown but inert so the demo UI matches the live one.
        st.file_uploader("Load prompt from .txt", type=["txt"], disabled=True)
        st.text_area("Scoring prompt", value=_demo_prompt, height=300, disabled=True)
        prompt = None
    else:
        prompt_path = Path(settings.prompt_file)
        default_prompt = prompt_path.read_text() if prompt_path.exists() else ""

        # Seed the editable area once; after that the widget owns its state via
        # the key, so user edits and re-runs don't clobber each other.
        if "prompt_text" not in st.session_state:
            st.session_state["prompt_text"] = default_prompt

        # Uploading a .txt populates the box but leaves it editable. Only apply a
        # file the first time we see it (name+size signature) so it doesn't
        # overwrite later manual edits on every rerun.
        uploaded = st.file_uploader(
            "Load prompt from .txt",
            type=["txt"],
            help="Optional: fill the prompt below from a text file. You can still edit it after.",
        )
        if uploaded is not None:
            sig = (uploaded.name, uploaded.size)
            if st.session_state.get("_prompt_file_sig") != sig:
                st.session_state["prompt_text"] = uploaded.getvalue().decode("utf-8")
                st.session_state["_prompt_file_sig"] = sig

        prompt = st.text_area(
            "Scoring prompt",
            key="prompt_text",
            height=300,
            help="Instructions sent to the model. The job advert is appended automatically.",
        )

st.divider()
col1, col2 = st.columns(2)

scraper = JobScraper()
with col1:
    if st.button("AGGREGATE_DATA", width="stretch"):
        try:
            with st.spinner("QUERYING_REMOTE_SERVERS..."):
                st.session_state.scraping = scraper.run(
                    search_n_pages=search_n_pages,
                    use_last_scrape=use_last_scrape,
                    query=search_query,
                    location=search_location,
                )
            st.success("Data aggregation complete")
        except (RuntimeError, FileNotFoundError) as e:
            st.error(f"SCRAPE_FAILED // {e}")
with col2:
    if st.button("INITIALIZE_SCORING", width="stretch"):
        if "scraping" not in st.session_state:
            st.error("ERROR: NO_DATA_SOURCE_FOUND")
        else:
            try:
                progress = st.progress(0.0)
                best_box = st.empty()
                # Stream the leading match as scoring proceeds instead of
                # leaving the user staring at a bare progress bar.
                best = {"fit": -1}

                def show_best(result):
                    fit = result.get("overall_fit") or 0
                    if fit <= best["fit"]:
                        return
                    best["fit"] = fit
                    best_box.success(
                        f"CURRENT_BEST // MATCH_{fit} // "
                        f"{result.get('job_title', '?')} @ {result.get('company', '?')}"
                    )

                scorer = JobScorer(
                    model=model,
                    temperature=temperature,
                    api_key=api_key,
                    prompt=prompt,
                    query=search_query,
                    location=search_location,
                )

                with st.spinner("NEURAL_PROCESSING_IN_PROGRESS..."):
                    results_df = scorer.score(
                        st.session_state.scraping,
                        progress_cb=lambda p: progress.progress(p),
                        result_cb=show_best,
                        exclude_keywords=exclude_keywords,
                    )
                    st.session_state.df = results_df
                progress.empty()
                best_box.empty()
            except (RuntimeError, FileNotFoundError, ValueError) as e:
                st.error(f"SCORING_FAILED // {e}")

if "df" in st.session_state:
    df = st.session_state.df.copy()

    if "original_url" in df.columns:
        df = df.drop(columns=["original_url"])

    df_sorted = df.sort_values(by="overall_fit", ascending=False)

    scored = df_sorted.dropna(subset=["overall_fit"])

    # The table is a scannable shortlist, not a data dump: known columns come
    # first and any the LLM omitted are skipped, while extra fields from a custom
    # prompt are appended after them (see order_table_columns).
    table_df = df_sorted[order_table_columns(df_sorted.columns)]

    # All rendered results live in one keyed container so tooling (e.g. the demo
    # screenshot script) can target the whole block via the `.st-key-results`
    # class Streamlit emits for a keyed container.
    with st.container(key="results"):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("TOTAL_ENTRIES", int(len(df)))
        m2.metric("HIGH_MATCH", int(len(scored[scored["overall_fit"] >= 8])))
        m3.metric("AVG_SCORE", f"{scored['overall_fit'].mean():.1f}" if len(scored) else "—")
        m4.metric("CORP_DIVERSITY", int(df["company"].nunique()))

        st.markdown(f"### <span style='color:#38bdf8;opacity:0.8;'>[</span> {grad('HIGH_PRIORITY_MATCHES')} <span style='color:#38bdf8;opacity:0.8;'>]</span>", unsafe_allow_html=True)

        st.dataframe(
            table_df,
            column_config={
                "overall_fit": st.column_config.ProgressColumn(
                    "MATCH_/10", min_value=0, max_value=10, format="%d"
                ),
                "job_url": st.column_config.LinkColumn("SOURCE_URL"),
                "job_title": st.column_config.TextColumn("JOB_TITLE", width="medium"),
                "company": st.column_config.TextColumn("COMPANY", width="small"),
                "engagement_type": st.column_config.TextColumn("ENGAGEMENT"),
                "salary": st.column_config.TextColumn("SALARY"),
            },
            width="stretch",
            hide_index=True,
        )

        st.markdown(f"### <span style='color:#38bdf8;opacity:0.8;'>[</span> {grad('TECHNICAL_ANALYSIS_LOG')} <span style='color:#38bdf8;opacity:0.8;'>]</span>", unsafe_allow_html=True)
        for _, row in df_sorted.head(5).iterrows():
            with st.expander(
                f"MATCH_{row['overall_fit']} // {row['job_title']} // {row['company']}"
            ):
                st.markdown(f"**SUMMARY:** {row.get('triage_summary', 'N/A')}")

                # Only rendered when the prompt actually produced a red_flags value,
                # so prompts that omit the field show nothing here.
                red_flags = row.get("red_flags")
                if red_flags is not None and str(red_flags).strip().lower() not in (
                    "",
                    "nan",
                    "none",
                ):
                    st.markdown(f"**{grad('RED_FLAGS')}:** {red_flags}", unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"### {grad('+ TECHNICAL_PROS')}", unsafe_allow_html=True)
                    for p in clean_list(row.get("technical_pros")):
                        st.caption(p)
                with c2:
                    st.markdown(f"### {grad('- RISK_FACTORS')}", unsafe_allow_html=True)
                    for r in clean_list(row.get("risk_factors")):
                        st.caption(r)
