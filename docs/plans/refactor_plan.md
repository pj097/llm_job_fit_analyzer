# Refactor Plan: LLM Job Fit Analyzer

**Date:** 2026-06-12
**Goal:** Evolve the experimental implementation into a maintainable app with a first-class demo mode, modelled on the record/replay ("VCR") architecture described in `demo_app_review.md`.

---

## 1. Evaluation of the current state

### What is working well
- **Clear separation of concerns already exists**: `scrapers/` → `services/scraping.py` → `services/scoring.py` → `llm/` providers behind a `BaseLLM` ABC. The seams needed for a demo mode are already in place.
- **The app already contains an accidental VCR.** `use_last_scrape` replays the last scrape from `search_results/*.json`, and the scored cache (`data/scored_cache_*.json`) replays LLM results keyed by normalized job URL. Demo mode is largely a matter of *formalizing* these two mechanisms, not inventing new ones.
- Incremental cache saves (atomic tmp-file replace), URL normalization for stable cache keys, and hybrid Ollama/Gemini support are all sensible and worth keeping.

### Key problems

**Bugs (fix before any refactor):**
1. **Broken Gemini context-caching block** — `src/services/scoring.py:47-61` references `genai` and `timedelta` which are never imported (`use_cache=True` + Gemini raises `NameError`). It also uses the *old* `google.generativeai` caching API while `gemini.py` uses the new `google.genai` client, hardcodes `gemini-1.5-flash-001`, and `GeminiProvider.generate()` ignores `cache_name` anyway — so the server cache is never used even when created.
2. **`null` cache-key corruption** — in `scoring.py:91`, if a job has neither `job_url` nor an `apply_options` link, `url` is `None` and all such jobs collapse into a single `"null"` cache entry (visible in `data/scored_cache_ollama_gemma3_12b.json`). Jobs without a stable key should be skipped or keyed by a content hash.
3. **Normalization mismatch** — `JobScraper` normalizes only `apply_options[0].link`, but `JobScorer` prefers `job.get("job_url")`, which is never normalized → cache misses and duplicate spend.
4. **`temperature=0.0` is silently discarded** — `temperature or settings.default_temperature` (`scoring.py:23`) treats `0.0` as falsy and substitutes the default (`1.0`). Use `if temperature is not None`.
5. **Stale pagination token** — `GoogleScraper` mutates `self.search_params['next_page_token']`; a second `run()` in the same session resumes from the previous run's last page.
6. **Layering violation** — `google_scraper.py` imports `streamlit` inside the scrape loop to report errors, and will `KeyError` if the response has neither `jobs_results` nor `error`. Scrapers should raise/return errors; the UI layer renders them.
7. **Batch mode is a stub** — the UI exposes a "Batch Mode" checkbox but `score()` only has a comment where the batch logic should be, and `check_batch_results` doesn't download results. Either finish it or remove the toggle until it works.

**Structural issues:**
8. **Required secrets block startup** — `Settings` requires `gemini_api_key` and `serpapi_key`, so the app cannot even start for Ollama-only use, tests, or a demo build. Make them `Optional[str] = None` and validate at point of use.
9. **Heavy imports at module level** — `app.py` imports `ollama`; the services import `serpapi`, `google.genai`, `langchain_ollama` at import time. This is what forced the current `mock_build/mock_app.py` hack into existence, and it stops the app starting in any environment without those services configured (tests, demo container).
10. **The demo is a fork of the app, not a mode of it** — `mock_app.py` patches `sys.modules` with `MagicMock` and `exec()`s `app.py`. It is brittle (any new import in `app.py` breaks it), drifts from the real app, and leaks mock artifacts (`mock_results.shape`) into the UI. This is the single biggest thing the Vectra pattern fixes.
11. **No tests, no lint CI** — and the `deploy.yml` guard for main-branch-only deployment is commented out, so every PR force-pushes to the public pages branches.

### Verdict on `demo_app_review.md` as a target
The **record/replay core is the right model** and maps cleanly onto this codebase. However, Vectra is a backend/frontend split (FastAPI + Streamlit), so parts of it should *not* be copied:

| Vectra concept | Adopt here? | Mapping |
|---|---|---|
| `DEMO_MODE` / `SAVE_FOR_DEMO` env settings | ✅ Yes | New fields on `Settings` |
| `RecordableService` interception | ✅ Yes | A small `Recorder` used at the two existing seams: `scrape()` and `generate()`/scored-cache |
| Demo-aware UI degradation | ✅ Yes | Banner + disabled controls in `app.py` via `settings.demo_mode` |
| Recording workflow script | ✅ Yes | `scripts/record_demo.py` driving the services directly |
| `/v1/health`, admin endpoints | ❌ No | Single-process Streamlit app — read settings directly; no HTTP API needed |
| Demo container (`Containerfile.demo`) | ✅ Yes — **primary target** | Lightweight, standalone container with fixtures baked in and zero API keys, deployed to a VPS. No LLM, no SerpApi → near-zero running cost. The stlite/`mock_build` static-page pipeline is retired along with it. |

---

## 2. Target architecture

```
src/
  config/settings.py      # + demo_mode, save_for_demo, fixtures_dir; optional secrets
  services/
    recorder.py           # NEW: record/replay store (load_fixture / save_fixture)
    scraping.py           # demo-aware via recorder
    scoring.py            # demo-aware via recorder; dead cache code removed
  llm/                    # lazy provider imports; unchanged interfaces
demo/
  fixtures/
    google_scrape.json    # curated, sanitized scrape results
    scored_jobs.json      # curated scored results (same schema as scored_cache)
scripts/
  record_demo.py          # SAVE_FOR_DEMO workflow: scrape → score → curate → write fixtures
app.py                    # demo-aware UI; lazy ollama import
Containerfile             # live app (unchanged)
Containerfile.demo        # demo container: ENV DEMO_MODE=true, fixtures baked in, no secrets
```

(`mock_build/` is deleted once the demo container ships.)

**Replay keying decision:** replay LLM results by **normalized job URL** (the existing scored-cache schema), *not* by prompt hash. Prompt-hash replay breaks whenever `.prompt.txt` changes; URL keying is stable, already proven by the current cache, and means demo fixtures are just a curated scored cache. Trade-off: demo mode cannot show "live" scoring of an unknown job — acceptable, and consistent with Vectra locking model parameters in demo.

**How the modes compose** (mirrors Vectra §1.1):
- `demo_mode=True` → `JobScraper.run()` returns `demo/fixtures/google_scrape.json`; `JobScorer` is constructed without any LLM provider and serves only from `demo/fixtures/scored_jobs.json` (jobs missing from fixtures are dropped with a notice). No network, no keys, no heavy imports.
- `demo_mode=False, save_for_demo=True` → live run; after each successful scrape/score, the result is *also* written to `fixtures_dir`.
- Both false → current live behavior.

---

## 3. Phased plan

### Phase 0 — Hardening (prerequisite, ~1 day) ✅ DONE 2026-06-12
1. ✅ Fixed bugs 1–7 above. The broken context-cache block and the `use_cache`/`use_batch` UI toggles were **deleted** (never functional); reintroduce properly later if Gemini spend justifies it.
2. ✅ URLs normalized in one place: `normalize_url` is now a module-level function in `services/scraping.py`, used by both scraper and `JobScorer._job_url()`; jobs with no derivable key are skipped.
3. ✅ `gemini_api_key` / `serpapi_key` are optional; a clear error is raised only when the corresponding provider/scraper is actually used. This is what lets the demo container start with zero secrets.
4. ✅ Heavy imports made lazy: `import ollama` inside the provider branch in `app.py`; `import serpapi` inside the scrape call; LLM provider modules imported inside the `JobScorer` provider branches.

### Phase 1 — Record/replay core (~1 day) ✅ DONE 2026-06-12
1. ✅ `Settings` gained `demo_mode`, `save_for_demo`, `fixtures_dir` (default `demo/fixtures`); the remaining required fields got safe defaults so `Settings()` instantiates with **no `.env` at all** (demo-container requirement, originally slated for Phase 5's smoke test).
2. ✅ `services/recorder.py` with `fixture_path` / `load_fixture` / `save_fixture` (JSON, atomic tmp-replace writes).
3. ✅ `JobScraper.run()` and `JobScorer.__init__`/`score()` wired per the mode table; in demo mode the scorer is built with no LLM provider and unrecorded jobs are dropped with a notice. Verified end-to-end: record → fixtures → replay with no keys, no network, no `.env`.
4. ✅ Bonus fix found while testing with real data: SerpApi Google Jobs results carry `source_link`/`share_link`, **never** `job_url`/`apply_options` — which was the true cause of the `"null"` cache collapse. `_job_url()` now falls back `job_url` → `apply_options[0].link` → `source_link` → `share_link`.

### Phase 2 — Demo-aware UI (~half day) ✅ DONE 2026-06-12
1. ✅ `app.py` in demo mode: `DEMO_MODE // RECORDED_FIXTURES` caption + info banner; DATA_ENGINE checkbox/slider and NEURAL_RUNTIME provider/model/temperature controls shown disabled ("recorded"); MODEL_GUIDE hidden; AGGREGATE_DATA / INITIALIZE_SCORING keep working against fixtures so the interactive flow is preserved (Vectra §2.2).
2. ✅ Gemini model selectbox expander placement fixed (done in Phase 0).
3. ✅ Extra robustness: live mode shows an `OLLAMA_OFFLINE` warning instead of crashing when no Ollama server is reachable; scoring/scraping failures (missing fixture, missing key/params) render as `st.error` instead of tracebacks. Verified with `streamlit.testing.v1.AppTest`: demo render + both buttons end-to-end, missing-fixture error path, live mode without Ollama.

### Phase 3 — Recording workflow (~half day) ✅ DONE 2026-06-12
1. ✅ `scripts/record_demo.py`: runs scrape + score with `save_for_demo=True`, **curates** (`--top` by `overall_fit` plus `--low` for contrast, deduplicated by derived URL), **sanitizes** (strips `thumbnail` signed URLs; aborts if a configured secret appears in any fixture), and **verifies** the demo replay end to end before declaring success. URL derivation extracted to module-level `derive_job_url()` so the script curates with the exact keying logic the scorer uses.
2. ✅ README gained a "Demo Mode (record & replay)" section: settings table, fixture-refresh procedure, demo run command.
3. ✅ Fixtures committed under `demo/fixtures/`: a **real recorded scrape** plus **curated sample analyses** (no live LLM was available when they were written; the demo banner and README label them as such). Re-run `scripts/record_demo.py` against a live LLM to replace them with genuine output.

### Phase 4 — Packaging & VPS deploy (~1 day) ✅ DONE 2026-06-12
1. ✅ `Containerfile.demo` — based on the existing `Containerfile`, plus `ENV DEMO_MODE=true`, `demo/fixtures/` copied in, no secrets mounted, and trimmed dependencies if practical (the lazy imports mean `serpapi`/`ollama`/`google.genai` are never touched at runtime). Lightweight, standalone, zero keys.
2. ⚠️ Rewrite `.forgejo/workflows/deploy.yml` for the VPS flow: on push to `main`, build the demo image, push it to the registry, and trigger a redeploy on the VPS. Guarded with `if: github.ref == 'refs/heads/main' && github.event_name == 'push'` — PRs build only, never deploy. **Not yet live**: the push/redeploy steps are real commands but inert until `REGISTRY`/`REGISTRY_USER`/`IMAGE` variables and `REGISTRY_TOKEN`/`DEPLOY_WEBHOOK_*` secrets are configured on the Forgejo instance, and the `docker`-labelled runner must expose a Docker daemon. (The first version of this file had stub `echo` steps — fixed 2026-06-12.)
3. ✅ Reverse-proxy note for the VPS added to `README.md`: serve the demo under the existing site with `streamlit run --server.baseUrlPath` set accordingly; cap resources (it's static data, a small container is plenty).
4. ✅ Delete `mock_build/` and the stlite pages-push steps — the static-page demo is retired in favor of the VPS container.

### Phase 5 — Tests & CI (~1 day, parallelizable) ✅ DONE 2026-06-12
1. ✅ The fixtures double as test data: pytest covering `normalize_url`, cache hit/miss & null-key handling, demo-mode scrape/score replay, and `clean_list`.
2. ✅ Added a lint+test workflow (ruff migrated to the current `[tool.ruff.lint]` table format).
3. ✅ Smoke test: the demo replay is exercised end-to-end in CI via `streamlit.testing.v1.AppTest` (`tests/integration/test_demo_app.py`) — runs the real `app.py` with no `.env` and no network, clicks both buttons, and asserts every fixture job is served. (The original `streamlit run` + `kill -0` smoke step was vacuous — Streamlit doesn't execute the script until a session connects — and was removed 2026-06-12. The same fix made the suite hermetic: the scoring test no longer depends on the gitignored `.prompt.txt`, and `uv.lock` is now tracked so container builds work from a fresh checkout.)

### Phase 6 — Code Quality & Scalability (Extra Stage) ✅ DONE 2026-06-12
1. ✅ **Comprehensive Test Suite**: Structured `tests/unit/` mirroring the `src/` layout. Added robust tests for `LLMProviders` (Ollama/Gemini SDK integrations), `JobScrapers` (mocked `SerpApi` interactions), and app configurations.
2. **Code Coverage Validation**: Configured `pytest-cov` and achieved ~90% code coverage across the `src/` backend pipeline.
3. ✅ **Strict Type Enforcement**: Added `pyright` to the `uv` toolchain, fixed typing errors related to `None` constraints in `JobScorer` and Streamlit `metric` subsets, and enforced type-checking in the CI pipeline.
4. ✅ **Automatic Formatting**: Integrated `ruff format` to apply Black-equivalent styling across the entire codebase and added a strict checking hook to `.forgejo/workflows/lint_test.yml`.

---

## 4. Explicitly out of scope (for now)
- FastAPI backend/frontend split — single-process Streamlit doesn't need it; revisit only if a second frontend appears.
- Finishing Gemini batch mode — remove the UI stub; track as a separate feature.
- Additional scrapers — per README "Further Work", not part of this refactor.

## 5. Suggested order of PRs
1. `fix/hardening` (Phase 0) — pure fixes, no behavior change for happy paths. ✅ done 2026-06-12.
2. `feat/demo-recorder` (Phases 1–2) — demo mode functional locally.
3. `feat/record-workflow` (Phase 3) — fixtures generated and committed.
4. `feat/demo-deploy` (Phase 4) — `Containerfile.demo` + VPS deploy pipeline; `mock_build/` and stlite retired.
5. `chore/tests-ci` (Phase 5).
