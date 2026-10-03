"""Cookie input stays in files; adapters expose safe metadata only."""

from __future__ import annotations

import json

from click.testing import CliRunner

from gflow_cli.cli import main
from gflow_cli.selfhost.profile_import import ImportedProfile

P = "11111111-1111-4111-8111-111111111111"


def test_cookie_import_cli_dispatches_without_echoing_credentials(monkeypatch, tmp_path):
    from gflow_cli import cli_auth_import as module

    source = tmp_path / "cookies.tsv"
    source.write_text("SID\tprivate-test-value\t.google.com\t/\tSession")
    seen = []

    async def imported(table, profile, **kwargs):
        seen.append((table.count, profile, kwargs))
        return ImportedProfile(profile, "operator@example.test", P, table.count)

    monkeypatch.setattr(module, "import_cookie_profile", imported)
    result = CliRunner().invoke(
        main,
        [
            "auth",
            "import-cookies",
            "--cookies-file",
            str(source),
            "--profile",
            "new",
            "--project",
            P,
            "--expected-email",
            "operator@example.test",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["profile"] == "new"
    assert data["projectId"] == P
    assert data["cookieCount"] == 1
    assert "private-test-value" not in result.output
    assert seen == [(1, "new", {"expected_email": "operator@example.test", "project_id": P})]


def test_cookie_import_cli_rejects_ambiguous_table_before_browser(monkeypatch, tmp_path):
    from gflow_cli import cli_auth_import as module

    source = tmp_path / "cookies.tsv"
    source.write_text("private-test-value\tnot-valid")

    async def forbidden(*args, **kwargs):
        raise AssertionError("Browser should not start")

    monkeypatch.setattr(module, "import_cookie_profile", forbidden)
    result = CliRunner().invoke(
        main,
        ["auth", "import-cookies", "--cookies-file", str(source), "--profile", "new", "--json"],
    )
    assert result.exit_code == 11
    assert "private-test-value" not in result.output


def test_cookie_import_cli_refuses_symlink_input(monkeypatch, tmp_path):
    from gflow_cli import cli_auth_import as module

    original = tmp_path / "private.tsv"
    original.write_text("SID\tprivate-test-value\t.google.com\t/\tSession")
    linked = tmp_path / "link.tsv"
    linked.symlink_to(original)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Browser should not start")

    monkeypatch.setattr(module, "import_cookie_profile", forbidden)
    result = CliRunner().invoke(
        main,
        ["auth", "import-cookies", "--cookies-file", str(linked), "--profile", "new", "--json"],
    )
    assert result.exit_code == 11
    assert "private-test-value" not in result.output


def test_nonregular_cookie_file_is_refused_before_open(monkeypatch, tmp_path):
    import os

    import pytest

    from gflow_cli import cli_auth_import as module
    from gflow_cli.errors import ConfigurationError

    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO is POSIX-only")
    source = tmp_path / "cookies.fifo"
    os.mkfifo(source)
    original_open = os.open

    def never_open_fifo(path, *args, **kwargs):
        if path == source:
            pytest.fail("Nonregular credentials must be refused before opening")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", never_open_fifo)
    with pytest.raises(ConfigurationError):
        module._read_table(source)
