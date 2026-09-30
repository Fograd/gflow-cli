"""Tests for stealth_window configuration and launch args."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_stealth_window_default_enabled(tmp_path: Path) -> None:
    settings = Settings()
    assert settings.stealth_window is True

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" in args
    assert "--no-focus-on-init" in args


def test_stealth_window_disabled_explicitly(tmp_path: Path) -> None:
    settings = Settings(stealth_window=False)
    assert settings.stealth_window is False

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" not in args
    assert "--no-focus-on-init" not in args


def test_stealth_window_disabled_via_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GFLOW_CLI_STEALTH_WINDOW", "0")
    settings = Settings()
    assert settings.stealth_window is False

    client = FlowApiClient(profile_dir=tmp_path / "prof", settings=settings)
    kwargs = client._persistent_context_kwargs()
    args = kwargs.get("args") or []

    assert "--window-position=-30000,-30000" not in args
    assert "--no-focus-on-init" not in args
