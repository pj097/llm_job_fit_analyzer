import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_flow_block_in_sync_with_mmd():
    """The README mermaid block must match static/flow.mmd (one source of truth).

    If this fails, run: uv run python scripts/sync_flow_diagram.py
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_flow_diagram.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
