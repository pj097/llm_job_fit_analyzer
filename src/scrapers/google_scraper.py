import json
from time import sleep

from config.settings import settings


class GoogleScraper:
    def __init__(self):
        self.serpapi_key = settings.serpapi_key.get_secret_value() if settings.serpapi_key else None
        self.search_params = json.loads(settings.google_search_params)

    def scrape(self, search_n_pages, save_jobs_path, query=None, location=None):
        return self.serpapi_search(search_n_pages, save_jobs_path, query, location)

    def serpapi_search(self, search_n_pages, save_jobs_path, query=None, location=None):
        if not self.serpapi_key:
            raise RuntimeError(
                "SERPAPI_KEY is not configured. Set it in your .env to scrape Google Jobs."
            )

        # Work on a copy so UI overrides and pagination tokens don't leak into
        # the next run. The search line and location now come from the UI; the
        # rest (engine, hl, gl) stays in GOOGLE_SEARCH_PARAMS.
        search_params = dict(self.search_params)
        if query is not None:
            search_params["q"] = query
        if location is not None:
            search_params["location"] = location

        if not search_params.get("q"):
            raise RuntimeError("Search query is empty. Enter a job title or keywords to search.")

        # Imported lazily so the app can start without serpapi configured
        import serpapi

        client = serpapi.Client(api_key=self.serpapi_key)

        all_results = []

        # Cap at n-ish jobs (google decreases the return after 100-ish)
        for _ in range(search_n_pages):
            search_results = client.search(search_params)
            response = search_results.as_dict()

            if "jobs_results" not in response:
                error = response.get("error", "unknown error")
                if not all_results:
                    raise RuntimeError(f"SerpApi search failed: {error}")
                # Keep what we already fetched instead of losing the whole run
                print(f"Warning: stopping pagination early: {error}")
                break

            all_results.extend(response["jobs_results"])

            pagination = search_results.get("serpapi_pagination")
            if pagination is None:
                break
            search_params["next_page_token"] = pagination["next_page_token"]
            sleep(2)

        save_jobs_path.write_text(json.dumps(all_results, indent=2))

        # Record the search this scrape ran with, in a params/ sibling that the
        # `google_*.json` globs (scrape selection) deliberately won't match. The
        # demo recorder uses it to flag a fixture whose label disagrees with the
        # jobs it ships.
        params_path = save_jobs_path.parent / "params" / save_jobs_path.name
        params_path.parent.mkdir(parents=True, exist_ok=True)
        params_path.write_text(
            json.dumps(
                {"query": search_params.get("q"), "location": search_params.get("location")},
                indent=2,
            )
        )

        return all_results
