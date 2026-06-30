from pathlib import Path

from services.scoring import JobScorer, derive_job_url
from services.scraping import JobScraper, normalize_url


def test_normalize_url():
    """Test URL normalization logic."""
    assert normalize_url("https://example.com/job?utm_source=test") == "https://example.com/job"
    assert normalize_url("http://example.com/job/") == "http://example.com/job/"
    assert (
        normalize_url("https://example.com/job?trk=123&foo=bar")
        == "https://example.com/job?foo=bar"
    )
    assert normalize_url("") == ""
    assert normalize_url(None) == ""


def test_derive_job_url():
    """Test priority logic for finding the best URL."""
    # Priority: job_url > apply_options[0].link > source_link > share_link

    # 1. job_url
    assert derive_job_url({"job_url": "https://a.com"}) == "https://a.com"

    # 2. apply_options
    assert derive_job_url({"apply_options": [{"link": "https://b.com"}]}) == "https://b.com"

    # 3. source_link
    assert derive_job_url({"source_link": "https://c.com"}) == "https://c.com"

    # 4. share_link
    assert derive_job_url({"share_link": "https://d.com"}) == "https://d.com"

    # Null case
    assert derive_job_url({}) == ""


def test_cache_hit_and_null_key(tmp_path, mocker, monkeypatch):
    """Test that valid keys hit the cache and null keys are safely skipped."""
    mocker.patch("config.settings.settings.demo_mode", False)

    # Sandbox the scorer: .prompt.txt is gitignored (absent on a fresh
    # checkout) and the cache writes to data/ relative to the cwd, so both
    # must live under tmp_path for the test to be hermetic.
    monkeypatch.chdir(tmp_path)
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Score this job.")
    mocker.patch("config.settings.settings.prompt_file", str(prompt_file))

    # Create a fake scorer and cache
    scorer = JobScorer(model="fake-model")
    scorer.scored_data = {
        "https://example.com/job1": {"job_url": "https://example.com/job1", "overall_fit": 9}
    }

    # Mock the LLM to prevent network calls and detect if it was called
    mock_llm = mocker.Mock()
    mock_llm.generate.return_value = '{"overall_fit": 5, "company": "New"}'
    scorer.llm = mock_llm

    scraping_data = {
        "google": {
            "results": [
                # Cache hit
                {"job_url": "https://example.com/job1?utm_source=1", "title": "Job 1"},
                # Cache miss
                {"job_url": "https://example.com/job2", "title": "Job 2"},
                # Null key
                {"title": "No Link Job"},
            ]
        }
    }

    df = scorer.score(scraping_data)

    # Assertions
    assert len(df) == 2, "Null key job should be skipped"

    hit = df[df["job_url"] == "https://example.com/job1"].iloc[0]
    assert hit["overall_fit"] == 9, "Should load from cache"
    assert hit["job_title"] == "Job 1", "Should inject missing title into old cache"

    miss = df[df["job_url"] == "https://example.com/job2"].iloc[0]
    assert miss["overall_fit"] == 5, "Should generate via mock LLM"
    assert miss["job_title"] == "Job 2", "Should inject missing title from scrape"

    assert mock_llm.generate.call_count == 1, "LLM should only be called once for the miss"


def test_result_cb_streams_each_scored_job(tmp_path, mocker, monkeypatch):
    """result_cb fires once per job served (cache hit and fresh score alike)."""
    mocker.patch("config.settings.settings.demo_mode", False)
    monkeypatch.chdir(tmp_path)
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Score this job.")
    mocker.patch("config.settings.settings.prompt_file", str(prompt_file))

    scorer = JobScorer(model="fake-model")
    scorer.scored_data = {
        "https://example.com/job1": {"job_url": "https://example.com/job1", "overall_fit": 9}
    }
    mock_llm = mocker.Mock()
    mock_llm.generate.return_value = '{"overall_fit": 5, "company": "New"}'
    scorer.llm = mock_llm

    scraping_data = {
        "google": {
            "results": [
                {"job_url": "https://example.com/job1?utm_source=1", "title": "Job 1"},
                {"job_url": "https://example.com/job2", "title": "Job 2"},
            ]
        }
    }

    seen = []
    scorer.score(scraping_data, result_cb=lambda r: seen.append(r["overall_fit"]))

    # One callback for the cache hit, one for the freshly scored job.
    assert seen == [9, 5]


def test_exclude_keywords_drops_matching_titles(tmp_path, mocker, monkeypatch):
    """Jobs whose title matches an exclude keyword never reach the cache or LLM."""
    mocker.patch("config.settings.settings.demo_mode", False)
    monkeypatch.chdir(tmp_path)
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Score this job.")
    mocker.patch("config.settings.settings.prompt_file", str(prompt_file))

    scorer = JobScorer(model="fake-model")
    mock_llm = mocker.Mock()
    mock_llm.generate.return_value = '{"overall_fit": 5}'
    scorer.llm = mock_llm

    scraping_data = {
        "google": {
            "results": [
                {"job_url": "https://example.com/eng", "title": "ML Engineer"},
                {"job_url": "https://example.com/mgr", "title": "Engineering Manager"},
                {"job_url": "https://example.com/dir", "title": "Director of Data"},
            ]
        }
    }

    # Case-insensitive match drops the manager and director roles.
    df = scorer.score(scraping_data, exclude_keywords=["manager", "DIRECTOR"])

    assert list(df["job_title"]) == ["ML Engineer"]
    assert mock_llm.generate.call_count == 1, "Excluded titles must not be scored"


def test_demo_mode_replay(mocker):
    """Test that demo mode serves exclusively from recorded fixtures."""
    mocker.patch("config.settings.settings.demo_mode", True)

    fake_fixtures_dir = Path("fake_demo_fixtures")
    mocker.patch("config.settings.settings.fixtures_dir", fake_fixtures_dir)

    def fake_load_fixture(name):
        if name == "scored_jobs":
            return {"https://demo.com/job": {"job_url": "https://demo.com/job", "overall_fit": 10}}
        elif name == "google_scrape":
            return [
                {"job_url": "https://demo.com/job", "title": "Demo Job"},
                {"job_url": "https://demo.com/unscored", "title": "Unscored Job"},
            ]
        return {}

    mocker.patch("services.recorder.load_fixture", side_effect=fake_load_fixture)

    # 1. Scrape in demo mode
    scraper = JobScraper()
    scraping = scraper.run()

    assert "google" in scraping
    assert len(scraping["google"]["results"]) == 2

    # 2. Score in demo mode
    scorer = JobScorer()
    assert scorer.llm is None, "LLM should not be initialized in demo mode"

    df = scorer.score(scraping)

    # Should only return the 1 job that exists in the scored_jobs fixture
    assert len(df) == 1
    assert df.iloc[0]["overall_fit"] == 10
    assert df.iloc[0]["job_url"] == "https://demo.com/job"
