"""Serial profile workers, CLI subprocess isolation and durable callback delivery."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import json
import mimetypes
import os
import signal
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import httpx

from gflow_cli.selfhost.config import (
    MAX_ASSET,
    MODEL_ALIASES,
    VIDEO_ALIASES,
    Settings,
    validate_callback,
)
from gflow_cli.selfhost.store import Store


def parse_json_output(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if not text[end:].strip() and isinstance(value, dict):
            return cast(dict[str, Any], value)
    raise ValueError("CLI did not return a complete JSON result")


def contained_file(path: str, root: Path) -> Path:
    candidate = Path(path).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("Output file is outside the managed directory or missing")
    return candidate


def native_refusal_error(result: dict[str, Any], exit_code: int) -> dict[str, Any] | None:
    """Only exact canonical typed refusals cross the private subprocess boundary."""
    error = result.get("error")
    if not isinstance(error, dict):
        return None
    error = cast(dict[str, Any], error)
    expected = {
        10: ("WafRejectionError", "https://gflow-cli.dev/errors/waf-rejection"),
        5: ("ContentPolicyError", "https://gflow-cli.dev/errors/content-policy"),
        4: ("NativeQuotaError", "https://gflow-cli.dev/errors/native-quota"),
    }.get(exit_code)
    if (
        expected is None
        or error.get("class") != expected[0]
        or error.get("type") != expected[1]
        or error.get("exit_code") != exit_code
        or error.get("outcome_unknown") is True
        or error.get("outcomeUnknown") is True
        or result.get("outcome_unknown") is True
        or result.get("outcomeUnknown") is True
    ):
        return None
    if exit_code == 4:
        from gflow_cli.selfhost.model_quarantine import quota_metadata

        metadata = quota_metadata(error)
        if metadata is None:
            return None
        quota_code = (
            "google_flow_model_access_denied"
            if metadata["nativeReason"] == "PUBLIC_ERROR_MODEL_ACCESS_DENIED"
            else "google_flow_native_quota"
        )
        return {
            "code": quota_code,
            "exit_code": 4,
            "retryable": False,
            "detail": "Google Flow returned a typed native quota or model access refusal.",
            **metadata,
        }
    if exit_code == 5:
        code = "google_flow_content_policy"
        detail = "Google Flow refused this request under its content policy."
    else:
        detail_value = error.get("detail")
        unusual = error.get("reason") == "PUBLIC_ERROR_UNUSUAL_ACTIVITY" or (
            isinstance(detail_value, str) and "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in detail_value
        )
        code = "google_flow_unusual_activity" if unusual else "google_flow_waf_rejection"
        detail = (
            "Google Flow refused this request because of unusual activity."
            if unusual
            else "Google Flow refused this request at its browser protection check."
        )
    return {"code": code, "exit_code": exit_code, "retryable": False, "detail": detail}


async def subprocess_run(
    args: list[str], timeout: int, *, image_recovery_id: str | None = None
) -> tuple[int, bytes]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in (
            "GFLOW_DAEMON_TOKEN",
            "GFLOW_SELFHOST_ACCOUNTS",
            "GFLOW_CAPSOLVER_KEY",
            "GFLOW_2CAPTCHA_KEY",
        )
    }
    env.pop("GFLOW_IMAGE_RECOVERY_ID", None)
    if image_recovery_id is not None:
        env["GFLOW_IMAGE_RECOVERY_ID"] = str(uuid.UUID(image_recovery_id))
    env["GFLOW_CLI_DEBUG_TRACEBACK"] = "0"
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        raise
    return process.returncode or 0, stdout


def image_reference_inputs(
    cfg: Settings, store: Store, profile: str, payload: dict[str, Any], refs: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Revalidate server-owned source records; paths never come from callers."""
    records: object = payload.get("_image_reference_sources")
    if records is None:
        records = [{"id": value, "kind": "managed"} for value in refs]
    if not isinstance(records, list):
        raise ValueError("Image reference source records do not match inputs")
    rows = cast(list[object], records)
    if len(rows) != len(refs):
        raise ValueError("Image reference source records do not match inputs")
    native: list[str] = []
    local_ids: list[str] = []
    paths: list[str] = []
    for identifier, value in zip(refs, rows, strict=True):
        if not isinstance(value, dict):
            raise ValueError("Image reference source record is invalid")
        record = cast(dict[str, Any], value)
        if (
            set(record) != {"id", "kind"}
            or record.get("id") != identifier
            or not isinstance(record.get("kind"), str)
            or record.get("kind") not in {"managed", "native"}
        ):
            raise ValueError("Image reference source record is invalid")
        if record["kind"] == "native":
            if payload.get("email") != cfg.accounts[profile]["email"]:
                raise ValueError("Native references require the selected configured account")
            native.append(identifier)
        else:
            asset = store.asset_get(identifier)
            if asset["profile"] != profile or asset["mime"] not in ("image/png", "image/jpeg"):
                raise ValueError("Managed image reference is not owned by the selected account")
            paths.append(str(contained_file(asset["path"], cfg.root)))
            local_ids.append(identifier)
    return native, local_ids, paths


async def execute(cfg: Settings, store: Store, job: dict[str, Any]) -> dict[str, Any]:
    from gflow_cli.selfhost.native_captcha import native_secret_path

    payload = json.loads(job["payload"])
    path = native_secret_path(payload, cfg.root)
    try:
        return await _execute(cfg, store, job)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


async def _execute(cfg: Settings, store: Store, job: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(job["payload"])
    profile = job["profile"]
    project = payload["project"]
    if job["kind"] == "accounts/health":
        from gflow_cli.api._engine import CONTEXT_TEARDOWN_TIMEOUT_S, DRIVER_STOP_TIMEOUT_S
        from gflow_cli.selfhost.session_health import (
            HEALTH_TIMEOUT,
            health_observation,
            public_health_observation,
        )

        try:
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "session-health",
                    profile,
                    json.dumps({"project_id": project}),
                ],
                min(
                    cfg.timeout,
                    int(
                        HEALTH_TIMEOUT + 2 * CONTEXT_TEARDOWN_TIMEOUT_S + DRIVER_STOP_TIMEOUT_S + 15
                    ),
                ),
            )
            if code or len(raw) > 65536:
                return {"projectId": project, "sessionHealth": health_observation()}
            native = parse_json_output(raw)
            observation = (
                public_health_observation(native.get("sessionHealth"))
                if native.get("status") == "ok"
                else health_observation()
            )
            return {"projectId": project, "sessionHealth": observation}
        except TimeoutError:
            return {
                "projectId": project,
                "sessionHealth": health_observation(reason="probe_timeout"),
            }
        except Exception:
            return {"projectId": project, "sessionHealth": health_observation()}
    out = Path(job.get("_output") or cfg.root / "output" / job["id"])
    out.mkdir(parents=True, exist_ok=True)
    if job["kind"] in {"voices/create", "voices/delete"}:
        creating = job["kind"] == "voices/create"
        native_payload = {"project_id": project}
        if creating:
            if "captchaSecret" in payload:
                native_payload["captchaSecret"] = payload["captchaSecret"]
            native_payload.update(
                display_name=payload["displayName"],
                preset_voice=payload["voice"],
                dialog=payload["dialog"],
                performance=payload.get("performance", ""),
            )
        else:
            native_payload["ref"] = payload["ref"]
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "voice-saved-create" if creating else "voice-saved-delete",
                profile,
                json.dumps(native_payload),
            ],
            cfg.timeout,
        )
        result = parse_json_output(raw)
        if code or result.get("status") != "ok":
            refusal = native_refusal_error(result, code)
            if refusal is not None:
                return {"projectId": project, "error": refusal}
            error = result.get("error", {})
            if (
                code != 40
                or error.get("type") != "https://gflow-cli.dev/errors/voice-mutation-unknown"
                or error.get("outcome_unknown") is not True
            ):
                return {
                    "projectId": project,
                    "error": {"code": "native_voice_operation_failed", "retryable": False},
                }
            voice_failure: dict[str, Any] = {
                "code": "voice_mutation_outcome_unknown",
                "retryable": False,
                "outcome_unknown": True,
            }
            if error.get("project_id") == project:
                for key in ("phase", "known_media_ids", "workflow_ids"):
                    if key in error:
                        voice_failure[key] = error[key]
            return {"projectId": project, "error": voice_failure}
        if not creating:
            return {"projectId": project, "deleted": result["deleted"], "operation": "delete"}
        return {
            "projectId": project,
            "ref": result["ref"],
            "workflowId": result["workflow_id"],
            "displayName": result["display_name"],
            "voice": result["ref"],
            "mediaId": result["ref"],
            "baseVoice": result["preset_voice"],
            "dialog": result["dialogue"],
            "voicePerformance": result["performance"],
            "source": "user",
        }
    if job["kind"] in {"videos/extend", "videos/edit", "videos/reference", "videos/promote"}:
        promoting = job["kind"] == "videos/promote"
        referencing = job["kind"] == "videos/reference"
        editing = job["kind"] == "videos/edit"
        request = out / "request.json"
        request.write_text(json.dumps(payload), encoding="utf-8")
        request.chmod(0o600)
        try:
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.video_promotion_worker"
                    if promoting
                    else "gflow_cli.selfhost.reference_video_worker"
                    if referencing
                    else "gflow_cli.selfhost.native_video_edit_worker"
                    if editing
                    else "gflow_cli.selfhost.extension_worker",
                    profile,
                    project,
                    str(request),
                ],
                cfg.timeout,
            )
        finally:
            request.unlink(missing_ok=True)
        result = parse_json_output(raw)
        if code:
            refusal = native_refusal_error(result, code)
            if refusal is not None:
                return {"projectId": project, "error": refusal}
            error = result.get("error", {})
            if code != 40 or error.get("outcome_unknown") is not True:
                return {
                    "projectId": project,
                    "error": {"code": "native_video_operation_failed", "retryable": False},
                }
            return {
                "projectId": project,
                "error": {
                    "code": "native_video_promotion_outcome_unknown"
                    if promoting
                    else "native_video_generation_outcome_unknown"
                    if referencing
                    else "native_video_edit_outcome_unknown"
                    if editing
                    else "native_video_extension_outcome_unknown",
                    "retryable": False,
                    "outcome_unknown": True,
                    **(
                        {"phase": error["phase"]}
                        if error.get("phase") in ("video_submit", "video_poll")
                        else {}
                    ),
                    **(
                        {key: error[key] for key in ("media_ids", "workflow_ids") if key in error}
                        if error.get("project_id") == project
                        else {}
                    ),
                },
            }
        if (
            result.get("type")
            != (
                "video_promotion_result"
                if promoting
                else "video_reference_result"
                if referencing
                else "video_edit_result"
                if editing
                else "video_extension_result"
            )
            or result.get("project_id") != project
        ):
            raise ValueError("Native extension returned an unsupported result")
        media_rows: list[dict[str, Any]] = []
        for item in result["results"]:
            media = str(uuid.UUID(item["media_id"]))
            path = contained_file(item["local_path"], out)
            store.asset(media, profile, project, str(path), "video/mp4")
            media_rows.append(
                {
                    "mediaGenerationId": media,
                    "workflowId": item["workflow_id"],
                    "downloadPath": f"/v1/google-flow/assets/{media}/download",
                    "mimeType": "video/mp4",
                    **(
                        {key: item[key] for key in ("width", "height") if key in item}
                        if promoting
                        else {}
                    ),
                }
            )
        return {
            "projectId": project,
            **(
                {}
                if referencing
                else {
                    "sourceMediaGenerationId": payload["referenceVideo_1"]
                    if editing
                    else payload["mediaGenerationId"]
                }
            ),
            "media": media_rows,
            "completedCount": len(media_rows),
            **(
                {"operation": "native-promotion", "resolution": payload["resolution"]}
                if promoting
                else {}
            ),
            **(
                {
                    key: result[key]
                    for key in ("startFrameIndex", "endFrameIndex", "sourceDurationSeconds")
                    if key in result
                }
                if editing
                else {}
            ),
        }
    if job["kind"] in {"assets/archive", "assets/delete"}:
        deleting = job["kind"] == "assets/delete"
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "media-delete-individual" if deleting else "media-delete",
                profile,
                json.dumps({"project_id": project, "media_ids": payload["mediaGenerationIds"]}),
            ],
            cfg.timeout,
        )
        if code:
            if len(raw) <= 65536:
                from gflow_cli.selfhost.unknown_native_media import unknown_native_media_result

                try:
                    unknown = unknown_native_media_result(
                        parse_json_output(raw),
                        code,
                        project,
                        "delete" if deleting else "archive",
                        store.get(job["id"]),
                    )
                    if unknown is not None:
                        store.checkpoint(job["id"], unknown)
                        return unknown
                except (ValueError, TypeError, KeyError):
                    pass
            return {"error": {"code": "native_archive_failed", "retryable": False}}
        result = parse_json_output(raw)
        if result.get("status") != "ok":
            raise ValueError("Native archive did not report success")
        return {
            "deleted": result["deleted"],
            **(
                {
                    "deletedCount": len(result["deleted"]),
                    "alreadyDeleted": result.get("already_deleted", []),
                    "newlyDeleted": result.get("newly_deleted", result["deleted"]),
                    "receiptPersisted": result.get("receipt_persisted", False),
                }
                if deleting
                else {}
            ),
            "operation": "delete" if deleting else "archive",
            "scope": "google-project-library",
            "googleLibraryModified": (
                bool(result.get("newly_deleted", result["deleted"])) if deleting else True
            ),
            "localCacheModified": False,
            "projectId": project,
        }
    if job["kind"] == "videos/concatenate":
        from gflow_cli.selfhost.concatenate import Clip
        from gflow_cli.selfhost.concatenate import execute as concatenate_execute

        clips = [
            Clip(
                path=contained_file(store.asset_get(item["mediaGenerationId"])["path"], cfg.root),
                trim_start=item["trimStart"],
                trim_end=item["trimEnd"],
            )
            for item in payload["media"]
        ]
        output = await concatenate_execute(clips, out / "concatenated.mp4", timeout_s=300)
        artifact = "local_" + str(uuid.uuid4())
        store.asset(artifact, profile, "", str(output.path), "video/mp4")
        result: dict[str, Any] = {
            "backend": "local-ffmpeg",
            "inputsCount": len(clips),
            "localArtifactId": artifact,
            "downloadPath": f"/v1/google-flow/assets/{artifact}/download",
            "duration": output.duration,
            "width": output.width,
            "height": output.height,
        }
        if output.path.stat().st_size <= MAX_ASSET:
            result["encodedVideo"] = base64.b64encode(output.path.read_bytes()).decode()
        return result
    cli = [sys.executable, "-m", "gflow_cli.cli"]
    common = ["--profile", profile, "--project", project]
    kind = job["kind"]
    items: list[dict[str, Any]]
    refs: list[str] = []
    native_refs: list[str] = []
    local_ids: list[str] = []
    managed_paths: list[str] = []
    if kind == "images":
        refs = list(
            dict.fromkeys(
                payload[f"reference_{i}"] for i in range(1, 11) if payload.get(f"reference_{i}")
            )
        )
        native_refs, local_ids, managed_paths = image_reference_inputs(
            cfg, store, profile, payload, refs
        )
        args = cli + [
            "image",
            "i2i" if refs else "t2i",
            *common,
            "--json",
            "--out",
            str(out),
            "--model",
            MODEL_ALIASES[payload["model"]],
            "--aspect",
            payload["aspectRatio"],
            "--count",
            str(payload["count"]),
        ]
        for path in managed_paths:
            # Managed bytes are uploaded; native IDs stay separate for the private worker.
            args.extend(["--ref", path])
        args.extend(["--reference-syntax", "slots", "--", payload["prompt"]])
    elif kind == "images/upscale":
        args = cli + [
            "image",
            "upscale",
            payload["mediaGenerationId"],
            *common,
            "--scale",
            payload["resolution"],
            "--out",
            str(out),
        ]
    elif kind == "assets" and payload["mime"] == "video/mp4":
        args = [
            sys.executable,
            "-m",
            "gflow_cli.selfhost.native_worker",
            "upload-video",
            profile,
            json.dumps(
                {
                    "project_id": project,
                    "path": str(contained_file(payload["input"], cfg.root)),
                    "rights_confirmed": payload.get("rightsConfirmed", False),
                }
            ),
        ]
    elif kind == "assets":
        args = [
            sys.executable,
            "-m",
            "gflow_cli.selfhost.operation_worker",
            profile,
            project,
            str(contained_file(payload["input"], cfg.root)),
        ]
    elif kind == "videos":
        refs = [
            payload[f"referenceImage_{i}"]
            for i in range(1, 8)
            if payload.get(f"referenceImage_{i}")
        ]
        mode = "i2v" if payload.get("startImage") else "r2v" if refs else "t2v"
        args = cli + [
            "video",
            mode,
            *common,
            "--json",
            "--out-dir",
            str(out),
            "--aspect",
            payload["aspectRatio"],
            "--count",
            str(payload["count"]),
        ]
        if payload.get("model"):
            args.extend(["--model", VIDEO_ALIASES[payload["model"]]])
        if payload.get("duration"):
            args.extend(["--duration", str(payload["duration"])])
        if payload.get("resolution"):
            args.extend(["--resolution", payload["resolution"]])
        for key, flag in (("startImage", "--initial-frame"), ("endImage", "--end-frame")):
            if payload.get(key):
                args.extend(
                    [flag, str(contained_file(store.asset_get(payload[key])["path"], cfg.root))]
                )
        for ref in refs:
            args.extend(["--ref", str(contained_file(store.asset_get(ref)["path"], cfg.root))])
        args.extend(["--", payload["prompt"]])
    elif kind in ("videos/upscale", "videos/gif"):
        args = cli + [
            "video",
            "upscale",
            payload["mediaGenerationId"],
            *common,
            "--scale",
            "270p" if kind == "videos/gif" else payload["resolution"],
            "--out",
            str(out),
        ]
    else:
        raise ValueError("Unknown queued operation")
    request_path: Path | None = None
    if kind == "images" and any(
        key in payload
        for key in (
            "seed",
            "captchaSecret",
            "captchaOrder",
            "captchaRetry",
            "reference_prompt_plan",
            "_image_reference_sources",
        )
    ):
        request_path = out / "request.json"
        worker_payload = {
            **payload,
            "model": MODEL_ALIASES[payload["model"]],
            "refs": native_refs,
            "refPaths": managed_paths,
            "local_ref_ids": local_ids if "reference_prompt_plan" in payload else [],
        }
        with request_path.open("w", encoding="utf-8") as file:
            request_path.chmod(0o600)
            json.dump(worker_payload, file)
        args = [
            sys.executable,
            "-m",
            "gflow_cli.selfhost.image_worker",
            profile,
            project,
            str(request_path),
        ]
    if kind == "images/upscale" and any(
        payload.get(key) is not None for key in ("captchaSecret", "captchaOrder", "captchaRetry")
    ):
        request_path = out / "request.json"
        descriptor = os.open(request_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file)
        args = [
            sys.executable,
            "-m",
            "gflow_cli.selfhost.image_upscale_worker",
            profile,
            project,
            str(request_path),
        ]
    if kind == "videos" and (
        payload.get("count", 1) > 1
        or any(
            payload.get(key) is not None
            for key in ("captchaSecret", "captchaOrder", "captchaRetry")
        )
    ):
        request_path = out / "request.json"
        worker_payload = {
            **payload,
            "model": VIDEO_ALIASES[payload["model"]] if payload.get("model") else None,
            "start_image": str(
                contained_file(store.asset_get(payload["startImage"])["path"], cfg.root)
            )
            if payload.get("startImage")
            else None,
            "end_image": str(contained_file(store.asset_get(payload["endImage"])["path"], cfg.root))
            if payload.get("endImage")
            else None,
            "reference_paths": [
                str(contained_file(store.asset_get(ref)["path"], cfg.root)) for ref in refs
            ],
        }
        descriptor = os.open(request_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(worker_payload, file)
        args = [
            sys.executable,
            "-m",
            "gflow_cli.selfhost.general_video_worker",
            profile,
            project,
            str(request_path),
        ]
    try:
        if kind == "images":
            code, raw = await subprocess_run(args, cfg.timeout, image_recovery_id=job["id"])
        else:
            code, raw = await subprocess_run(args, cfg.timeout)
    except asyncio.CancelledError:
        if kind == "videos" and payload.get("count", 1) > 1:
            from gflow_cli.selfhost.video_batch_output import interruption_checkpoint

            batch_interruption = interruption_checkpoint(out / "video-checkpoint.json", project)
            if batch_interruption is not None:
                store.checkpoint(job["id"], batch_interruption)
        raise
    finally:
        if kind == "images":
            store.image_recovery(job)
        if request_path:
            request_path.unlink(missing_ok=True)
    if code and kind == "videos" and payload.get("count", 1) > 1:
        checkpoint_path = out / "video-checkpoint.json"
        try:
            if not checkpoint_path.is_file() or checkpoint_path.stat().st_size > 16384:
                raise ValueError("No bounded batch checkpoint")
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (
                checkpoint.get("project_id") != project
                or checkpoint.get("phase") not in ("video_submit", "video_poll")
                or not isinstance(checkpoint.get("media_ids"), list)
                or not isinstance(checkpoint.get("workflow_ids"), list)
            ):
                raise ValueError("Batch checkpoint scope is unavailable")
            # An existing emitted typed error takes precedence over recovery.
            if not raw or code in (-9, -15, 124, 137, 143):
                raw = json.dumps(
                    {
                        "error": {
                            **checkpoint,
                            "class": "GeneralVideoOutcomeUnknown",
                            "outcome_unknown": True,
                        }
                    }
                ).encode()
                code = 40
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if (
        code
        and kind == "videos"
        and (
            payload.get("count", 1) > 1
            or any(
                payload.get(key) is not None
                for key in ("captchaSecret", "captchaOrder", "captchaRetry")
            )
        )
        and len(raw) <= 65536
    ):
        try:
            failure = parse_json_output(raw)
            refusal = native_refusal_error(failure, code)
            if refusal is not None:
                return {"projectId": project, "error": refusal}
            error = failure.get("error", {})
            media_ids = error.get("media_ids")
            workflow_ids = error.get("workflow_ids")
            if (
                code == 40
                and error.get("class") == "GeneralVideoOutcomeUnknown"
                and error.get("project_id") == project
                and error.get("outcome_unknown") is True
                and error.get("phase") in ("video_submit", "video_poll")
                and isinstance(media_ids, list)
                and isinstance(workflow_ids, list)
                and len(cast(list[Any], media_ids)) <= 4
                and len(cast(list[Any], workflow_ids)) <= 4
            ):
                media = [str(uuid.UUID(value)) for value in cast(list[Any], media_ids)]
                workflows = [str(uuid.UUID(value)) for value in cast(list[Any], workflow_ids)]
                if (
                    len(media) != len(workflows)
                    or len(set(media + workflows)) != len(media) * 2
                    or project in media + workflows
                ):
                    raise ValueError("Video uncertainty requires distinct actual paired handles")
                unknown = {
                    "projectId": project,
                    "knownMediaGenerationIds": media,
                    "outcomeUnknown": True,
                    "error": {
                        "code": "video_generation_outcome_unknown",
                        "retryable": False,
                        "phase": error["phase"],
                        "media_ids": media,
                        "workflow_ids": workflows,
                    },
                }
                store.checkpoint(job["id"], unknown)
                return unknown
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    if code:
        if (
            code in {4, 5, 10}
            and kind in {"images", "images/upscale", "videos"}
            and len(raw) <= 65536
        ):
            try:
                refusal = native_refusal_error(parse_json_output(raw), code)
                if refusal is not None:
                    return {"projectId": project, "error": refusal}
            except (ValueError, TypeError, KeyError, AttributeError):
                pass
        if kind == "assets" and payload["mime"] == "video/mp4" and len(raw) <= 65536:
            from gflow_cli.selfhost.unknown_native_media import unknown_native_media_result

            try:
                unknown = unknown_native_media_result(
                    parse_json_output(raw), code, project, "upload", store.get(job["id"])
                )
                if unknown is not None:
                    store.checkpoint(job["id"], unknown)
                    return unknown
            except (ValueError, TypeError, KeyError):
                pass
        if kind == "images" and len(raw) <= 65536:
            # Import only allow-listed recovery handles/contained paths; never raw errors.
            try:
                failure = parse_json_output(raw)
                from gflow_cli.selfhost.unknown_image import unknown_image_result

                unknown = unknown_image_result(failure, code, project)
                if unknown is not None:
                    return store.checkpoint_image_unknown(job["id"], unknown)
                records = failure.get("error", {}).get("imageRecovery", {}).get("images", [])
                if isinstance(records, list) and 1 <= len(cast(list[Any], records)) <= 4:
                    safe: list[dict[str, Any]] = []
                    for record in cast(list[Any], records):
                        if not isinstance(record, dict):
                            continue
                        item = cast(dict[str, Any], record)
                        entry: dict[str, Any] = {"media_name": item.get("media_name")}
                        if "local_path" in item:
                            entry["local_path"] = item["local_path"]
                        safe.append(entry)
                    store.image_recovery(job, {"images": safe})
            except (ValueError, TypeError, AttributeError, KeyError):
                pass
        # Keep potentially sensitive CLI output local.
        return {
            "error": {
                "code": "gflow_command_failed",
                "exit_code": code,
                "retryable": False,
                "detail": "Google Flow command failed; inspect the local diagnostic log.",
            }
        }
    if kind == "videos" and payload.get("count", 1) > 1:
        from gflow_cli.selfhost.video_batch_output import publish_video_batch

        result = parse_json_output(raw)
        envelope = await publish_video_batch(
            store,
            result,
            profile=profile,
            project=project,
            out=out,
            count=payload["count"],
        )
        envelope["email"] = cfg.accounts[profile]["email"]
        store.checkpoint(job["id"], envelope)
        return envelope
    if kind in ("videos/upscale", "videos/gif"):
        files = [
            path
            for path in out.rglob("*")
            if path.is_file() and path.suffix.lower() in (".mp4", ".gif")
        ]
        if len(files) != 1:
            raise ValueError("Export completed without exactly one managed output")
        result = {"local_path": str(files[0]), "media_id": payload["mediaGenerationId"]}
        items = []
    elif kind == "images/upscale":
        files = [
            path
            for path in out.rglob("*")
            if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg")
        ]
        if len(files) != 1:
            raise ValueError("Upscale completed without exactly one managed output")
        items = [{"media_name": payload["mediaGenerationId"], "local_path": str(files[0])}]
        result = {"project_id": project}
    else:
        result = parse_json_output(raw)
        if (
            kind == "assets"
            and payload["mime"] == "video/mp4"
            and result.get("code") == "upload_rights_required"
        ):
            return {
                "error": {
                    "code": "upload_rights_required",
                    "retryable": False,
                    "detail": (
                        "Google requires upload rights confirmation. If you own the rights, "
                        "submit a new request with X-Flow-Rights-Confirmed: true; "
                        "otherwise confirm in the browser."
                    ),
                }
            }
        if result.get("status") not in ("ok", "completed"):
            raise ValueError("CLI reported an unsuccessful result")
        items = result.get("images", [])
    if kind == "images" and not items:
        raise ValueError("Generation completed without any image outputs")
    if kind == "assets":
        media = str(uuid.UUID(result["media_id"]))
        path = contained_file(payload["input"], cfg.root)
        store.asset(media, profile, project, str(path), payload["mime"])
        return {
            "email": cfg.accounts[profile]["email"],
            "projectId": project,
            "mediaGenerationId": {"mediaGenerationId": media},
        }
    media_items: list[dict[str, Any]] = []
    known: list[str] = []
    recovered: list[dict[str, Any]] = []
    if kind == "images":
        previous = store.get(job["id"])
        known.extend(previous.get("knownMediaGenerationIds", []))
        recovered = previous.get("media", [])
        for item in items:
            try:
                identifier = str(uuid.UUID(item["media_name"]))
                if identifier not in known:
                    known.append(identifier)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        store.checkpoint(
            job["id"],
            {
                "knownMediaGenerationIds": known,
                "media": recovered,
                "generatedCount": len(known),
                "completedCount": len(recovered),
            },
        )
    for item in items:
        path = contained_file(item["local_path"], out)
        if path.stat().st_size > MAX_ASSET:
            raise ValueError("Image exceeds inline response limit")
        media = str(uuid.UUID(item["media_name"]))
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        store.asset(media, profile, result.get("project_id", project), str(path), mime)
        media_items.append(
            {
                "mediaGenerationId": media,
                "image": {
                    "generatedImage": {
                        "encodedImage": base64.b64encode(path.read_bytes()).decode(),
                        "seed": item.get("seed"),
                        "width": item.get("dimensions", {}).get("width"),
                        "height": item.get("dimensions", {}).get("height"),
                    }
                },
            }
        )
        if kind == "images":
            completed = {entry["mediaGenerationId"]: entry for entry in recovered}
            completed.update({entry["mediaGenerationId"]: entry for entry in media_items})
            store.checkpoint(
                job["id"],
                {
                    "knownMediaGenerationIds": known,
                    "media": list(completed.values()),
                    "generatedCount": len(known),
                    "completedCount": len(completed),
                },
            )
    if kind.startswith("videos"):
        path = contained_file(result.get("local_path") or str(out / "video.mp4"), out)
        media = str(uuid.UUID(result.get("media_id") or payload.get("mediaGenerationId")))
        artifact = media if kind == "videos" else f"{media}_{payload['resolution']}"
        store.asset(
            artifact,
            profile,
            project,
            str(path),
            "image/gif" if kind == "videos/gif" else "video/mp4",
        )
        media_items.append(
            {
                "mediaGenerationId": media,
                "video": {"downloadPath": f"/v1/google-flow/assets/{artifact}/download"},
                "localArtifactId": artifact,
            }
        )
    envelope: dict[str, Any] = {
        "email": cfg.accounts[profile]["email"],
        "projectId": project,
        "media": media_items,
    }
    if kind == "images" and len(media_items) != payload.get("count", 1):
        envelope["error"] = {
            "code": "image_output_count_mismatch",
            "expectedCount": payload.get("count", 1),
            "receivedCount": len(media_items),
            "retryable": False,
            "detail": (
                "Preserved returned images; inspect the job before submitting another generation."
            ),
        }
    if kind == "images":
        from gflow_cli.selfhost.http_jobs import aspect_metadata

        envelope.update(aspect_metadata(result))
    if result.get("captchaProvider"):
        envelope["captchaProvider"] = result["captchaProvider"]
    return envelope


async def worker(cfg: Settings, store: Store, profile: str) -> None:
    while True:
        if profile not in cfg.accounts:
            await asyncio.sleep(0.5)
            continue
        job = store.claim(profile)
        if job is None:
            await asyncio.sleep(0.5)
            continue
        try:
            result = await execute(cfg, store, job)
            store.finish(job["id"], "failed" if "error" in result else "completed", result)
        except asyncio.CancelledError:
            # Mark interrupted jobs on restart; never replay them.
            raise
        except TimeoutError:
            store.finish(
                job["id"],
                "interrupted",
                {"error": {"code": "submission_outcome_unknown", "retryable": False}},
            )
        except Exception:
            store.finish(
                job["id"],
                "failed",
                {"error": {"code": "invalid_operation_result", "retryable": False}},
            )


async def deliver_callbacks(cfg: Settings, store: Store) -> None:
    while True:
        with store.connection() as conn:
            pending = conn.execute(
                "SELECT * FROM callbacks WHERE delivered=0 AND attempts<5 AND due<=? "
                "ORDER BY id LIMIT 1",
                (time.time(),),
            ).fetchone()
        if pending is None:
            await asyncio.sleep(1)
            continue
        success = False
        try:
            url = validate_callback(pending["url"], cfg.callbacks)
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            addresses = await asyncio.get_running_loop().getaddrinfo(
                host, 443, type=socket.SOCK_STREAM
            )
            ip = str(addresses[0][4][0])
            if not ipaddress.ip_address(ip).is_global:
                raise ValueError("Callback resolved to a private address")
            netloc = f"[{ip}]" if ":" in ip else ip
            pinned = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
            message: Any = json.loads(pending["payload"])
            is_image = (
                isinstance(message, dict) and cast(dict[str, Any], message).get("type") == "image"
            )
            timeout = 5 if is_image else 10
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False
            ) as client:
                # Callback acknowledgment needs headers/status only. Never buffer
                # an unbounded recipient response; the context closes every stream.
                async with client.stream(
                    "POST",
                    pinned,
                    headers={"Host": host},
                    json=cast(Any, message),
                    extensions={"sni_hostname": host},
                ) as response:
                    success = 200 <= response.status_code < 300
        except Exception:
            pass
        with store.connection() as conn:
            conn.execute(
                "UPDATE callbacks SET delivered=?,attempts=attempts+1,due=? WHERE id=?",
                (
                    int(success),
                    time.time() + min(300, 2 ** (pending["attempts"] + 1)),
                    pending["id"],
                ),
            )
