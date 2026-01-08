# LLM Job Fit Analyzer

An intelligent job search assistant that scrapes job advertisements and uses **LLMs (Gemini & Ollama)** to score them against your unique career profile. It features local caching to save costs and an incremental-save mechanism to prevent data loss.



## Features
- **Hybrid LLM Support:** Seamlessly switch between local models (Ollama) and high-performance cloud models (Gemini 3).
- **Smart Caching:** Local JSON caching avoids re-scoring jobs you've already analyzed (0ms latency for known jobs).
- **URL Normalization:** Automatically strips tracking junk (UTM tags, trk IDs) to ensure stable cache hits.
- **Incremental Saving:** Updates your local database after *every* successful score to protect against crashes.
- **Batch Processing:** Support for Gemini API Batch mode to process large volumes at 50% cost.

---

## Installation & Setup

This project uses [uv](https://docs.astral.sh/uv/), an extremely fast Python package manager.

### 1. Prerequisites
- **Python 3.12+**
- **Ollama** (if running models locally)
- **SerpApi Key** (for Google Jobs scraping)
- **Gemini API key** (for Gemini 3.0+)

# Install dependencies and create virtual environment automatically
uv sync

# Use 'uv run' to execute the app locally within the managed environment
uv run streamlit run app.py --server.headless true --server.address=127.0.0.1

### `.env` Template

```bash
# --- General Settings ---
DEBUG=false
# Path to your prompt
PROMPT_FILE=.prompt.txt

# --- LLM Provider Configuration ---
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b
DEFAULT_TEMPERATURE=1.0
MAX_ATTEMPTS=5

# Gemini Settings (Cloud)
# Get your key at: https://aistudio.google.com/
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_DEFAULT_MODEL=gemini-3-flash-preview

# --- Scraping Configuration ---
# Get your key at: https://serpapi.com/
SERPAPI_KEY=YOUR_SERP_API_KEY_HERE
DEFAULT_SEARCH_PAGES=10
USE_LAST_SCRAPE=true

# Search Query Configuration (JSON format)
# Example: GOOGLE_SEARCH_PARAMS='{"engine": "google_jobs", "location": "London,England,United Kingdom", "hl": "en", "gl": "uk", "q": "Electrical Engineer"}'
GOOGLE_SEARCH_PARAMS='{"engine": "google_jobs", "location": "YOUR LOCATION HERE", "hl": "en", "gl": "YOUR DOMAIN HERE", "q": "YOUR JOB QUERY HERE"}'

# --- Filtering ---
EXCLUDE_TITLE_KEYWORDS=["french maid", "soulless executive"]
```

## Scoring Logic (Example Prompt)

The system uses a highly structured prompt located in `.prompt.txt`. This file defines your "Digital Recruiter" persona and your technical requirements. Below is the standard template used for evaluating Scientific Computing and ML roles:

### Example `.prompt.txt` (replace [PLACEHOLDER] brackets with your preferences)
> **Note:** The `{{INSERT_JOB_ADVERT_HERE}}` placeholder is automatically populated by the app during the scoring loop.

```markdown
### System Role
You are an expert technical recruiter specializing in [TARGET_INDUSTRY] and [SPECIFIC_DOMAIN] Engineering. Your task is to evaluate a provided job advertisement against a standardized candidate profile.

### Candidate Profile (Anonymized)
- **Primary Domain:** [CORE_DOMAIN_1], [CORE_DOMAIN_2], and high-scale system design.
- **Interests:** Applied research, operationalization, and [NICHE_INTEREST].
- **Values:** Engineering excellence, reproducibility, and end-to-end deployment (not just R&D).
- **Core Skills:** [LANGUAGE_1], [LANGUAGE_2], [FRAMEWORK_1], [CLOUD_INFRA], and large-scale data pipelines.
- **Culture:** Collaborative environments with opportunities for mentoring and technical leadership.
- **Ethics:** Strong focus on data privacy and the responsible handling of sensitive information.

### Evaluation Protocol
1. **Analyze:** Evaluate the job's technical stack, daily responsibilities, and company values against the profile.
2. **Score:** Assign 0–10 for each field based on strict alignment.
3. **Identify:** Detect "red flags" (e.g., "legacy maintenance only" or "non-technical focus").
4. **Format:** Output the result as a single, minified JSON object.

### Constraints
- If "Salary" is not explicitly stated, return `null`.
- The "Summary" must be 1–2 concise sentences.
- Use internal reasoning to ensure scores are non-inflated.
- OUTPUT ONLY COMPACT JSON. NO MARKDOWN. NO PREAMBLE.

### JSON Schema
{
  "job_title": string,
  "company": string,
  "salary": number | null,
  "overall_fit": integer,
  "technical_alignment": integer,
  "ml_engineering": integer,
  "scientific_relevance": integer,
  "tools_match": integer,
  "professional_influence": integer,
  "red_flags": string,
  "summary": string
}

### Input Data
<job_advert>
{{INSERT_JOB_ADVERT_HERE}}
</job_advert>