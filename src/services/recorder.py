"""Record/replay store for demo mode.

Fixtures are plain JSON files in settings.fixtures_dir. The demo container
ships with pre-recorded fixtures; the demo app reads them back with demo_mode
enabled so the application code above this layer stays unaware of which mode
it is running in.
"""

import json
from pathlib import Path

from config.settings import settings


def fixture_path(name: str) -> Path:
    return settings.fixtures_dir / f"{name}.json"


def load_fixture(name: str):
    path = fixture_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Demo fixture '{path}' is missing. "
            "Record one by running scripts/record_demo.py after scoring jobs in the main app."
        )
    return json.loads(path.read_text())


def save_fixture(name: str, data) -> None:
    path = fixture_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(path)
