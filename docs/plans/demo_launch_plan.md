# Demo Launch Plan

**Date:** 2026-06-12
**Goal:** Take the demo from "code-complete on the `refactor` branch" to "live on the VPS with genuine fixtures and a pipeline we trust."

Predecessor: `refactor_plan.md` (Phases 0–6, all code-complete). Everything below is sequenced — each milestone unblocks the next — and split between what runs on this machine and what needs you on the Forgejo instance / VPS.

---

## Milestone 1 — Land the refactor (PR `refactor` → `main`)

The branch holds Phases 0–6 plus the review fixes. Opening the PR is also the **first real execution of both workflows on the Forgejo runner** — until now they have only been verified locally, and the runner labels / container-build capability are unproven.

1. Open the PR. Both workflows trigger on `pull_request`; the deploy workflow's push/redeploy steps stay inert (guarded to `main` + `push`).
2. Watch for the known likely failure modes, in order of probability:
   - **`runs-on: docker` label mismatch** — both workflows now use the label the old (pre-refactor) deploy workflow used. If the runner advertises different labels, fix the label, nothing else.
   - **`docker build` fails in `deploy.yml`** — the runner needs a Docker daemon (socket mount or DinD). If the runner can't provide one, fallback: build with `podman build` if the host runner has it, or move image building to the VPS itself (`git pull` + build there) and reduce `deploy.yml` to the webhook trigger. Decide based on what the runner actually supports — don't pre-build infrastructure for a runner config we haven't seen fail yet.
   - **`actions/setup-python` / `setup-uv` quirks** inside the `node:20-bookworm` container — both are widely used on Forgejo, but if they misbehave, install uv via `curl -LsSf https://astral.sh/uv/install.sh | sh` and let `uv python install 3.12` replace setup-python.
3. Merge once green. The PR description should note the two behavior changes a reviewer would care about: demo fixtures are curated samples (Milestone 2 replaces them), and deploy is inert until Milestone 3's secrets exist.

**Acceptance:** PR merged; `lint_test` and the build-only path of `deploy` green on the Forgejo instance.

---

## Milestone 2 — Record genuine fixtures

The committed fixtures are a real scrape with **curated sample analyses** (no LLM was available when they were written). Before the demo is public-facing, replace them with real model output.

1. With Ollama up (or `GEMINI_API_KEY` set), run the recorder inside the app
   container (keeps the live scrape/score pipeline off the host):
   ```bash
   scripts/record_demo_container.sh                # reuse last scrape
   # or --fresh with SERPAPI_KEY for current listings
   ```
   (`uv run python scripts/record_demo.py` still works for local dev.)
   The script curates (top + low contrast), sanitizes (aborts on secret leakage), and verifies the replay by URL set.
2. Manually read every `triage_summary` before committing — these strings ship verbatim to a public site, and they are LLM commentary about real, named employers. Drop or re-record anything snarky or wrong; `--top`/`--low` re-curation is cheap.
3. Update the honesty copy, which currently says analyses are curated samples:
   - `app.py` demo banner → back to "captured from a real run" wording
   - `README.md` demo section → same
   - `refactor_plan.md` Phase 3.3 note → mark superseded
4. Commit fixtures + copy together (one commit, so the wording never disagrees with the data).

**Acceptance:** `uv run pytest tests/` green; demo replay verified locally via `scripts/record_demo.py` (its step [4/4] replays the fixtures); banner copy matches reality.

---

## Milestone 3 — Configure and ship the deploy

The pipeline commands are real but inert until the instance and VPS are configured. This is mostly your-side work; the repo needs at most small tweaks.

1. **Registry** — pick one (Codeberg's container registry, the Forgejo instance's package registry, or the VPS's own registry). Set on the Forgejo repo:
   - Variables: `REGISTRY`, `REGISTRY_USER`, `IMAGE`
   - Secrets: `REGISTRY_TOKEN`
2. **VPS runtime** — a systemd-managed container (podman quadlet is the natural fit):
   - unit pulls `${REGISTRY}/${IMAGE}:latest`, runs with memory/CPU caps (the app serves static fixtures; 256–512 MB is plenty)
   - pass `--server.baseUrlPath=/demos/vector-pathfinder` (or chosen path) per the README's reverse-proxy note
   - add `--browser.gatherUsageStats=false`
3. **Webhook receiver** — something on the VPS that, on POST with the bearer token, runs `podman pull` + `systemctl restart`. The `webhook` package or a 20-line systemd-socket script both work. Set `DEPLOY_WEBHOOK_URL` / `DEPLOY_WEBHOOK_TOKEN` secrets on Forgejo.
4. **Reverse proxy** — route the subpath to the container port; confirm websockets are proxied (Streamlit needs them; for nginx that's the `Upgrade`/`Connection` headers).
5. Push a trivial commit to `main` and watch the full chain: build → push → webhook → restart → new content live.

**Acceptance:** demo reachable at the public URL from a clean browser; a push to `main` visibly redeploys; container runs under resource caps with no secrets in its environment.

---

## Milestone 4 — Post-launch hardening (optional, cheap)

Do these only after the demo is live; none block launch.

1. **Containerfile.demo polish:** run as a non-root user; add a `HEALTHCHECK` against Streamlit's `/_stcore/health` endpoint; bake `--browser.gatherUsageStats=false` into the entrypoint.
2. **Python version alignment:** CI pins 3.12, the dev box runs 3.14, `pyproject.toml` says `>=3.12`. Pick the container's version (3.12) as canonical in CI and add a `requires-python` upper bound only if a real incompatibility appears (one pydantic-v1 deprecation warning already shows on 3.14).
3. **Uptime check:** any free pinger against the demo URL → email. The demo is static-fixture-backed, so alerts should be rare and meaningful.
4. **README badge** for the lint+test workflow once it's green on `main`.

---

## Explicitly deferred (unchanged from `refactor_plan.md` §4)

- Gemini batch scoring (UI stub already removed)
- Additional scrapers
- FastAPI backend/frontend split

## Suggested order of work

| Step | Where | Effort |
|---|---|---|
| 1. PR + CI shakeout | repo + Forgejo UI | ~half day, mostly waiting on runner behavior |
| 2. Real fixtures | this machine + Ollama | ~1 hour plus review of summaries |
| 3. Registry/VPS wiring | Forgejo UI + VPS shell | ~half day |
| 4. Hardening | repo | ~1 hour, post-launch |
