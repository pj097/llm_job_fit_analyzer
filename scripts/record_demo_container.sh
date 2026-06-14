#!/usr/bin/env bash
# Package the demo fixtures inside the app container.
#
# Runs scripts/record_demo.py in the live-app image so the Python environment
# matches production exactly. No LLM and no network access are needed: the
# script only reads from data/ (scored cache) and search_results/ (last scrape)
# and writes to demo/fixtures/.
#
# Prerequisites: run the main app and score some jobs first so the cache exists.
#
# Usage:
#   scripts/record_demo_container.sh
#   scripts/record_demo_container.sh --top 8 --low 2
#   scripts/record_demo_container.sh --cache data/scored_cache_ollama_gemma4_12b.json
#
# Afterwards, review and commit the contents of demo/fixtures/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-job-analyzer:latest}"

cd "$REPO_ROOT"

if ! podman image exists "$IMAGE"; then
    echo "[build] $IMAGE not found; building from Containerfile..."
    podman build -t "$IMAGE" -f Containerfile .
fi

echo "[record] running scripts/record_demo.py in $IMAGE ..."
exec podman run --rm -it \
    --volume "$REPO_ROOT/demo:/app/demo:Z" \
    --volume "$REPO_ROOT/data:/app/data:ro,Z" \
    --volume "$REPO_ROOT/search_results:/app/search_results:ro,Z" \
    --entrypoint python \
    "$IMAGE" scripts/record_demo.py "$@"
