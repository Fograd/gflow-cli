"""Final-batch preparation: one explicit output per path, no mutation replay."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.errors import ContentPolicyError, WafRejectionError

pytestmark = [pytest.mark.e2e]
scenarios("../features/native_video_paths_final.feature")


def private_checkpoint(case, **changes):
    case["record"].update(changes)
    fd = os.open(case["out"] / "checkpoint.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(case["record"], stream)
        stream.flush()
        os.fsync(stream.fileno())


def install_response_recorder(case, monkeypatch):
    """Record actual generation responses privately; never record request arguments."""
    from playwright.async_api import Page

    original = Page.evaluate
    selected = {"no0P6", "MZZa6b", "fZytfe", "jIps6"}
    sequence = 0

    async def evaluate(page, expression, arg=None):
        nonlocal sequence
        result = await original(page, expression, arg=arg)
        if isinstance(arg, dict) and arg.get("rpc") in selected:
            sequence += 1
            # Only response fields: never persist expression, args, headers or tokens.
            record = {
                "rpc": arg["rpc"],
                "status": result.get("status") if isinstance(result, dict) else None,
                "text": result.get("text") if isinstance(result, dict) else None,
            }
            path = case["out"] / f"rpc-response-{sequence:02d}-{arg['rpc']}.json"
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as stream:
                    json.dump(record, stream)
            except OSError:
                # The test can report capture trouble, but never turn an accepted
                # operation into a transport failure or repeat its evaluation.
                case["responseRecorderIncomplete"] = True
        return result

    monkeypatch.setattr(Page, "evaluate", evaluate)


def configure(monkeypatch, mode):
    if os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_PATH") != mode:
        pytest.skip("Select exactly one explicit native video path")
    required = ("PROFILE", "HOME", "RESOURCES_PROJECT", "NATIVE_VIDEO_OUTPUT")
    env = {key: os.environ.get("GFLOW_CLI_E2E_" + key, "") for key in required}
    if not all(env.values()):
        pytest.skip("Private profile/home/project/persistent output configuration required")
    project = str(UUID(env["RESOURCES_PROJECT"]))
    out = Path(env["NATIVE_VIDEO_OUTPUT"]) / mode
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.chmod(0o700)
    monkeypatch.setenv("GFLOW_CLI_HOME", env["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    case = {
        "profile": env["PROFILE"],
        "project": project,
        "out": out,
        "mode": mode,
        "record": {"mode": mode, "completed": False, "submitted": False},
    }
    install_response_recorder(case, monkeypatch)
    return case


@given(
    parsers.parse('a private one-shot native video allowance for "{mode}"'), target_fixture="case"
)
def video_case(monkeypatch, mode):
    if (
        os.environ.get("GFLOW_CLI_E2E_RUN_VIDEO") != "1"
        or os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_BUDGET") != "1"
    ):
        pytest.skip("Explicit paid-video opt-in and one-output budget required")
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is required before any paid request")
    case = configure(monkeypatch, mode)
    if mode in {"extension", "edit"}:
        source = os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_SOURCE", "")
        if not source:
            pytest.skip("Exact existing owned source video UUID required")
        case["source"] = str(UUID(source))
    if mode == "edit":
        end = os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_END_FRAME", "")
        if not end:
            pytest.skip("Explicit known clip end-frame required; no guessed duration")
        case["end_frame"] = int(end)
        assert 1 <= case["end_frame"] <= 240
    if mode == "audio-reference":
        if (
            os.environ.get("GFLOW_CLI_E2E_RUN_TTS") != "1"
            or os.environ.get("GFLOW_CLI_E2E_TTS_BUDGET") != "1"
        ):
            pytest.skip("Exactly one explicitly allowed TTS preview required")
        image = os.environ.get("GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA", "")
        if not image:
            pytest.skip("Existing privately catalogued owned image UUID required")
        case["images"], case["audio"] = (str(UUID(image)),), ()
    elif mode == "reference":
        case["images"] = tuple(
            str(UUID(x))
            for x in json.loads(os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_IMAGES", "[]"))
        )
        case["audio"] = tuple(
            str(UUID(x))
            for x in json.loads(os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_AUDIO", "[]"))
        )
        if not case["images"] and not case["audio"]:
            pytest.skip("Exact existing owned ingredients required")
        assert len(case["images"]) <= 7 and len(case["audio"]) <= 5
    # Persistent one-shot allowance refuses any accidental retry, even after a failure.
    fd = os.open(case["out"] / "allowance", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("one output; inspect checkpoint before any new allowance\n")
    private_checkpoint(case)
    return case


@given("a private read-only native reference catalog configuration", target_fixture="case")
def catalog_case(monkeypatch):
    return configure(monkeypatch, "catalogs")


def api(case):
    return FlowApiClient(profile_dir=get_settings().profile_subdir(case["profile"]), headless=False)


@when("the selected native video path submits once using a discovered model")
def generate(case):
    async def run():
        async with api(case) as client:
            mode = case["mode"]
            if mode == "extension":
                models = await client.list_native_extension_models(case["project"])
            elif mode == "edit":
                models = await client.list_native_video_edit_models(case["project"])
            else:
                models = await client.list_native_reference_video_models(
                    case["project"], with_audio=bool(case["audio"])
                )
            assert models, "Native catalog returned no usable model; nothing submitted"
            requested = os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_MODEL_KEY", "")
            candidates = [row for row in models if not requested or row["model_key"] == requested]
            assert candidates, "Requested key is not present in the observed catalog"
            if mode in {"reference", "audio-reference"}:
                candidates = [
                    row
                    for row in candidates
                    if type(row.get("max_images")) is int
                    and len(case["images"]) <= row["max_images"]
                    and (
                        not case["audio"]
                        or (
                            type(row.get("max_audio")) is int
                            and len(case["audio"]) <= row["max_audio"]
                        )
                    )
                    and 2 in (row.get("aspect_enums") or [])
                ]
                assert candidates, "Observed model limits do not fit supplied ingredients"
            model = min(candidates, key=lambda row: row["credits"])
            private_checkpoint(case, modelKey=model["model_key"])

            async def started(value):
                private_checkpoint(
                    case,
                    submitted=True,
                    project_id=value.project_id,
                    media_ids=list(value.media_ids),
                    workflow_ids=list(value.workflow_ids),
                )

            prompt = "Continue the gentle camera movement."
            if mode == "extension":
                value = await client.extend_native_video(
                    project_id=case["project"],
                    media_id=case["source"],
                    prompt=prompt,
                    model_key=model["model_key"],
                    count=1,
                    on_started=started,
                )
                records = await client.wait_native_extension(value, timeout_s=600)
            elif mode == "edit":
                value = await client.edit_native_video(
                    project_id=case["project"],
                    media_id=case["source"],
                    prompt="Add a soft cinematic atmosphere.",
                    model_key=model["model_key"],
                    end_frame=case["end_frame"],
                    on_started=started,
                )
                records = await client.wait_native_video_edit(value)
            else:
                prompt = "Animate this scene calmly."
                if case["images"]:
                    prompt += " Use @referenceImage_1."
                if case["audio"]:
                    prompt += " Match @referenceAudio_1."
                value = await client.generate_native_reference_video(
                    project_id=case["project"],
                    prompt=prompt,
                    reference_image_ids=case["images"],
                    reference_audio_ids=case["audio"],
                    model_key=model["model_key"],
                    count=1,
                    aspect="16:9",
                    on_started=started,
                )
                records = await client.wait_native_reference_video(value, timeout_s=600)
            assert len(records) == 1 and records[0].media_id == value.media_ids[0]
            assert (
                records[0].workflow_id == value.workflow_ids[0]
                and records[0].project_id == case["project"]
            )
            assert records[0].video_url is not None
            path = case["out"] / (records[0].media_id + ".mp4")
            await client.download(records[0].video_url, path)
            case["path"] = path
            private_checkpoint(case, downloaded=True)

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=900))
    except BaseException as error:
        safe = {}
        if hasattr(error, "to_problem_details"):
            problem = error.to_problem_details()
            safe = {
                key: problem[key]
                for key in (
                    "media_ids",
                    "workflow_ids",
                    "media_id",
                    "workflow_id",
                    "character_ref",
                    "project_id",
                    "phase",
                    "outcome_unknown",
                )
                if key in problem
            }
        private_checkpoint(
            case,
            unknown=not isinstance(error, (WafRejectionError, ContentPolicyError)),
            refusal=type(error).__name__
            if isinstance(error, (WafRejectionError, ContentPolicyError))
            else None,
            knownHandles=safe,
        )
        raise


@then("exactly one assigned video decodes and its checkpoint is complete")
def decoded(case):
    path = case["path"]
    assert path.is_file() and path.stat().st_size > 0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    streams = json.loads(result.stdout)["streams"]
    assert len(streams) == 1 and streams[0]["width"] > 0 and streams[0]["height"] > 0
    private_checkpoint(case, completed=case["mode"] != "audio-reference", decoded=True)


@when("reference model catalogs and native credits are read once")
def catalog_read(case):
    async def run():
        async with api(case) as client:
            case["models"] = await client.list_native_reference_video_models(case["project"])
            case["audioModels"] = await client.list_native_reference_video_models(
                case["project"], with_audio=True
            )
            case["credits"] = await client.get_credits()

    asyncio.run(asyncio.wait_for(run(), timeout=120))


@then("observed native model identities and a nonnegative credit balance are returned")
def catalog_results(case):
    assert case["models"] and case["audioModels"]
    assert all(row["model_key"] for row in case["models"] + case["audioModels"])
    assert type(case["credits"].credits) is int and case["credits"].credits >= 0
    private_checkpoint(case, completed=True, catalogsRead=True)


@given("a private one-shot native audio-reference lifecycle allowance", target_fixture="case")
def audio_reference_case(monkeypatch):
    return video_case(monkeypatch, "audio-reference")


@when("one TTS voice is saved, read and bound to an acknowledged test character")
def create_audio_and_character(case):
    from gflow_cli.services.native_characters import create_character_from_images

    async def run():
        async with api(case) as client:
            before = await client.list_saved_voices(case["project"])
            case["originalVoices"] = {row["ref"] for row in before["voices"]}
            before_media = await client.list_native_media(case["project"])
            case["originalMedia"] = {row["media_id"] for row in before_media["media"]}
            assert case["images"][0] in case["originalMedia"]
            # Exactly one TTS create: saved audio ref is the acknowledged native media UUID.
            voice = await client.create_saved_voice(
                project_id=case["project"],
                display_name="Owned final audio-reference test",
                preset_voice="Charon",
                dialog="A calm camera moves gently through this scene.",
                performance="Speak calmly at an ordinary pace.",
            )
            case["voice"] = voice["ref"]
            case["audio"] = (voice["ref"],)
            private_checkpoint(case, voice=voice["ref"], ttsPreviewUsed=True)
            assert voice["ref"] not in case["originalVoices"]
            fetched = await client.get_saved_voice(case["project"], voice["ref"])
            assert fetched["ref"] == voice["ref"]
        character = await create_character_from_images(
            profile=case["profile"],
            project_id=case["project"],
            display_name="Owned final audio binding test",
            image_reference_1=case["images"][0],
            voice=case["voice"],
        )
        case["character"] = character.entity_id
        private_checkpoint(case, character=character.entity_id)
        async with api(case) as client:
            fetched = await client.get_character(case["project"], entity_id=character.entity_id)
            assert fetched.voice == case["voice"]
            private_checkpoint(case, voiceBindingVerified=True)

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=600))
    except BaseException as error:
        safe = {}
        if hasattr(error, "to_problem_details"):
            problem = error.to_problem_details()
            safe = {
                key: problem[key]
                for key in (
                    "media_id",
                    "workflow_id",
                    "character_ref",
                    "completed_character_refs",
                    "phase",
                    "outcome_unknown",
                )
                if key in problem
            }
        private_checkpoint(
            case,
            unknown=not isinstance(error, (WafRejectionError, ContentPolicyError)),
            refusal=type(error).__name__
            if isinstance(error, (WafRejectionError, ContentPolicyError))
            else None,
            knownHandles=safe,
        )
        raise


@then("only the acknowledged test voice and character are deleted after video success")
def cleanup_acknowledged_audio_fixture(case):
    assert case["record"].get("decoded") is True and case["path"].is_file()
    assert case["voice"] not in case["originalVoices"]

    async def run():
        async with api(case) as client:
            private_checkpoint(case, deleteAttempted="character")
            await client.delete_characters(case["project"], [case["character"]])
            private_checkpoint(case, characterDeleted=True, deleteAttempted="voice")
            await client.delete_saved_voice(
                project_id=case["project"], voice_id=case["voice"], confirm_delete=True
            )
            voices = await client.list_saved_voices(case["project"])
            remaining = {row["ref"] for row in voices["voices"]}
            assert case["voice"] not in remaining
            assert case["originalVoices"] <= remaining
            media = await client.list_native_media(case["project"])
            assert case["originalMedia"] <= {row["media_id"] for row in media["media"]}
            assert case["images"][0] in {row["media_id"] for row in media["media"]}
            private_checkpoint(case, voiceDeleted=True, originalsPreserved=True, completed=True)

    # No finally-cleanup: an unknown create/generation/download outcome leaves the
    # private checkpoint for inspection instead of attempting another mutation.
    asyncio.run(asyncio.wait_for(run(), timeout=120))
