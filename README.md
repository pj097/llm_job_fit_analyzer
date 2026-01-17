# LLM Job Fit Analyzer

An intelligent job search assistant that scrapes job advertisements and uses **LLMs (Gemini & Ollama)** to score them against your unique career profile. It features local caching to save costs and an incremental-save mechanism to prevent data loss.

Why I have created this tool:

Tired of reading job descriptions that feel like a recipe blog post. We’ve all seen them: the job ads that spend ten paragraphs detailing the company’s "inspirational founding story" and the CEO's self-discovery trip to Peru before finally mentioning they need a Java dev. If you’re tired of hunting for actual technical requirements through a forest of corporate buzzwords, or companies that can't even describe what they need, this tool might be for you.

What this isn't intended for:

To entirely automate the job search process. This tool is intended to shortlist job listings, with the user making the final selection and applying for the job themselves.

## Features
- **Hybrid LLM Support:** Switch between local models (Ollama) and high-performance cloud models (Gemini 3).
- **Smart Caching:** Local JSON caching avoids re-scoring jobs you've already analyzed (0ms latency for known jobs).
- **URL Normalization:** Automatically strips tracking junk (UTM tags, trk IDs) to ensure stable cache hits.
- **Incremental Saving:** Updates your local database after *every* successful score to protect against crashes.
- **Batch Processing:** Support for Gemini API Batch mode to process large volumes at 50% cost.

---

## Installation & Setup

This project uses [uv](https://docs.astral.sh/uv/)

### 1. Prerequisites
- **Python 3.12+**
- **Ollama** (if running models locally)
- **SerpApi Key** (for Google Jobs scraping)
- **Gemini API key** (for Gemini 3.0+)

# Install dependencies and create virtual environment automatically
uv sync

# Use 'uv run' to execute the app locally within the managed environment
uv run streamlit run app.py --server.headless true --server.address=127.0.0.6

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

The system uses a highly structured prompt located in `.prompt.txt`. This file defines your "Digital Recruiter" persona and your technical requirements. Below is the standard template used for evaluating the roles (JSON Schema keys are required unless app.py is updated):

### Example `.prompt.txt` (replace [PLACEHOLDER] brackets with your preferences)
> **Note:** The `{{INSERT_JOB_ADVERT_HERE}}` placeholder is automatically populated by the app during the scoring loop.

```markdown
### System Role
You are a Lead Technical Headhunter specializing in [YOUR_FIELDS_OF_CHOICE_HERE]. Evaluate the job advert strictly against the provided profile.

### Candidate Profile
- Core: [YOUR_CORE].
- Expertise: [YOUR_EXPERTIZE].
- Philosophy: [YOUR_PHILOSOPHY]. 
- Domain: [YOUR_DOMAINS].
- Preferable: [YOUR_PREFERENCES].

### Evaluation Protocol
1.  Assign "overall_fit" (0–10). [SOMETHING_TERRIBLE] role is a 2. [SOMETHING_GREAT] is a 10.
2.  Determine "engagement_type" (Contract, FTC, or Permanent).
3.  Extract 3 "technical_pros" (e.g., [LIST_PROS]).
4.  Identify 3 "risk_factors" (e.g., [LIST_RISK_FACTORS]).

### JSON Schema
{
  "job_title": string,
  "company": string,
  "salary": number | null,
  "overall_fit": integer,
  "engagement_type": string,
  "triage_summary": string,
  "technical_pros": [string],
  "risk_factors": [string],
  "red_flags": string
}

### Constraints
- "triage_summary" must be exactly 2 sentences: 1) The technical "core" of the job. 2) Why it specifically fits/misses your niche.
- OUTPUT ONLY COMPACT JSON. NO MARKDOWN. NO PREAMBLE.

### Input Data
<job_advert>
{{INSERT_JOB_ADVERT_HERE}}
</job_advert>

### Further Work

Possibly more scrapers, though unlikely as Google does a decent job and scraping generally takes too much time and effort to maintain. 

Support for adding more LLMs. Currently this only uses a LLama model, but modifying this should be simple. 
Currently I would suggest grabbing the $300 in credits from Gemini as that will beat any local LLM for this task.