import json
from pathlib import Path

import pytest

from flagstaff_server.cli import main


@pytest.fixture(autouse=True)
def no_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Neither a developer's environment nor a .env in the working directory may leak in.
    for name in ("FLAGSTAFF_DATABASE_URL", "FLAGSTAFF_REDIS_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_writes_the_openapi_schema_without_any_settings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["openapi"]) == 0

    schema = json.loads(capsys.readouterr().out)
    assert schema["info"]["title"] == "Flagstaff"
    assert "/sdk/stream" in schema["paths"]


def test_writes_the_openapi_schema_to_a_file(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    assert main(["openapi", "--output", str(output)]) == 0

    assert "/projects/{project_key}/flags" in json.loads(output.read_text())["paths"]


def test_refuses_a_blank_key_name_before_reaching_for_the_database(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["create-admin-key", "--name", "  "]) == 2

    assert capsys.readouterr().err == "flagstaff-server create-admin-key: name must not be blank\n"


def test_says_which_setting_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["create-admin-key", "--name", "Release tooling"]) == 2

    assert "database_url" in capsys.readouterr().err


def test_reports_an_unreachable_database_in_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "FLAGSTAFF_DATABASE_URL", "postgresql+asyncpg://flagstaff@127.0.0.1:1/flagstaff"
    )
    monkeypatch.setenv("FLAGSTAFF_REDIS_URL", "redis://127.0.0.1:1/0")

    assert main(["create-admin-key", "--name", "Release tooling"]) == 1

    [line] = capsys.readouterr().err.splitlines()
    assert line.startswith("flagstaff-server create-admin-key: database error:")


def test_needs_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2
    assert "create-admin-key" in capsys.readouterr().err
