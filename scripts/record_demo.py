"""Packages the demo fixtures from the live scoring cache.

No LLM, no scraping. The main app must have already scored jobs; this script
reads the live cache, curates a representative subset, and writes the fixture
files the demo container ships with. If the required data does not exist it
tells you what to run first.

Usage:
    uv run python scripts/record_demo.py
    uv run python scripts/record_demo.py --top 8 --low 2
    uv run python scripts/record_demo.py --cache data/scored_cache_ollama_gemma4_12b.json

Afterwards, review and commit the contents of demo/fixtures/.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from config.settings import settings  # noqa: E402
from services import recorder  # noqa: E402
from services.scoring import JobScorer, derive_job_url  # noqa: E402
from services.scraping import JobScraper  # noqa: E402


def sanitize_job(job: dict) -> dict:
    job = dict(job)
    job.pop("thumbnail", None)  # signed/expiring image URLs
    return job


def parse_cache_meta(path: Path) -> tuple[str, str]:
    """Extract provider and model from a scored_cache_{provider}_{model}.json filename."""
    rest = path.stem.removeprefix("scored_cache_")  # e.g. "ollama_gemma4_12b"
    provider, _, model = rest.partition("_")
    return provider, model


def load_scrape_params(scrape_path: Path) -> dict | None:
    """Return the query/location a scrape ran with, or None if not recorded.

    The scraper writes this alongside each scrape under params/; older scrapes
    (made before that) simply have no sidecar.
    """
    params_path = scrape_path.parent / "params" / scrape_path.name
    if not params_path.exists():
        return None
    try:
        return json.loads(params_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--top", type=int, default=12, help="High-scoring jobs to keep")
    parser.add_argument("--low", type=int, default=3, help="Low-scoring jobs to keep for contrast")
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Scored cache file to use (default: most recently modified data/scored_cache_*.json)",
    )
    args = parser.parse_args()

    # 1. Find the live scored cache
    if args.cache:
        cache_path = args.cache
        if not cache_path.exists():
            print(f"ERROR: specified cache file not found: {cache_path}")
            return 1
    else:
        cache_files = sorted(
            Path("data").glob("scored_cache_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not cache_files:
            print(
                "ERROR: No scored cache found in data/.\n"
                "Run the main app and score some jobs first, then re-run this script."
            )
            return 1
        cache_path = cache_files[0]
        if len(cache_files) > 1:
            others = [str(p) for p in cache_files[1:]]
            print(f"[info] Multiple cache files found; using most recent: {cache_path}")
            print(f"       Others: {others}")
            print("       Pass --cache to choose a specific one.")

    # 2. Load and validate
    print(f"[1/4] Loading scored cache: {cache_path}")
    raw_cache: dict = json.loads(cache_path.read_text())

    # Extract provider/model from cache metadata (new format) or filename (legacy)
    cache_meta: dict = raw_cache.pop("_meta", None) if isinstance(raw_cache, dict) else None
    if cache_meta:
        _provider = cache_meta["provider"]
        _model = cache_meta["model"]
    else:
        _provider, _model = parse_cache_meta(cache_path)

    jobs_cache = raw_cache if cache_meta is None else raw_cache.get("jobs", raw_cache)
    valid = {url: item for url, item in jobs_cache.items() if item.get("overall_fit") is not None}
    skipped = len(jobs_cache) - len(valid)
    if skipped:
        print(f"      Skipped {skipped} job(s) with missing overall_fit")
    if not valid:
        print(
            "ERROR: No jobs with a valid overall_fit in the cache.\n"
            "Run the main app and score some jobs first."
        )
        return 1
    print(f"      {len(valid)} valid scored jobs found")

    # 3. Curate: top N + bottom N for contrast
    df = pd.DataFrame(valid.values())
    ranked = df.sort_values("overall_fit", ascending=False)
    keep = pd.concat([ranked.head(args.top), ranked.tail(args.low)]).drop_duplicates(
        subset="job_url"
    )
    keep_urls: set[str] = set(keep["job_url"])
    print(f"      Keeping {len(keep_urls)} jobs (top {args.top} + low {args.low})")

    # 4. Find the last scrape and match to keep_urls
    print("[2/4] Loading last scrape from search_results/...")
    scrape_files = sorted(
        Path("search_results").glob("google_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not scrape_files:
        print(
            "ERROR: No scrape file found in search_results/.\n"
            "Run the main app with 'Aggregate Data' first, then re-run this script."
        )
        return 1

    # Coherence check: the demo is LABELLED with the scored cache's query/location
    # but its jobs come from the latest scrape. If the two disagree (e.g. you
    # scored with 'Use last aggregation' after changing the search, or mixed
    # several searches into one cache) the fixture would mislabel its jobs.
    scrape_params = load_scrape_params(scrape_files[0])
    if scrape_params is not None and cache_meta:
        mismatches = [
            f"{field}: scrape={scrape_params.get(field)!r} cache={cache_meta.get(field)!r}"
            for field in ("query", "location")
            if (scrape_params.get(field) or "") != (cache_meta.get(field) or "")
        ]
        if mismatches:
            print("      WARNING: latest scrape and scored cache disagree on the search:")
            for m in mismatches:
                print(f"        {m}")
            print(
                "      The demo would be labelled with the cache values while its jobs come\n"
                "      from the scrape above. Re-run a single fresh scrape+score (uncheck\n"
                "      'Use last aggregation') so they match, or pass --cache to pick another."
            )

    raw_scrape: list = json.loads(scrape_files[0].read_text())
    kept_scrape: list[dict] = []
    seen: set[str] = set()
    for job in raw_scrape:
        url = derive_job_url(job)
        if url in keep_urls and url not in seen:
            seen.add(url)
            kept_scrape.append(sanitize_job(job))

    missing = keep_urls - seen
    if missing:
        print(
            f"      WARNING: {len(missing)} scored job(s) not found in the last scrape "
            f"and will be dropped:"
        )
        for url in sorted(missing):
            print(f"        {url}")
        print("      Re-run 'Aggregate Data' in the main app and retry if this is unexpected.")
        for url in missing:
            del valid[url]
        keep_urls -= missing

    print(f"      {len(kept_scrape)} scrape entries matched")

    # 5. Save fixtures
    print("[3/4] Saving fixtures...")
    # Capture the search line, location, and prompt so the demo can display them
    # as fixed inputs (the live UI lets the user edit these). These now come from
    # the UI, so prefer the values the scoring run recorded into the cache _meta;
    # fall back to config only for older caches that predate this.
    try:
        search_params = json.loads(settings.google_search_params)
    except json.JSONDecodeError:
        search_params = {}
    prompt_path = Path(settings.prompt_file)
    cm = cache_meta or {}
    _query = cm.get("query") or search_params.get("q", "")
    _location = cm.get("location") or search_params.get("location", "")
    _prompt = cm.get("prompt") or (prompt_path.read_text() if prompt_path.exists() else "")
    recorder.save_fixture(
        "scored_jobs",
        {
            "_meta": {
                "provider": _provider,
                "model": _model,
                "recorded_at": datetime.datetime.now().isoformat(),
                "query": _query,
                "location": _location,
                "prompt": _prompt,
            },
            "jobs": {url: valid[url] for url in keep_urls},
        },
    )
    recorder.save_fixture("google_scrape", kept_scrape)
    print(f"      Saved {len(keep_urls)} scored jobs and {len(kept_scrape)} scrape entries")

    # 6. Sanitize: fail if any configured secret leaked into a fixture
    blob = "".join(p.read_text() for p in settings.fixtures_dir.glob("*.json"))
    for name in ("serpapi_key", "gemini_api_key"):
        secret_field = getattr(settings, name)
        secret = secret_field.get_secret_value() if secret_field else None
        if secret and secret in blob:
            print(f"ERROR: {name} leaked into the fixtures; aborting. Nothing to commit.")
            return 1

    # 7. Verify: replay exactly as the demo container will
    print("[4/4] Verifying demo replay...")
    settings.demo_mode = True
    demo_df = JobScorer().score(JobScraper().run())
    replayed = set() if demo_df.empty else set(demo_df["job_url"])
    if replayed != keep_urls:
        print(
            f"ERROR: demo replay served {len(replayed)} jobs, expected {len(keep_urls)}; "
            f"missing: {sorted(keep_urls - replayed)}"
        )
        return 1

    print(f"      Demo replay OK: {len(demo_df)} jobs served from fixtures")
    print(f"Done. Review and commit the contents of {settings.fixtures_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
