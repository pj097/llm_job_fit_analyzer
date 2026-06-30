"""Overwrite Streamlit's shell favicon with the brand icon.

Streamlit's static index.html hardcodes `<link rel="shortcut icon" href="./favicon.png">`,
served before the app runs. So `st.set_page_config(page_icon=…)` only swaps the browser-tab
icon post-load via JS, which leaves a Streamlit-logo flash on cold load and a Streamlit icon
in bookmarks. The container images overwrite favicon.png at build time (Containerfile and
Containerfile.demo); this script does the same for a local `uv run` dev venv. Run once after
`uv sync` (re-run after a Streamlit upgrade reinstalls its static assets):

    uv run python scripts/brand_favicon.py
"""

from __future__ import annotations

import shutil
from importlib import util
from pathlib import Path

BRAND = Path(__file__).resolve().parent.parent / "static" / "favicon.png"


def main() -> None:
    if not BRAND.exists():
        raise SystemExit(f"brand favicon missing: {BRAND}")
    spec = util.find_spec("streamlit")
    if spec is None or not spec.origin:
        raise SystemExit("streamlit not installed in this environment")
    target = Path(spec.origin).parent / "static" / "favicon.png"
    shutil.copyfile(BRAND, target)
    print(f"branded favicon → {target}")


if __name__ == "__main__":
    main()
