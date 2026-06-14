import json
import sys

import pytest
from pydantic import SecretStr

from scrapers.google_scraper import GoogleScraper
from services.scraping import JobScraper


def test_google_scraper_init(mocker):
    mocker.patch("config.settings.settings.google_search_params", '{"q": "developer"}')
    mocker.patch("config.settings.settings.serpapi_key", SecretStr("fake-key"))

    scraper = GoogleScraper()
    assert scraper.search_params["q"] == "developer"
    assert scraper.serpapi_key == "fake-key"


def test_google_scraper_run_success(mocker, tmp_path):
    mock_client = mocker.Mock()
    mock_search_results = mocker.Mock()

    mock_search_results.as_dict.return_value = {
        "jobs_results": [{"title": "Dev 1", "job_id": "1"}, {"title": "Dev 2", "job_id": "2"}],
        "serpapi_pagination": {"next_page_token": "token123"},
    }
    mock_search_results.get.return_value = {"next_page_token": "token123"}
    mock_client.search.return_value = mock_search_results

    mock_serpapi = mocker.MagicMock()
    mock_serpapi.Client.return_value = mock_client
    mocker.patch.dict(sys.modules, {"serpapi": mock_serpapi})

    mocker.patch("scrapers.google_scraper.sleep")

    scraper = GoogleScraper()
    scraper.search_params = {"q": "test"}
    scraper.serpapi_key = "fake"

    save_path = tmp_path / "test.json"
    results = scraper.scrape(search_n_pages=1, save_jobs_path=save_path)

    assert len(results) == 2
    assert results[0]["title"] == "Dev 1"


def test_google_scraper_writes_search_params_sidecar(mocker, tmp_path):
    mock_client = mocker.Mock()
    mock_search_results = mocker.Mock()
    mock_search_results.as_dict.return_value = {"jobs_results": [{"title": "Dev", "job_id": "1"}]}
    mock_search_results.get.return_value = None  # no pagination -> stop after one page
    mock_client.search.return_value = mock_search_results

    mock_serpapi = mocker.MagicMock()
    mock_serpapi.Client.return_value = mock_client
    mocker.patch.dict(sys.modules, {"serpapi": mock_serpapi})

    scraper = GoogleScraper()
    scraper.search_params = {"engine": "google_jobs"}
    scraper.serpapi_key = "fake"

    save_path = tmp_path / "google_20260614-084130.json"
    scraper.scrape(
        search_n_pages=1, save_jobs_path=save_path, query="ML Engineer", location="Paris,France"
    )

    # Sidecar lives under params/ so the google_*.json scrape globs skip it.
    sidecar = save_path.parent / "params" / save_path.name
    assert sidecar.exists()
    assert list(save_path.parent.glob("google_*.json")) == [save_path]
    params = json.loads(sidecar.read_text())
    assert params == {"query": "ML Engineer", "location": "Paris,France"}


def test_google_scraper_run_error(mocker, tmp_path):
    mock_client = mocker.Mock()
    mock_search_results = mocker.Mock()

    mock_search_results.as_dict.return_value = {"error": "Invalid API key."}
    mock_client.search.return_value = mock_search_results

    mock_serpapi = mocker.MagicMock()
    mock_serpapi.Client.return_value = mock_client
    mocker.patch.dict(sys.modules, {"serpapi": mock_serpapi})

    scraper = GoogleScraper()
    scraper.search_params = {"q": "test"}
    scraper.serpapi_key = "fake"

    save_path = tmp_path / "test.json"

    with pytest.raises(RuntimeError) as exc:
        scraper.scrape(search_n_pages=1, save_jobs_path=save_path)

    assert "Invalid API key." in str(exc.value)


def test_job_scraper_run_fresh(mocker, tmp_path):
    mocker.patch("config.settings.settings.demo_mode", False)

    mock_google_scraper = mocker.MagicMock()
    mock_google_scraper.scrape.return_value = [{"title": "Live Job"}]
    mocker.patch("services.scraping.google_scraper.GoogleScraper", return_value=mock_google_scraper)

    # Mock search results path
    mocker.patch("services.scraping.Path.mkdir")

    scraper = JobScraper()
    res = scraper.run(search_n_pages=1, use_last_scrape=False)

    assert "google" in res
    assert res["google"]["results"][0]["title"] == "Live Job"
    mock_google_scraper.scrape.assert_called_once()
