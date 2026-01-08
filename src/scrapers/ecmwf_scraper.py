from selenium import webdriver

from bs4 import BeautifulSoup

from time import sleep

import json

class ECMWFScraper:
    def __init__(self):
        self.ecmwf_url = 'https://jobs.ecmwf.int/Home/Job'
    
    def get_job_links(self, soup):
        job_links = []
        job_relative_links = soup.select('a.mb-15')
        
        for a in job_relative_links:
            url = 'https://jobs.ecmwf.int' + a['href']
            job_links.append(url)
            
        return job_links
    
    def scrape(self, search_n_pages, save_jobs_path):
        all_results = []
        # Currently only handles first page page
        for _ in range(1):
            driver = webdriver.Chrome()
            driver.get(self.ecmwf_url)
            summary_soup = BeautifulSoup(
                driver.page_source, 'html.parser'
            )
            job_links = self.get_job_links(summary_soup)

            for job_link in job_links:
                sleep(1)
                
                driver.get(job_link)
                details_soup = BeautifulSoup(
                    driver.page_source, 'html.parser'
                )
                script = details_soup.find(
                    'script', {'type': 'application/ld+json'}
                )
                data_dict = json.loads(script.string)
                
                data_dict['share_link'] = data_dict['url']
                all_results.append(data_dict)

        save_jobs_path.write_text(json.dumps(all_results, indent=2))
                
        return all_results