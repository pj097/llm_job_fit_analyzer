import json
import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from scrapers import google_scraper
from config.settings import settings

class JobScraper:
    def __init__(self):
        self.results_dir = settings.results_dir
        self.results_dir.mkdir(exist_ok=True)
        
        # Initialize your scrapers
        self.providers = {
            "google": google_scraper.GoogleScraper(),
            # Add other scrapers here as you build them
        }

    def normalize_url(self, url: str) -> str:
        """Removes tracking parameters so the local cache recognizes the job."""
        if not url:
            return ""
        
        parsed = urlparse(url)
        # Common tracking/referral parameters to strip
        junk_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 
            'trk', 'ref', 'trackingId', 'original_referer',
            'utm_term', 'utm_content'
        }
        
        # Rebuild query string without the junk
        query_params = parse_qsl(parsed.query)
        clean_params = [(k, v) for k, v in query_params if k.lower() not in junk_params]
        
        # Construct clean URL
        clean_query = urlencode(clean_params)
        return urlunparse(parsed._replace(query=clean_query, fragment=''))

    def _get_saved_path(self, where: str, use_last_scrape: bool) -> Path:
        if use_last_scrape:
            job_paths = list(self.results_dir.glob(f"{where}_*.json"))
            if job_paths:
                return max(job_paths, key=lambda p: p.stat().st_ctime)

        now_ts = int(datetime.datetime.now().timestamp())
        return self.results_dir / f"{where}_{now_ts}.json"

    def run(self, search_n_pages: int = None, use_last_scrape: bool = None) -> dict:
        """Main entry point for the scraping service."""
        use_last_scrape = use_last_scrape if use_last_scrape is not None else settings.use_last_scrape
        search_n_pages = search_n_pages or settings.default_search_pages

        scraping_results = {}

        for where, scraper_instance in self.providers.items():
            save_path = self._get_saved_path(where, use_last_scrape)

            if use_last_scrape and save_path.exists():
                results = json.loads(save_path.read_text())
            else:
                results = scraper_instance.scrape(search_n_pages, save_path)

            # NORMALIZE: Ensure every link in the results is clean for the cache
            for job in results:
                if "apply_options" in job and job["apply_options"]:
                    raw_link = job["apply_options"][0].get("link", "")
                    job["apply_options"][0]["link"] = self.normalize_url(raw_link)

            scraping_results[where] = {
                "results": results,
                "path": save_path
            }

        return scraping_results