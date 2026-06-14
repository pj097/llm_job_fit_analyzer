"""Capture a full-page screenshot of the demo app with Playwright.

Drives the demo through its scrape + score flow (both replayed from the
recorded fixtures) and saves a full-page WebP — handy for the README, the
landing page, or social cards. No LLM, no scraping, no API keys: it only ever
exercises demo mode.

Usage:
    # Launch a throwaway demo server, capture, tear it down (one command):
    uv run python scripts/capture_demo.py --launch

    # Capture an already-running demo (e.g. the container on :8501):
    uv run python scripts/capture_demo.py --url http://localhost:8501

    # Just the landing view, without driving the scrape/score buttons:
    uv run python scripts/capture_demo.py --launch --no-score

Prerequisites (Playwright is an optional dev dependency):
    uv sync --group screenshot
    uv run playwright install chromium
"""

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def wait_for_health(base_url: str, timeout: float) -> bool:
    """Poll Streamlit's health endpoint until it answers or we give up."""
    import time

    health = base_url.rstrip("/") + "/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def launch_demo(port: int, theme: str) -> subprocess.Popen:
    """Start a headless Streamlit server in demo mode as a subprocess.

    `--theme.base` forces light/dark without touching app code.
    """
    env = {**os.environ, "DEMO_MODE": "true"}
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        f"--theme.base={theme}",
    ]
    return subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# Injected just before the screenshot. Hides Streamlit's top chrome (the
# menu/Deploy toolbar) and defeats the app's internal scroll container so a
# full_page shot captures the whole page instead of a single viewport.
_SCREENSHOT_CSS = """
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}
"""

# Force every sidebar expander (rendered as native <details>) open so its
# content shows in the shot. Setting .open directly avoids per-expander clicks.
_EXPAND_SIDEBAR_JS = """
document.querySelectorAll("[data-testid='stSidebar'] details")
    .forEach(d => { d.open = true; });
"""

# The results block (metrics, matches dataframe, analysis log) is wrapped in
# app.py by `st.container(key="results")`, which Streamlit renders with this
# class. The screenshot script targets it for --region results.
_RESULTS_SELECTOR = ".st-key-results"

# Open the first analysis-log expander inside the results block (the top match
# under TECHNICAL_ANALYSIS_LOG).
_EXPAND_FIRST_LOG_JS = """
() => {
    const ex = document.querySelector(
        ".st-key-results [data-testid='stExpander'] details");
    if (ex) ex.open = true;
}
"""


def capture(
    url: str,
    out: Path,
    *,
    quality: int,
    score: bool,
    width: int,
    height: int,
    crop_top: int,
    region: str,
) -> None:
    """Open the demo, optionally drive the scrape/score flow, screenshot it."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: Playwright is not installed.\n"
            "  uv sync --group screenshot\n"
            "  uv run playwright install chromium"
        )
        raise SystemExit(1) from None

    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        try:
            page.goto(url, wait_until="domcontentloaded")
            # Streamlit holds a websocket open, so networkidle never settles;
            # wait on concrete elements instead.
            page.get_by_role("button", name="AGGREGATE_DATA").wait_for(timeout=30_000)

            if score:
                print("      Aggregating data (replayed)...")
                page.get_by_role("button", name="AGGREGATE_DATA").click()
                page.get_by_text("Data aggregation complete").wait_for(timeout=30_000)

                print("      Scoring (replayed)...")
                page.get_by_role("button", name="INITIALIZE_SCORING").click()
                # Results render the dataframe; wait for it, then let the
                # progress bar/spinner clear before shooting.
                page.locator("[data-testid='stDataFrame']").wait_for(timeout=60_000)

            # Reveal everything we want visible before measuring/shooting.
            page.evaluate(_EXPAND_SIDEBAR_JS)
            if region == "results":
                page.evaluate(_EXPAND_FIRST_LOG_JS)
            page.add_style_tag(content=_SCREENSHOT_CSS)
            # Let the relayout settle, then grow the viewport to the full content
            # height so nothing past the first screen is clipped.
            page.wait_for_timeout(1000)
            full_height = int(page.evaluate("() => document.body.scrollHeight"))
            page.set_viewport_size({"width": width, "height": min(full_height + 40, 20_000)})
            page.wait_for_timeout(500)

            # Playwright only emits PNG/JPEG, so capture PNG bytes and let Pillow
            # write the requested format (WebP by default). Pillow ships with
            # Streamlit, so no extra dependency.
            if region == "results":
                loc = page.locator(_RESULTS_SELECTOR).first
                try:
                    loc.wait_for(timeout=10_000)
                except PlaywrightTimeoutError:
                    print(
                        f"ERROR: results block '{_RESULTS_SELECTOR}' not found. Make sure "
                        "scoring ran (don't pass --no-score)."
                    )
                    raise SystemExit(1) from None
                png = loc.screenshot()
            else:
                png = page.screenshot(full_page=True)
        finally:
            browser.close()

    _write_image(png, out, quality, crop_top=crop_top)


def _write_image(png: bytes, out: Path, quality: int, *, crop_top: int = 0) -> None:
    """Encode PNG screenshot bytes to the format implied by out's extension."""
    from io import BytesIO

    from PIL import Image

    fmt = {".webp": "WEBP", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}.get(
        out.suffix.lower(), "WEBP"
    )
    img = Image.open(BytesIO(png))
    if crop_top > 0:
        img = img.crop((0, min(crop_top, img.height), img.width, img.height))
    if fmt == "JPEG":
        img = img.convert("RGB")  # drop alpha; JPEG has no transparency
    save_kwargs = {} if fmt == "PNG" else {"quality": quality}
    img.save(out, format=fmt, **save_kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL of a running demo (default: http://localhost:<port>)",
    )
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Start a throwaway demo server, capture, then stop it",
    )
    parser.add_argument("--port", type=int, default=8501, help="Port for --launch / default URL")
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "static" / "demo.webp", help="Output image path"
    )
    parser.add_argument("--quality", type=int, default=82, help="WebP quality (1-100)")
    parser.add_argument("--width", type=int, default=1280, help="Viewport width")
    parser.add_argument("--height", type=int, default=800, help="Viewport height")
    parser.add_argument(
        "--theme",
        default="dark",
        choices=["dark", "light"],
        help="Streamlit theme to force (only applies with --launch)",
    )
    parser.add_argument(
        "--crop-top",
        type=int,
        default=0,
        help="Pixels to crop off the top of the final image (after the chrome is hidden)",
    )
    parser.add_argument(
        "--region",
        default="full",
        choices=["full", "results"],
        help="'full' page, or just the 'results' block (metrics → analysis log, "
        "with the top analysis entry expanded)",
    )
    parser.add_argument(
        "--no-score",
        dest="score",
        action="store_false",
        help="Capture the landing view without driving the scrape/score buttons",
    )
    args = parser.parse_args()

    url = args.url or f"http://localhost:{args.port}"

    server: subprocess.Popen | None = None
    if args.launch:
        print(f"[1/3] Launching demo server on port {args.port}...")
        server = launch_demo(args.port, args.theme)
        if not wait_for_health(url, timeout=60):
            server.terminate()
            print("ERROR: demo server did not become healthy within 60s.")
            return 1
    else:
        print(f"[1/3] Using running demo at {url}")
        if not wait_for_health(url, timeout=10):
            print(f"ERROR: no healthy demo at {url}. Start one or pass --launch.")
            return 1

    try:
        print("[2/3] Capturing...")
        capture(
            url,
            args.out,
            quality=args.quality,
            score=args.score,
            width=args.width,
            height=args.height,
            crop_top=args.crop_top,
            region=args.region,
        )
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    print(f"[3/3] Saved {args.out} ({args.out.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
