"""Keep the README's mermaid block in sync with the canonical diagram source.

`static/flow.mmd` is the single source of truth: the app reads it at runtime
(it ships in the demo container; README.md does not). The README only embeds a
copy so the forge/GitHub renders the diagram inline. This script regenerates
that copy from flow.mmd, between the FLOW_DIAGRAM markers, so the two never
drift.

Usage:
    uv run python scripts/sync_flow_diagram.py          # rewrite README block
    uv run python scripts/sync_flow_diagram.py --check   # exit 1 if out of sync
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MMD = ROOT / "static" / "flow.mmd"
README = ROOT / "README.md"

# Everything between these markers is generated — never hand-edit it.
BLOCK_RE = re.compile(
    r"(?P<start><!-- FLOW_DIAGRAM:START.*?-->\n).*?(?P<end>\n<!-- FLOW_DIAGRAM:END -->)",
    re.DOTALL,
)


def render_readme(readme_text: str, mmd_text: str) -> str:
    """Return *readme_text* with the marked block replaced by *mmd_text*."""
    fenced = f"```mermaid\n{mmd_text}```"
    if not mmd_text.endswith("\n"):
        fenced = f"```mermaid\n{mmd_text}\n```"
    if not BLOCK_RE.search(readme_text):
        raise SystemExit(
            "ERROR: FLOW_DIAGRAM:START/END markers not found in README.md; "
            "cannot sync the diagram block."
        )
    return BLOCK_RE.sub(lambda m: m.group("start") + fenced + m.group("end"), readme_text)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    current = README.read_text()
    updated = render_readme(current, MMD.read_text())

    if current == updated:
        print("README flow diagram is in sync with static/flow.mmd.")
        return 0
    if check:
        print(
            "ERROR: README flow diagram is out of sync with static/flow.mmd.\n"
            "Run: uv run python scripts/sync_flow_diagram.py"
        )
        return 1
    README.write_text(updated)
    print("Updated the README flow diagram block from static/flow.mmd.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
