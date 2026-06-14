import json

import pytest

from services import recorder


def test_fixture_path(mocker, tmp_path):
    mocker.patch("config.settings.settings.fixtures_dir", tmp_path)
    assert recorder.fixture_path("test") == tmp_path / "test.json"


def test_load_fixture_success(mocker, tmp_path):
    mocker.patch("config.settings.settings.fixtures_dir", tmp_path)

    file_path = tmp_path / "test_data.json"
    file_path.write_text('{"mock": "data"}')

    data = recorder.load_fixture("test_data")
    assert data == {"mock": "data"}


def test_load_fixture_not_found(mocker, tmp_path):
    mocker.patch("config.settings.settings.fixtures_dir", tmp_path)

    with pytest.raises(FileNotFoundError) as exc:
        recorder.load_fixture("missing")
    assert "Demo fixture" in str(exc.value)


def test_save_fixture(mocker, tmp_path):
    mocker.patch("config.settings.settings.fixtures_dir", tmp_path)

    test_data = {"key": "value"}
    recorder.save_fixture("new_fixture", test_data)

    file_path = tmp_path / "new_fixture.json"
    assert file_path.exists()

    saved_data = json.loads(file_path.read_text())
    assert saved_data == test_data
