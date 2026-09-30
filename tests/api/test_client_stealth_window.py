"""Tests for stealth_window configuration and launch args."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import Settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_stealth_window_default_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that stealth_window defaults to True and passes off-screen launch args."""
    monkeypatch.delenv("GFLOW_CLI_STEALTH_WINDOW", raising=False)
    settings = Settings(_env_file=None)
    assert settings.stealth_window is True

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" in args
    assert "--no-focus-on-init" in args


def test_stealth_window_disabled_explicitly(tmp_path: Path) -> None:
    """Verify that setting stealth_window=False omits off-screen launch args."""
    settings = Settings(stealth_window=False)
    assert settings.stealth_window is False

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" not in args
    assert "--no-focus-on-init" not in args


def test_stealth_window_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that GFLOW_CLI_STEALTH_WINDOW=0 disables the stealth launch args."""
    monkeypatch.setenv("GFLOW_CLI_STEALTH_WINDOW", "0")
    settings = Settings()
    assert settings.stealth_window is False

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" not in args
    assert "--no-focus-on-init" not in args
