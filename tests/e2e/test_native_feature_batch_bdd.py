"""Preparation only: explicit final-batch gates; no implicit paid or mutation retries."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.errors import ContentPolicyError, WafRejectionError
from gflow_cli.services.native_characters import create_character_from_images

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/native_feature_batch.feature")


def checkpoint(case):
    safe = {
        key: case[key]
        for key in (
            "voice",
            "character",
            "media",
            "deleteAttempted",
            "completed",
            "unknown",
            "knownHandles",
        )
        if key in case
    }
    fd = os.open(case["output"] / "checkpoint.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(safe, stream)


def remember_failure(case, error):
    # Private inspect-only handles from a typed problem; never retry or delete inferred IDs.
    if hasattr(error, "to_problem_details"):
        problem = error.to_problem_details()
        case["knownHandles"] = {
            key: problem[key]
            for key in (
                "known_media_ids",
                "pending_media_ids",
                "workflow_ids",
                "character_ref",
                "completed_character_refs",
                "phase",
            )
            if key in problem
        }
    case["unknown"] = not isinstance(error, (WafRejectionError, ContentPolicyError))
    checkpoint(case)


def configured(monkeypatch, mode):
    if os.environ.get("GFLOW_CLI_E2E_FINAL_NATIVE_BATCH") != mode:
        pytest.skip("Explicit final native batch feature selection required")
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT")
    values = {key: os.environ.get("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()) or values["PROFILE"] != "pro1":
        pytest.skip("Explicit private pro1 profile/home/project required")
    output = os.environ.get("GFLOW_CLI_E2E_FINAL_NATIVE_OUTPUT", "")
    if not output:
        pytest.skip("Private persistent allowance/checkpoint directory required")
    path = Path(output) / mode
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    case = {"profile": values["PROFILE"], "project": values["RESOURCES_PROJECT"], "output": path}
    if mode != "catalogs":
        fd = os.open(path / "allowance", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("one explicit feature lifecycle; inspect checkpoint before any rerun\n")
    return case


def client(case):
    return FlowApiClient(profile_dir=get_settings().profile_subdir(case["profile"]), headless=False)


@given(
    "a privately configured final native batch with a one-shot TTS allowance", target_fixture="case"
)
def tts_case(monkeypatch):
    if (
        os.environ.get("GFLOW_CLI_E2E_RUN_VIDEO") != "1"
        or os.environ.get("GFLOW_CLI_E2E_RUN_TTS") != "1"
        or os.environ.get("GFLOW_CLI_E2E_TTS_BUDGET") != "1"
    ):
        pytest.skip("TTS and billed-work explicit opt-ins plus one-preview budget required")
    if not os.environ.get("GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA"):
        pytest.skip("Existing privately catalogued decoded image required")
    return configured(monkeypatch, "tts")


@given(
    "a privately configured final native batch with a free synthetic allowance",
    target_fixture="case",
)
def deletion_case(monkeypatch, tmp_path):
    if os.environ.get("GFLOW_CLI_E2E_NATIVE_MEDIA_BUDGET") != "1":
        pytest.skip("One explicitly authorized free synthetic upload required")
    case = configured(monkeypatch, "individual-delete")
    path = tmp_path / "owned-new-clip.mp4"
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=yellow:s=256x256:r=24:d=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0 and path.is_file()
    case["path"] = path
    return case


@given(
    "a privately configured final native batch with explicit read-only permission",
    target_fixture="case",
)
def catalog_case(monkeypatch):
    return configured(monkeypatch, "catalogs")


@when("one saved voice is created, read, bound to an owned character and deleted")
def voice_lifecycle(case):
    async def run():
        async with client(case) as api:
            before = await api.list_saved_voices(case["project"])
            case["originalVoices"] = {row["ref"] for row in before["voices"]}
            voice = await api.create_saved_voice(
                project_id=case["project"],
                display_name="Owned final TTS test",
                preset_voice="Charon",
                dialog="This is an explicitly authorized voice test.",
                performance="Speak calmly at an ordinary pace.",
            )
            case["voice"] = voice["ref"]
            checkpoint(case)
            assert case["voice"] not in case["originalVoices"]
            detail = await api.get_saved_voice(case["project"], case["voice"])
            assert detail["ref"] == case["voice"]
        character = await create_character_from_images(
            profile=case["profile"],
            project_id=case["project"],
            display_name="Owned final voice binding test",
            image_reference_1=os.environ["GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA"],
            voice=case["voice"],
        )
        case["character"] = character.entity_id
        checkpoint(case)
        async with client(case) as api:
            fetched = await api.get_character(case["project"], entity_id=case["character"])
            assert fetched.voice == case["voice"]
            case["deleteAttempted"] = "character"
            checkpoint(case)
            await api.delete_characters(case["project"], [case["character"]])
            case["deleteAttempted"] = "voice"
            checkpoint(case)
            await api.delete_saved_voice(
                project_id=case["project"],
                voice_id=case["voice"],
                confirm_delete=True,
            )
            after = await api.list_saved_voices(case["project"])
            remaining = {row["ref"] for row in after["voices"]}
            assert case["voice"] not in remaining
            assert case["originalVoices"] <= remaining
            originals = await api.list_native_media(case["project"])
            assert os.environ["GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA"] in {
                row["media_id"] for row in originals["media"]
            }
            case["completed"] = True
            checkpoint(case)

    try:
        asyncio.run(run())
    except BaseException as error:
        remember_failure(case, error)
        raise


@when("one synthetic clip is uploaded and permanently deleted by its exact media identity")
def permanent_delete(case):
    async def run():
        async with client(case) as api:
            before = await api.list_native_media(case["project"])
            case["originalMedia"] = {row["media_id"] for row in before["media"]}
            uploaded = await api.upload_native_video(
                project_id=case["project"],
                path=case["path"],
                rights_confirmed=True,
            )
            case["media"] = uploaded["media_id"]
            checkpoint(case)
            assert case["media"] not in case["originalMedia"]
            case["deleteAttempted"] = "media"
            checkpoint(case)
            deleted = await api.delete_native_media(
                project_id=case["project"],
                media_ids=[case["media"]],
                confirm_delete=True,
            )
            assert deleted["deleted"] == [case["media"]]
            # Empty delete acknowledgement precedes native timeline propagation.
            # Poll reads only; never repeat the mutation to force visibility.
            for attempt in range(11):
                after = await api.list_native_media(case["project"])
                remaining = {row["media_id"] for row in after["media"]}
                assert case["originalMedia"] <= remaining
                if case["media"] not in remaining:
                    break
                if attempt < 10:
                    await asyncio.sleep(2)
            assert case["media"] not in remaining
            case["completed"] = True
            checkpoint(case)

    try:
        asyncio.run(run())
    except BaseException as error:
        remember_failure(case, error)
        raise


@when("native extension and edit model catalogs are read")
def read_catalogs(case):
    async def run():
        async with client(case) as api:
            case["extensionModels"] = await api.list_native_extension_models(case["project"])
            case["editModels"] = await api.list_native_video_edit_models(case["project"])

    asyncio.run(run())


@then("only the acknowledged test voice and character have been removed")
@then("every original active media identity remains active")
def completed(case):
    assert case["completed"] is True


@then("both model catalogs contain observed model identities")
def catalogs(case):
    assert case["extensionModels"] and case["editModels"]
    assert all(row.get("model_key") for row in case["extensionModels"] + case["editModels"])


@given(
    parsers.parse('a privately configured count-one Auto image allowance for "{surface}"'),
    target_fixture="case",
)
def auto_case(monkeypatch, surface):
    if os.environ.get("GFLOW_CLI_E2E_AUTO_SURFACE") != surface:
        pytest.skip("Explicit coordinated count-one Auto adapter required")
    if os.environ.get("GFLOW_CLI_E2E_IMAGE_BUDGET") != "1":
        pytest.skip("Count-one image authorization required")
    reference = os.environ.get("GFLOW_CLI_E2E_AUTO_LOCAL_REFERENCE", "")
    allowance_root = os.environ.get("GFLOW_CLI_E2E_IMAGE_ALLOWANCE_ROOT", "")
    if not reference or not allowance_root:
        pytest.skip("Private verified local reference and shared maximum-three allowance required")
    # Resolve and decode input before consuming any billing allowance.
    from gflow_cli.services.image_aspect import resolve_image_aspect

    _, decision = resolve_image_aspect("auto", [Path(reference)])
    case = configured(monkeypatch, "auto")
    case.update(surface=surface, reference=reference, decision=decision)
    if surface == "MCP":
        case["url"] = os.environ.get("GFLOW_MCP_E2E_URL", "")
        case["token"] = os.environ.get("GFLOW_DAEMON_TOKEN", "")
        if not case["url"] or not case["token"]:
            pytest.skip("Actual registered MCP URL and private bearer required")
    root = Path(allowance_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for slot in range(1, 4):
        try:
            fd = os.open(root / ("image-" + str(slot)), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w") as stream:
            stream.write("one Auto " + surface + " request; never replay\n")
        break
    else:
        pytest.skip("Global additional three-image allowance exhausted")
    return case


@when(parsers.parse('the "{surface}" adapter submits one local-reference Auto image'))
def auto_generate(case, surface):
    output = case["output"] / ("auto-" + surface.lower() + ".jpg")
    prompt = "Create a calm landscape inspired by this reference."
    if surface == "CLI":
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "gflow_cli.cli",
                "image",
                "i2i",
                prompt,
                "--ref",
                case["reference"],
                "--aspect",
                "auto",
                "--model",
                "nano2",
                "--count",
                "1",
                "--project",
                case["project"],
                "--profile",
                case["profile"],
                "--output",
                str(output),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=360,
            check=False,
        )
        value = json.loads(process.stdout)
        case["unknown"] = process.returncode != 0
        checkpoint(case)
        assert process.returncode == 0 and value["status"] == "ok"
        case["files"] = [value["images"][0]["local_path"]]
    else:

        async def invoke():
            async with httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + case["token"]},
                timeout=360,
                trust_env=False,
            ) as http:
                async with streamable_http_client(case["url"], http_client=http) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()
                        result = await asyncio.wait_for(
                            session.call_tool(
                                "gflow_generate_image",
                                {
                                    "prompt": prompt,
                                    "model": "nano2",
                                    "count": 1,
                                    "aspect": "auto",
                                    "reference_images": [case["reference"]],
                                    "profile": case["profile"],
                                    "project": case["project"],
                                    "output": str(output),
                                    "wait": True,
                                },
                            ),
                            timeout=360,
                        )
                        value = result.structured_content
                        if value is None:
                            value = json.loads(
                                next(item.text for item in result.content if item.type == "text")
                            )
                        case["unknown"] = result.is_error is True
                        checkpoint(case)
                        assert result.is_error is not True
                        return value

        value = asyncio.run(invoke())
        assert value["status"] == "completed"
        case["files"] = value["files"]
    case["result"] = value


@then("one image decodes with the derived aspect metadata")
def auto_decoded(case):
    assert len(case["files"]) == 1
    with Image.open(case["files"][0]) as image:
        image.load()
        assert image.width > 0 and image.height > 0
    result = case["result"]
    assert result["requestedAspectRatio"] == "auto"
    assert result["resolvedAspectRatio"] == case["decision"].resolved_aspect
    assert result["aspectPolicy"] == case["decision"].policy
