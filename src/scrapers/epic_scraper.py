from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent

from bs4 import BeautifulSoup

from time import sleep
import random

import json

class EpicScraper:
    def __init__(self, url=None):
        if url is None:
            self.epic = (
                'https://www.epicgames.com/site/en-US/careers/jobs?'
                +'country=United%20Kingdom&department=Engineering'
                +'&keyword=machine%20learning&page=1'
            )
        else:
            self.epic = url
    
    def get_job_links(self, soup):
        relative_links = soup.select('a[href^="/site/en-US/careers/jobs/"]')
        job_links = ['https://epicgames.com' + j['href'] for j in relative_links]
        return job_links

    def get_job_details(self, driver):
        wait = WebDriverWait(driver, 10)
        content_intro = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div.content-intro')
            )
        )
        siblings = driver.find_elements(
            By.XPATH, "//div[@class='content-intro']/following-sibling::*"
        )
        all_elements = [content_intro] + siblings
        combined_text = '\n\n'.join(elem.text for elem in all_elements)
        
        return combined_text

    def get_driver(self):
        options = Options()
        ua = UserAgent()
        user_agent = ua.random
        options.add_argument(f'--user-agent={user_agent}')
        driver = webdriver.Chrome(options=options)
        return driver
    
    def scrape(self, search_n_pages, save_jobs_path):
        all_results = []
        # Currently only handles first page page
        driver = webdriver.Chrome()
        driver.get(self.epic)
        sleep(random.uniform(1.9, 2.1))
        
        summary_soup = BeautifulSoup(
            driver.page_source, 'html.parser'
        )
        job_links = self.get_job_links(summary_soup)

        for job_link in job_links:
            driver = self.get_driver()
            driver.get(job_link)
            sleep(random.uniform(1.9, 2.1))
            job_text = self.get_job_details(driver)
            data_dict = {
                'description': job_text
            }
            data_dict['share_link'] = job_link
            all_results.append(data_dict)

        save_jobs_path.write_text(json.dumps(all_results, indent=2))
                
        return all_results