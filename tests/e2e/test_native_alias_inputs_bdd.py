"""Opt-in actual Flow reads/download and REST forwarding; workers remain disabled."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

scenarios("../features/native_alias_inputs.feature")


def require(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


@given(
    "an opted-in existing owned image and a REST server with workers disabled",
    target_fixture="case",
)
def configured(tmp_path, monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_ALIAS_INPUTS") != "1":
        pytest.skip("Explicit real-read/download alias-input opt-in required")
    project = os.getenv("GFLOW_CLI_E2E_ALIAS_INPUT_PROJECT", "")
    media = os.getenv("GFLOW_CLI_E2E_ALIAS_INPUT_IMAGE", "")
    profile = os.getenv("GFLOW_CLI_E2E_ALIAS_INPUT_PROFILE", "")
    require(bool(project and media and profile), "Owned image fixture is required")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    require(bool(home), "Explicit authenticated profile home is required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    environment = Settings.environment()
    require(profile in environment.accounts, "Explicit profile must be configured")
    account = environment.accounts[profile]["email"]
    cfg = replace(
        environment,
        root=tmp_path,
        token=uuid4().hex,
        accounts={profile: {"email": account, "project": project}},
    )
    alias = "user:bdd_" + uuid4().hex + "-email:opaque-image:" + media
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield {
            "client": client,
            "headers": {"Authorization": "Bearer " + cfg.token},
            "account": account,
            "profile": profile,
            "project": project,
            "media": media,
            "alias": alias,
            "root": tmp_path,
        }


@when("its exact alias is registered and submitted as a video start frame")
def register_and_submit(case):
    client = case["client"]
    response = client.post(
        "/v1/google-flow/assets/" + case["account"] + "/aliases",
        headers=case["headers"],
        json={
            "alias": case["alias"],
            "mediaGenerationId": case["media"],
            "projectId": case["project"],
            "kind": "image",
        },
    )
    require(response.status_code == 201, "Fresh owned alias registration failed")
    response = client.post(
        "/v1/google-flow/videos",
        headers=case["headers"],
        json={
            "prompt": "A steady camera observing the existing blue vase.",
            "startImage": case["alias"],
            "model": "omni-flash",
            "duration": 4,
            "resolution": "360p",
            "count": 1,
            "async": True,
        },
    )
    require(response.status_code == 201, "Alias video forwarding failed")
    case["response"] = response.json()


@then("fresh downloaded image bytes and a canonical scoped job exist without generation")
def verify(case):
    store = case["client"].app.state.store
    job = store.claim(case["profile"])
    require(job is not None, "Expected exactly one local queued job")
    payload = json.loads(job["payload"])
    require(
        payload["startImage"] == case["media"]
        and payload["projectId"] == case["project"]
        and payload["email"] == case["account"],
        "Queued video must preserve exact canonical scope",
    )
    require(
        "https://" not in json.dumps(payload) and case["alias"] not in json.dumps(payload),
        "Queue must not persist a signed URL or unnormalized alias",
    )
    require(store.claim(case["profile"]) is None, "No additional job should exist")
    row = store.asset_get(case["media"])
    path = Path(row["path"])
    require(
        row["profile"] == case["profile"]
        and row["project"] == case["project"]
        and row["mime"] in {"image/png", "image/jpeg"}
        and path.is_relative_to(case["root"])
        and 0 < path.stat().st_size <= 20 * 1024 * 1024,
        "Managed image cache must preserve validated local scope",
    )
    with Image.open(path) as image:
        require(image.size == (1024, 1024), "Existing blue-vase fixture dimensions changed")
        image.verify()
    # Workers were never started: this claim only inspects local queue translation.


@given(
    "an opted-in one-shot video budget and an acknowledged owned character fixture",
    target_fixture="video_case",
)
def video_configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_ALIAS_VIDEO") != "1":
        pytest.skip("Explicit reserved count1 video allowance required")
    root = Path(os.getenv("GFLOW_CLI_E2E_ALIAS_VIDEO_ROOT", ""))
    fixture = Path(os.getenv("GFLOW_CLI_E2E_ALIAS_VIDEO_FIXTURE", ""))
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    require(
        root.is_absolute() and fixture.is_file() and bool(home),
        "Private fixture configuration required",
    )
    data = json.loads(fixture.read_text())
    require(
        data["phase"] == "created" and data["verified"] is True, "Acknowledged fixture required"
    )
    require(
        data["account"] == "pro1"
        and data["model"]["model_key"] == "abra_r2v_4s_360p"
        and data["model"]["credits"] == 4,
        "Fresh cheapest reference model required",
    )
    checkpoint = root / "checkpoint.json"
    require(
        not checkpoint.exists(), "One-shot video checkpoint already exists; inspect before retrying"
    )
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    env = Settings.environment()
    account = env.accounts["pro1"]["email"]
    cfg = replace(
        env,
        root=root / "api",
        token=uuid4().hex,
        accounts={"pro1": {"email": account, "project": data["project"]}},
        allow_video=True,
    )
    # Private native workers resolve supplied-token files against this isolated API root.
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(cfg.root))
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield {
            "client": client,
            "headers": {"Authorization": "Bearer " + cfg.token},
            "account": account,
            "cfg": cfg,
            "fixture": data,
            "checkpoint": checkpoint,
        }


@when("verified image and character aliases plus a preset voice are submitted once")
def video_submit(video_case, monkeypatch):
    from gflow_cli.selfhost import runtime
    from gflow_cli.selfhost.runtime import execute, parse_json_output

    child_diagnostic = {}
    real_subprocess = runtime.subprocess_run

    async def observe_subprocess(args, timeout, **kwargs):
        code, raw = await real_subprocess(args, timeout, **kwargs)
        if len(args) > 2 and args[2] == "gflow_cli.selfhost.reference_video_worker":
            child_diagnostic["exit_code"] = code
            try:
                child = parse_json_output(raw)
                for key in ("type", "error_class"):
                    value = child.get(key)
                    if isinstance(value, str) and value.replace("_", "").isalnum():
                        child_diagnostic[key] = value
                error_code = child.get("error", {}).get("code")
                if isinstance(error_code, str) and error_code.replace("_", "").isalnum():
                    child_diagnostic["error_code"] = error_code
            except (ValueError, TypeError, AttributeError):
                pass
        return code, raw

    monkeypatch.setattr(runtime, "subprocess_run", observe_subprocess)
    case = video_case
    data = case["fixture"]
    client = case["client"]
    prefix = "user:bdd_" + uuid4().hex + "-email:opaque-"
    image_alias = prefix + "image:" + data["source"]
    character_alias = prefix + "character:" + data["entity_id"] + "-imgs:1"
    for collection, body in (
        ("assets", {"alias": image_alias, "mediaGenerationId": data["source"], "kind": "image"}),
        ("characters", {"alias": character_alias, "entityId": data["entity_id"]}),
    ):
        response = client.post(
            "/v1/google-flow/" + collection + "/" + case["account"] + "/aliases",
            headers=case["headers"],
            json={**body, "projectId": data["project"]},
        )
        require(response.status_code == 201, "Fresh alias registration failed before submission")
    solver_payload = {}
    solver_stats = None
    if os.getenv("GFLOW_CLI_E2E_ALIAS_VIDEO_SOLVER") == "CapSolver":
        from gflow_cli.api.client import FlowApiClient
        from gflow_cli.api.recaptcha import discover_site_key
        from gflow_cli.config import get_settings
        from gflow_cli.selfhost.captcha import CaptchaStats, ProviderKeys, Solver

        solver_stats = CaptchaStats(case["cfg"].root)
        solver_stats.record("CapSolver", "solveStarted")

        async def solve():
            key = ProviderKeys(Path.home() / ".config/homelab").get("CapSolver")
            require(bool(key), "Configured CapSolver key required")
            async with FlowApiClient(
                profile_dir=get_settings().profile_subdir("pro1"), headless=False
            ) as browser:
                page = await browser._checkout_page()
                try:
                    await page.goto(
                        "https://flow.google.com/project/" + data["project"],
                        wait_until="domcontentloaded",
                    )
                    await page.wait_for_function(
                        """() => [...document.querySelectorAll(
                            'script[src*="recaptcha/enterprise.js"]'
                        )].some(s => /[?&]render=[^&]+/.test(s.src))""",
                        timeout=10000,
                    )
                    sitekey = await discover_site_key(page)
                    solution = await Solver().solve(
                        "CapSolver", key, page.url, sitekey, "VIDEO_GENERATION"
                    )
                    return solution.token
                finally:
                    browser._checkin_page(page)

        try:
            solver_payload["captchaToken"] = asyncio.run(solve())
            solver_stats.record("CapSolver", "solved")
        except Exception as error:
            solver_stats.record("CapSolver", "solveFailed")
            failure = {
                "phase": "solver_failed_before_submit",
                "error_class": type(error).__name__,
                "generation_submitted": False,
            }
            temporary = case["checkpoint"].with_suffix(".tmp")
            temporary.write_text(json.dumps(failure))
            temporary.chmod(0o600)
            temporary.replace(case["checkpoint"])
            pytest.fail("CapSolver failed before native video submission", pytrace=False)
    response = client.post(
        "/v1/google-flow/videos",
        headers=case["headers"],
        json={
            **solver_payload,
            "prompt": (
                "Animate @referenceImage_3 matching the blue vase in @referenceImage_7. "
                "Use @referenceAudio_1 for a brief spoken greeting."
            ),
            "referenceImage_3": character_alias,
            "referenceImage_7": image_alias,
            "referenceAudio_1": "Charon",
            "model": "omni-flash",
            "modelKey": data["model"]["model_key"],
            "duration": 4,
            "resolution": "360p",
            "count": 1,
            "async": True,
        },
    )
    require(response.status_code == 201, "Native alias video admission failed")
    store = client.app.state.store
    job = store.claim("pro1")
    require(job is not None and job["kind"] == "videos/reference", "Native reference job required")
    payload = json.loads(job["payload"])
    require(
        payload["referenceSlotIds"]["referenceImage_3"] == data["entity_id"]
        and payload["referenceSlotIds"]["referenceImage_7"] == data["source"]
        and payload["referenceSlotIds"]["referenceAudio_1"] == "Charon"
        and payload["project"] == data["project"],
        "Canonical mixed reference slots changed",
    )
    record = {
        "phase": "before_execute",
        "job_id": job["id"],
        "account": "pro1",
        "count": 1,
        "model_key": data["model"]["model_key"],
        "credits": 4,
        "canonical_slots_verified": True,
    }

    def save():
        path = case["checkpoint"]
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record))
        temporary.chmod(0o600)
        temporary.replace(path)

    save()
    if solver_stats is not None:
        solver_stats.record("CapSolver", "submitted")
    try:
        result = asyncio.run(execute(case["cfg"], store, job))
    except Exception:
        record.update(phase="inspect_checkpoint", unknown=True, completed=False)
        save()
        pytest.fail("Video execution outcome requires private checkpoint inspection", pytrace=False)
    state = "failed" if "error" in result else "completed"
    if solver_stats is not None:
        solver_stats.record(
            "CapSolver",
            "unknown"
            if result.get("error", {}).get("outcome_unknown")
            or result.get("error", {}).get("code") == "native_video_operation_failed"
            else "accepted"
            if state == "completed"
            else "rejected",
        )
    store.finish(job["id"], state, result)
    record.update(
        phase="terminal",
        completed=state == "completed",
        result=result,
        unknown=(
            None
            if result.get("error", {}).get("code") == "native_video_operation_failed"
            else result.get("error", {}).get("outcome_unknown", False)
        ),
        refusal=result.get("error", {}).get("code"),
        child_diagnostic=child_diagnostic,
    )
    save()
    case["record"] = record
    case["store"] = store


@then("one native video decodes and the alias-input checkpoint is complete")
def video_verify(video_case):
    record = video_case["record"]
    require(
        record["completed"] is True,
        "Google did not accept the one-shot video; inspect private checkpoint",
    )
    media = record["result"].get("media", [])
    require(len(media) == 1, "Exactly one assigned output required")
    asset = video_case["store"].asset_get(media[0]["mediaGenerationId"])
    path = Path(asset["path"])
    require(path.is_file() and asset["mime"] == "video/mp4", "Managed MP4 required")
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "null", "-"],
        capture_output=True,
        timeout=30,
    )
    require(decoded.returncode == 0, "Assigned video did not decode")
    record["decoded"] = True
    checkpoint = video_case["checkpoint"]
    temporary = checkpoint.with_suffix(".tmp")
    temporary.write_text(json.dumps(record))
    temporary.chmod(0o600)
    temporary.replace(checkpoint)
