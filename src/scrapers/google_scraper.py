import serpapi
from pathlib import Path
import json

from time import sleep

from config.settings import settings

class GoogleScraper:
    def __init__(self):
        self.serpapi_key = settings.serpapi_key
        self.search_params = json.loads(settings.google_search_params)

    def scrape(self, search_n_pages, save_jobs_path):
        return self.serpapi_search(search_n_pages, save_jobs_path)

    def serpapi_search(self, search_n_pages, save_jobs_path):
        client = serpapi.Client(api_key=self.serpapi_key)
        
        all_results = []
    
        # Cap at n-ish jobs (google decreases the return after 100-ish)
        for i in range(search_n_pages):
            search_results = client.search(self.search_params)
            
            all_results.extend(
                search_results.as_dict()['jobs_results']
            )
    
            pagination = search_results.get('serpapi_pagination')
            
            if pagination is not None:
                self.search_params['next_page_token'] = pagination['next_page_token']
            else:
                break
            sleep(2)
            
        save_jobs_path.write_text(json.dumps(all_results, indent=2))
    
        return all_results