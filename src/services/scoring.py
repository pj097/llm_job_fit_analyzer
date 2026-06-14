import json
import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from config.settings import settings
from services import recorder
from services.scraping import normalize_url

# Appended to the (user-editable) prompt in code so the instructions the user
# sees stay free of machinery and there's no placeholder for them to delete.
JOB_ADVERT_BLOCK = "\n\n### Input Data\n<job_advert>\n{advert}\n</job_advert>"


def derive_job_url(job: dict) -> str:
    """Derives the normalized URL used as the cache key, or '' if none exists.

    Google Jobs results carry source_link (employer/job board) and
    share_link (Google, always present); prefer the most direct link.
    """
    apply_link = (job.get("apply_options") or [{}])[0].get("link")
    url = job.get("job_url") or apply_link or job.get("source_link") or job.get("share_link")
    return normalize_url(url)


class JobScorer:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
        prompt: str | None = None,
        query: str | None = None,
        location: str | None = None,
    ):
        self.demo_mode = settings.demo_mode

        if self.demo_mode:
            # Replay recorded scores only: no LLM provider, no prompt,
            # no live cache file
            self.llm = None
            raw = recorder.load_fixture("scored_jobs")
            if "_meta" in raw:
                self.fixture_meta = raw["_meta"]
                self.scored_data = raw.get("jobs", {})
            else:
                self.fixture_meta = {}
                self.scored_data = raw
            return

        self.provider_name = provider or settings.default_provider
        self.model_name = model or settings.default_model
        self.temp = temperature if temperature is not None else settings.default_temperature
        self.api_key = api_key or (
            settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
        )

        # 1. Initialize LLM Provider
        # Imported lazily so the unused provider's dependencies never load.
        if self.provider_name == "ollama":
            from llm.ollama import OllamaProvider

            self.llm = OllamaProvider(model=self.model_name, temperature=self.temp)
        elif self.provider_name == "gemini":
            from llm.gemini import GeminiProvider

            self.llm = GeminiProvider(
                model=self.model_name, api_key=self.api_key, temperature=self.temp
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")

        # 2. Local Result Caching (Save Money)
        clean_model_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", self.model_name)
        cache_filename = f"scored_cache_{self.provider_name}_{clean_model_name}.json"

        self.local_db_path = Path("data") / cache_filename
        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.scored_data = self._load_local_db()

        # UI-supplied prompt wins; fall back to the file default when absent
        # (e.g. headless runs).
        self.prompt_template = prompt or Path(settings.prompt_file).read_text()

        # The search line/location the user actually ran with. Recorded into the
        # cache _meta so the demo recorder can replay them as fixed inputs
        # instead of re-reading stale config.
        self.query = query
        self.location = location

    def _load_local_db(self) -> dict:
        if self.local_db_path.exists():
            try:
                raw = json.loads(self.local_db_path.read_text())
                if "_meta" in raw and "jobs" in raw:
                    return raw["jobs"]
                return raw
            except json.JSONDecodeError, OSError:
                return {}
        return {}

    def _save_to_local_db(self):
        """Writes the entire current scored_data state to disk."""
        tmp_path = self.local_db_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "_meta": {
                            "provider": self.provider_name,
                            "model": self.model_name,
                            "prompt": self.prompt_template,
                            "query": self.query,
                            "location": self.location,
                        },
                        "jobs": self.scored_data,
                    },
                    f,
                    indent=4,
                )
            tmp_path.replace(self.local_db_path)
        except Exception as e:
            print(f"Warning: Failed to save cache: {e}")

    def score(
        self,
        scraping: dict,
        progress_cb: Callable | None = None,
        result_cb: Callable | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> pd.DataFrame:
        final_results = []
        jobs_to_process = []

        # Case-insensitive title exclusions; drop jobs before they reach the
        # cache or the LLM so excluded titles never cost tokens.
        exclude = [k.lower() for k in (exclude_keywords or []) if k.strip()]

        # Step 1: Filter using LOCAL CACHE
        for platform, scrape in scraping.items():
            for job in scrape.get("results", []):
                title = job.get("title") or job.get("job_title") or ""
                if exclude and any(k in title.lower() for k in exclude):
                    print(f"Excluding job by title filter: {title}")
                    continue

                url = derive_job_url(job)

                if not url:
                    # No stable key to cache or link this job under
                    print(f"Skipping job without a URL: {job.get('title') or job.get('job_title')}")
                    continue

                if url in self.scored_data:
                    cached_item = self.scored_data[url]
                    # FIX: Inject title from source if missing in old cache
                    if "job_title" not in cached_item:
                        cached_item["job_title"] = job.get("title") or job.get("job_title")
                    cached_item.setdefault("job_url", url)
                    final_results.append(cached_item)
                    if result_cb:
                        result_cb(cached_item)
                elif self.demo_mode:
                    # Only recorded jobs can be shown in demo mode
                    print(f"Demo mode: no recorded score for {url}; dropping job")
                else:
                    jobs_to_process.append({"job": job, "platform": platform, "url": url})

        # Step 2: Handle NEW jobs
        if jobs_to_process:
            if not self.llm:
                raise RuntimeError("LLM provider is not initialized, cannot score new jobs.")

            prompts = [
                self.prompt_template + JOB_ADVERT_BLOCK.format(advert=json.dumps(item["job"]))
                for item in jobs_to_process
            ]

            for i, prompt in enumerate(prompts):
                try:
                    raw_json = self.llm.generate(prompt)
                    parsed = json.loads(raw_json)

                    # --- THE FIX: MANUAL METADATA INJECTION ---
                    original_job = jobs_to_process[i]["job"]

                    # Pull the title directly from the SCRAPED data, not the LLM
                    parsed["job_title"] = original_job.get("title") or original_job.get("job_title")
                    parsed["company"] = original_job.get("company") or parsed.get("company")
                    parsed["job_url"] = jobs_to_process[i]["url"]
                    parsed["where"] = jobs_to_process[i]["platform"]

                    # Update cache and results
                    self.scored_data[parsed["job_url"]] = parsed
                    self._save_to_local_db()

                    final_results.append(parsed)
                    if result_cb:
                        result_cb(parsed)

                except Exception as e:
                    print(f"Error scoring {jobs_to_process[i]['url']}: {e}")

                if progress_cb:
                    progress_cb((i + 1) / len(prompts))

        valid_results = []
        for item in final_results:
            if item.get("overall_fit") is None:
                print(
                    f"Dropping job with missing overall_fit: "
                    f"{item.get('job_title') or item.get('job_url')}"
                )
            else:
                valid_results.append(item)

        return pd.DataFrame(valid_results)
