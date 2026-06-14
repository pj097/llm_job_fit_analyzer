#!/usr/bin/env bash
# Capture a full-page demo screenshot inside the app container.
#
# Playwright and its Chromium browser are baked into the main image
# (see Containerfile), so this just runs scripts/capture_demo.py there. The
# image is Debian-based, which is where Chromium's apt-installed shared
# libraries live.
#
# The script's --launch flag starts a headless demo server inside the same
# container, so no separate app process is needed. Everything is replayed from
# demo/fixtures/ (baked into the image): no LLM, no scraping, no API keys.
#
# Output lands in the repo's static/ (mounted rw) as static/demo.webp by default.
#
# Usage:
#   scripts/capture_demo_container.sh
#   scripts/capture_demo_container.sh --no-score
#   scripts/capture_demo_container.sh --out static/social-card.webp --quality 90
#
# After changing app.py or the capture script, rebuild the image so the change
# is picked up: `podman build -t job-analyzer:latest -f Containerfile .`
# (the Chromium layer is cached, so this is fast).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-job-analyzer:latest}"

cd "$REPO_ROOT"

if ! podman image exists "$IMAGE"; then
    echo "[build] $IMAGE not found; building from Containerfile..."
    podman build -t "$IMAGE" -f Containerfile .
fi

echo "[capture] running capture_demo.py in $IMAGE (Playwright + Chromium baked in) ..."
# scripts/ is mounted ro so capture-script tweaks are picked up without an image
# rebuild; static/ is mounted rw so the screenshot persists back to the repo.
# Lowercase `:z` is the shared SELinux relabel and is idempotent; never use `:Z`,
# which applies private per-container MCS categories that outlive the container
# and lock the host out of the files.
exec podman run --rm -it \
    --volume "$REPO_ROOT/scripts:/app/scripts:ro,z" \
    --volume "$REPO_ROOT/static:/app/static:z" \
    --entrypoint python \
    "$IMAGE" scripts/capture_demo.py --launch --out static/demo.webp "$@"
