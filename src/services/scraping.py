import datetime
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from config.settings import settings
from scrapers import google_scraper
from services import recorder


def normalize_url(url: str | None) -> str:
    """Removes tracking parameters so the local cache recognizes the job."""
    if not url:
        return ""

    parsed = urlparse(url)
    # Common tracking/referral parameters to strip
    junk_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "trk",
        "ref",
        "trackingId",
        "original_referer",
        "utm_term",
        "utm_content",
    }

    # Rebuild query string without the junk
    query_params = parse_qsl(parsed.query)
    clean_params = [(k, v) for k, v in query_params if k.lower() not in junk_params]

    # Construct clean URL
    clean_query = urlencode(clean_params)
    return urlunparse(parsed._replace(query=clean_query, fragment=""))


class JobScraper:
    def __init__(self):
        self.results_dir = settings.results_dir
        if not settings.demo_mode:
            self.results_dir.mkdir(exist_ok=True)

        # Initialize your scrapers
        self.providers = {
            "google": google_scraper.GoogleScraper(),
            # Add other scrapers here as you build them
        }

    def _get_saved_path(self, where: str, use_last_scrape: bool) -> Path:
        if use_last_scrape:
            job_paths = list(self.results_dir.glob(f"{where}_*.json"))
            if job_paths:
                return max(job_paths, key=lambda p: p.stat().st_ctime)

        # Human-readable but lexically sortable (== chronological) and FS-safe
        # (no colons). Ordering still relies on stat() mtime/ctime, not the name.
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.results_dir / f"{where}_{stamp}.json"

    def run(
        self,
        search_n_pages: int | None = None,
        use_last_scrape: bool | None = None,
        query: str | None = None,
        location: str | None = None,
    ) -> dict:
        """Main entry point for the scraping service."""
        if settings.demo_mode:
            # Replay recorded scrapes; no network, no keys
            return {
                where: {
                    "results": recorder.load_fixture(f"{where}_scrape"),
                    "path": recorder.fixture_path(f"{where}_scrape"),
                }
                for where in self.providers
            }

        use_last_scrape = (
            use_last_scrape if use_last_scrape is not None else settings.use_last_scrape
        )
        search_n_pages = search_n_pages or settings.default_search_pages

        scraping_results = {}

        for where, scraper_instance in self.providers.items():
            save_path = self._get_saved_path(where, use_last_scrape)

            if use_last_scrape and save_path.exists():
                results = json.loads(save_path.read_text())
            else:
                results = scraper_instance.scrape(search_n_pages, save_path, query, location)

            # NORMALIZE: Ensure every link in the results is clean for the cache
            for job in results:
                if "apply_options" in job and job["apply_options"]:
                    raw_link = job["apply_options"][0].get("link", "")
                    job["apply_options"][0]["link"] = normalize_url(raw_link)

            scraping_results[where] = {"results": results, "path": save_path}

        return scraping_results
