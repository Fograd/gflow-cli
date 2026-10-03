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
    }.get(exit_code)
    if (
        expected is None
        or error.get("class") != expected[0]
        or error.get("type") != expected[1]
        or error.get("exit_code") != exit_code
        or error.get("outcome_unknown") is True
    ):
        return None
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


async def execute(cfg: Settings, store: Store, job: dict[str, Any]) -> dict[str, Any]:
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
    if job["kind"] == "videos" and payload.get("count", 1) > 1:
        accumulated: dict[str, Any] = {
            "email": cfg.accounts[profile]["email"],
            "projectId": project,
            "media": [],
            "completedCount": 0,
            "requestedCount": payload["count"],
        }
        for index in range(payload["count"]):
            one = {**payload, "count": 1}
            child = {**job, "payload": json.dumps(one), "_output": str(out / f"part-{index + 1}")}
            single = await execute(cfg, store, child)
            if "error" in single:
                return {**accumulated, "error": single["error"]}
            accumulated["media"].extend(single["media"])
            accumulated["completedCount"] += 1
            store.checkpoint(job["id"], accumulated)
        return accumulated
    if job["kind"] in {"voices/create", "voices/delete"}:
        creating = job["kind"] == "voices/create"
        native_payload = {"project_id": project}
        if creating:
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
    if job["kind"] in {"videos/extend", "videos/edit", "videos/reference"}:
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
                    "gflow_cli.selfhost.reference_video_worker"
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
                    "code": "native_video_generation_outcome_unknown"
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
                "video_reference_result"
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
            "operation": "delete" if deleting else "archive",
            "scope": "google-project-library",
            "googleLibraryModified": True,
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
    if kind == "images":
        refs = list(
            dict.fromkeys(
                payload[f"reference_{i}"] for i in range(1, 11) if payload.get(f"reference_{i}")
            )
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
        for ref in refs:
            # Re-upload our saved bytes into the pinned project, avoiding cross-project UUID drift.
            args.extend(["--ref", str(contained_file(store.asset_get(ref)["path"], cfg.root))])
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
        )
    ):
        request_path = out / "request.json"
        worker_payload = {
            **payload,
            "model": MODEL_ALIASES[payload["model"]],
            "refPaths": [
                str(contained_file(store.asset_get(ref)["path"], cfg.root)) for ref in refs
            ],
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
    try:
        if kind == "images":
            code, raw = await subprocess_run(args, cfg.timeout, image_recovery_id=job["id"])
        else:
            code, raw = await subprocess_run(args, cfg.timeout)
    finally:
        if kind == "images":
            store.image_recovery(job)
        if request_path:
            request_path.unlink(missing_ok=True)
    if code:
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
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                # Callback acknowledgment needs headers/status only. Never buffer
                # an unbounded recipient response; the context closes every stream.
                async with client.stream(
                    "POST",
                    pinned,
                    headers={"Host": host},
                    json=json.loads(pending["payload"]),
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
