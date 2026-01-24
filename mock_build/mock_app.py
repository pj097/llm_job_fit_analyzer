# Mock app for web bundling with stlite

import sys
import re
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock

# Create a "Black Hole" for the browser-breaking imports
# We put these in sys.modules BEFORE importing app.py
mock_names = [
    'ollama', 
    'services.scraping', 
    'services.scoring',
    'config.settings'
]

for name in mock_names:
    sys.modules[name] = MagicMock()

# Mock the settings object
sys.modules['config.settings'].settings.app_name = 'LLM Job Fit Analyzer (Demo)'
sys.modules['config.settings'].settings.exclude_title_keywords = []
sys.modules['config.settings'].settings.use_last_scrape = True
sys.modules['config.settings'].settings.default_search_pages = 10
sys.modules['config.settings'].settings.default_provider = 'ollama'
sys.modules['config.settings'].settings.gemini_api_key = 'a very secret key'

# Mock Ollama
mock_ollama = MagicMock()
# Simulate a list of models so the sidebar selectbox has options
mock_ollama.list.return_value = {
    'models': [
        # {'model': 'llama3.1:8b'}, 
        # {'model': 'qwen2_5_7b''},
        {'model': 'gemma3_12b-it-q4_K_M'}
    ]
}
sys.modules['ollama'] = mock_ollama

# Mock the scorer
mock_scoring_mod = MagicMock()
mock_scorer_inst = mock_scoring_mod.JobScorer.return_value

def load_demo_data():
    # This function is called when 'scorer.score()' is triggered
    df = pd.read_json(
        'demo_data.json',
        orient='index'
    )
    df = df.reset_index().rename(columns={'index': 'original_url'})
    return df

demo_df = load_demo_data()

mock_scorer_inst.score.return_value = demo_df
sys.modules['services.scoring'] = mock_scoring_mod

# Mock the scraper
mock_scraping_mod = MagicMock()
mock_scraper_inst = mock_scraping_mod.JobScraper.return_value

mock_results = MagicMock()
mock_results.shape = demo_df.shape

mock_scraper_inst.run.return_value = {
    'google': {
        'results': mock_results
    }
}
sys.modules['services.scraping'] = mock_scraping_mod


# Now import the real app
# Make it believe the lie above, and hopefully this import will succeed in the browser!
with open('app.py', 'r') as f:
    code = f.read()

# These replacements fix the "Version Gap" issues in stlite on-the-fly
def clean_code(text):
    # Fix Buttons
    text = re.sub(
        r"width\s*=\s*['\"]stretch['\"]", 
        "use_container_width=True", 
        text
    )
    
    # Remove problematic keywords (and the preceding comma/whitespace)
    keywords = [
        "accept_new_options",
        "color",
        "width",
        "height",
        "hide_index"
    ]
    for kw in keywords:
        # This regex looks for: 
        # 1. A comma 
        # 2. Any amount of whitespace/newlines (\s*)
        # 3. The keyword + equal sign + any value until the next comma or closing paren
        # Note: This is a simplified version for a demo environment
        pattern = rf",\s*{kw}\s*=\s*[^,)]+"
        text = re.sub(pattern, "", text)
    
    return text

stlite_compatible_code = clean_code(code)
exec(stlite_compatible_code, globals())