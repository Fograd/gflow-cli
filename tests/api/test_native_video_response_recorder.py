"""Offline paid-test recorder policy; no browser or Google requests."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.config import BrowserEngine

spec = importlib.util.spec_from_file_location(
    "native_video_final_bdd", Path(__file__).parents[1] / "e2e/test_native_video_paths_final_bdd.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [BrowserEngine.PATCHRIGHT, BrowserEngine.PLAYWRIGHT])
async def test_recorder_uses_selected_engine_and_forwards_context_once(
    monkeypatch, tmp_path, engine
):
    if engine == BrowserEngine.PATCHRIGHT:
        from patchright.async_api import Page
    else:
        from playwright.async_api import Page
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(browser_engine=engine))
    result = {"status": 200, "text": "synthetic-response"}
    original = AsyncMock(return_value=result)
    monkeypatch.setattr(Page, "evaluate", original)
    case = {"out": tmp_path}
    module.install_response_recorder(case, monkeypatch)
    page = object()
    arg = {"rpc": "MZZa6b", "token": "do-not-persist", "args": ["private-request"]}
    kwargs = {"isolated_context": False} if engine == BrowserEngine.PATCHRIGHT else {}
    assert await Page.evaluate(page, "page-owned-expression", arg=arg, **kwargs) is result
    original.assert_awaited_once_with(page, "page-owned-expression", arg=arg, **kwargs)
    saved = json.loads((tmp_path / "rpc-response-01-MZZa6b.json").read_text())
    assert saved == {"rpc": "MZZa6b", **result}
    assert "do-not-persist" not in json.dumps(saved)


@pytest.mark.asyncio
async def test_recorder_capture_failure_never_replays_accepted_request(monkeypatch, tmp_path):
    from playwright.async_api import Page

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(browser_engine=BrowserEngine.PLAYWRIGHT)
    )
    original = AsyncMock(return_value={"status": 200, "text": "accepted"})
    monkeypatch.setattr(Page, "evaluate", original)
    (tmp_path / "rpc-response-01-MZZa6b.json").touch()
    case = {"out": tmp_path}
    module.install_response_recorder(case, monkeypatch)
    assert (await Page.evaluate(object(), "expr", {"rpc": "MZZa6b"}))["text"] == "accepted"
    original.assert_awaited_once()
    assert case["responseRecorderIncomplete"] is True


def test_reference_case_accepts_preset_but_keeps_exact_image_and_character_ids(
    monkeypatch, tmp_path
):
    project = "11111111-1111-4111-8111-111111111111"
    image = "22222222-2222-4222-8222-222222222222"
    character = "33333333-3333-4333-8333-333333333333"
    monkeypatch.setenv("GFLOW_CLI_E2E_RUN_VIDEO", "1")
    monkeypatch.setenv("GFLOW_CLI_E2E_NATIVE_VIDEO_BUDGET", "1")
    monkeypatch.setenv("GFLOW_CLI_E2E_NATIVE_VIDEO_IMAGES", json.dumps([image]))
    monkeypatch.setenv("GFLOW_CLI_E2E_NATIVE_VIDEO_CHARACTERS", json.dumps([character]))
    monkeypatch.setenv("GFLOW_CLI_E2E_NATIVE_VIDEO_AUDIO", json.dumps(["voices/kore"]))
    monkeypatch.setattr(module.shutil, "which", lambda name: "/fixture/ffprobe")
    monkeypatch.setattr(
        module,
        "configure",
        lambda *args: {
            "out": tmp_path,
            "project": project,
            "record": {},
        },
    )
    case = module.video_case(monkeypatch, "reference")
    assert case["audio"] == ("Kore",)
    assert case["images"] == (image,) and case["characters"] == (character,)
