import json
import time
import pandas as pd
import re
from pathlib import Path
from typing import Callable, Optional

from llm.ollama import OllamaProvider
from llm.gemini import GeminiProvider
from config.settings import settings

class JobScorer:
    def __init__(
        self, 
        provider: str = None, 
        model: str = None, 
        temperature: float = None, 
        api_key: str = None,
        use_cache: bool = True
    ):
        self.provider_name = provider or settings.default_provider
        self.model_name = model or settings.default_model
        self.temp = temperature or settings.default_temperature
        self.api_key = api_key or settings.gemini_api_key
        
        # 1. Initialize LLM Provider
        if self.provider_name == "ollama":
            self.llm = OllamaProvider(model=self.model_name, temperature=self.temp)
        elif self.provider_name == "gemini":
            self.llm = GeminiProvider(model=self.model_name, api_key=self.api_key, temperature=self.temp)
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")

        # 2. Local Result Caching (Save Money)
        clean_model_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', self.model_name)
        cache_filename = f"scored_cache_{self.provider_name}_{clean_model_name}.json"
        
        # 2. SET THE PATH
        self.local_db_path = Path("data") / cache_filename
        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.scored_data = self._load_local_db()

        # 3. Server-side Context Caching (Speed & Token Discount)
        self.prompt_template = Path(settings.prompt_file).read_text()
        self.server_cache_name = None
        
        if use_cache and isinstance(self.llm, GeminiProvider):
            # Split template to get only instructions/profile (before the job variable)
            static_context = self.prompt_template.split("{{INSERT_JOB_ADVERT_HERE}}")[0]
    
            # Technical Note: Gemini's minimum for caching is 32,768 tokens 
            # for it to be active for billing, but you can create them smaller for testing.
            # len() is characters, so 2000 chars is roughly 500-700 tokens.
            if len(static_context) > 2000: 
                cache = genai.caching.CachedContent.create(
                    model='models/gemini-1.5-flash-001', # Use your specific model
                    display_name='job_evaluation_context',
                    contents=[static_context],
                    ttl=timedelta(minutes=60), # Cache expires after 1 hour
                )
                self.server_cache_name = cache.name

    def _load_local_db(self) -> dict:
        if self.local_db_path.exists():
            try:
                return json.loads(self.local_db_path.read_text())
            except:
                return {}
        return {}

    def _save_to_local_db(self):
        """Writes the entire current scored_data state to disk."""
        tmp_path = self.local_db_path.with_suffix('.tmp')
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                # We save the full internal dictionary, not a passed argument
                json.dump(self.scored_data, f, indent=4)
            tmp_path.replace(self.local_db_path)
        except Exception as e:
            print(f"Warning: Failed to save cache: {e}")

    def score(self, scraping: dict, use_batch: bool = False, progress_cb: Optional[Callable] = None) -> pd.DataFrame:
        final_results = []
        jobs_to_process = []
        gen_args = {"cache_name": self.server_cache_name} if self.server_cache_name else {}

        # Step 1: Filter using LOCAL CACHE
        for platform, scrape in scraping.items():
            for job in scrape.get("results", []):
                # Ensure we have a unique URL or ID
                url = job.get("job_url") or job.get("apply_options", [{}])[0].get("link")
                
                if url in self.scored_data:
                    cached_item = self.scored_data[url]
                    # FIX: Inject title from source if missing in old cache
                    if "job_title" not in cached_item:
                        cached_item["job_title"] = job.get("title") or job.get("job_title")
                    final_results.append(cached_item)
                else:
                    jobs_to_process.append({"job": job, "platform": platform, "url": url})

        if not jobs_to_process:
            return pd.DataFrame(final_results)

        # Step 2: Handle NEW jobs
        prompts = [self.prompt_template.replace("{{INSERT_JOB_ADVERT_HERE}}", json.dumps(item["job"])) 
                   for item in jobs_to_process]

        # (Batch logic remains here...)

        # WORKFLOW B: REAL-TIME (Synchronous)
        for i, prompt in enumerate(prompts):
            try:
                raw_json = self.llm.generate(prompt, **gen_args)
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
                
            except Exception as e:
                print(f"Error scoring {jobs_to_process[i]['url']}: {e}")

            if progress_cb:
                progress_cb((i + 1) / len(prompts))

        return pd.DataFrame(final_results)

    def check_batch_results(self, batch_id: str):
        """Polls Gemini to see if the batch is done and saves to local cache."""
        if not isinstance(self.llm, GeminiProvider):
            return None
            
        job = self.llm.client.batches.get(name=batch_id)
        if job.state.name == "JOB_STATE_SUCCEEDED":
            # Implementation for downloading and parsing results would go here
            # For now, we return the status
            return "SUCCEEDED"
        return job.state.name