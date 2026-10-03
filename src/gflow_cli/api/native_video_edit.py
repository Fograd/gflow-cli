"""Source-derived Omni edit DTO. Accepted output remains a live-proof obligation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api._engine import mint_evaluate_kwargs
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_extension import (
    _NATIVE_FETCH,  # pyright: ignore[reportPrivateUsage]
    NativeExtensionStarted,
    NativeExtensionUnknownError,
    _read_native,  # pyright: ignore[reportPrivateUsage]
    _uuid,  # pyright: ignore[reportPrivateUsage]
    extension_args,
    new_extension_started,
    parse_extension_models,
    wait_native_extension,
)
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.api.transports.migrated_composer import (
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.native_voices import parse_saved_voices
from gflow_cli.errors import ConfigurationError, ContentPolicyError, WafRejectionError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from gflow_cli.api.client import FlowApiClient

RPC = "jIps6"


class NativeVideoEditUnknownError(NativeExtensionUnknownError):
    problem_type = "https://gflow-cli.dev/errors/native-video-edit-unknown"
    title = "Native video edit outcome unknown"

    def __init__(self, started: NativeExtensionStarted) -> None:
        super().__init__(started)
        self.route = "video.edit.native"


def video_edit_args(
    started: NativeExtensionStarted,
    *,
    prompt: str,
    model_key: str,
    aspect: str,
    token: str,
    start_frame: int = 0,
    end_frame: int = 240,
    image_ids: tuple[str, ...] = (),
    audio_ids: tuple[str, ...] = (),
) -> list[Any]:
    """E4a fields5 metadata,9 image refs,10 audio refs; unlike K4a extension."""
    if (
        type(start_frame) is not int
        or type(end_frame) is not int
        or not 0 <= start_frame <= 239
        or not 1 <= end_frame <= 240
        or start_frame >= end_frame
    ):
        raise ConfigurationError(
            detail="Edit requires a positive virtual24fps frame window in0..240"
        )
    if len(started.media_ids) != 1 or len(image_ids) > 5 or len(audio_ids) > 3:
        raise ConfigurationError(
            detail="Edit supports one output, five images and three audio references"
        )
    for values in (image_ids, audio_ids):
        if len(set(values)) != len(values):
            raise ConfigurationError(detail="Edit references must be distinct")
        for value in values:
            _uuid(value)
    args = extension_args(
        started,
        prompt=prompt,
        model_key=model_key,
        aspect=aspect,
        token=token,
        trim_start_frame=start_frame,
        trim_end_frame=end_frame,
    )
    row = args[0][0]
    metadata = row.pop(5)
    row[4] = metadata
    if image_ids or audio_ids:
        row.extend(
            [
                None,
                None,
                None,
                [[None, value] for value in image_ids],
                [[value] for value in audio_ids],
            ]
        )
    return args


async def edit_native_video(
    client: FlowApiClient,
    *,
    project_id: str,
    media_id: str,
    prompt: str,
    model_key: str,
    start_frame: int = 0,
    end_frame: int,
    image_ids: tuple[str, ...] = (),
    audio_ids: tuple[str, ...] = (),
    on_started: Callable[[NativeExtensionStarted], Awaitable[None]] | None = None,
) -> NativeExtensionStarted:
    """One source-owned edit dispatch, with preassigned recovery identities."""
    project_id, media_id = _uuid(project_id), _uuid(media_id)
    started = new_extension_started(project_id, media_id, 1)
    video_edit_args(
        started,
        prompt=prompt,
        model_key=model_key,
        aspect="16:9",
        token="validate",
        start_frame=start_frame,
        end_frame=end_frame,
        image_ids=image_ids,
        audio_ids=audio_ids,
    )
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native video edit requires migrated Flow")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        payload = await read_project_payload(page, project_id)
        rows = parse_media_snapshot(payload, project_id)["media"]
        active = {
            row["media_id"]
            for row in project_media(payload, project_id)
            if row["archived"] is False
        }
        if not {media_id, *image_ids, *audio_ids} <= active:
            raise ConfigurationError(detail="Edit inputs require active owned project workflows")
        source = next(
            (row for row in rows if row["media_id"] == media_id and row["kind"] == "video"), None
        )
        if source is None:
            raise ConfigurationError(detail="Edit source requires an owned typed project video")
        if any(
            not any(row["media_id"] == ref and row["kind"] == "image" for row in rows)
            for ref in image_ids
        ):
            raise ConfigurationError(detail="Edit image reference requires an owned typed image")
        if audio_ids:
            voices = {row["ref"] for row in parse_saved_voices(payload, project_id)}
            if not set(audio_ids) <= voices:
                raise ConfigurationError(
                    detail="Edit audio reference requires an owned saved voice"
                )
        width, height = source.get("width"), source.get("height")
        aspect = next(
            (
                ratio
                for w, h, ratio in ((16, 9, "16:9"), (9, 16, "9:16"), (1, 1, "1:1"))
                if isinstance(width, int) and isinstance(height, int) and width * h == height * w
            ),
            None,
        )
        if aspect is None:
            raise ConfigurationError(detail="Edit source aspect requires measured dimensions")
        models = await _read_native(page, "HTrJv", [], project_id)
        credits = await _read_native(page, "nzlxg", [], project_id)
        if not isinstance(credits, list) or len(cast(list[Any], credits)) < 4:
            raise ConfigurationError(detail="Native edit account tier was not observed")
        eligible = parse_extension_models(
            models, tier=cast(list[Any], credits)[3], required_requirements=(1, 6, 20)
        )
        if not any(row["model_key"] == model_key for row in eligible):
            raise ConfigurationError(detail="Model key is not an available native edit model")
        token = await TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs()).mint(
            "VIDEO_GENERATION"
        )
        args = video_edit_args(
            started,
            prompt=prompt,
            model_key=model_key,
            aspect=aspect,
            token=token,
            start_frame=start_frame,
            end_frame=end_frame,
            image_ids=image_ids,
            audio_ids=audio_ids,
        )
        if on_started:
            await on_started(started)
        try:
            result = await page.evaluate(
                _NATIVE_FETCH, {"rpc": RPC, "args": args, "source": f"/project/{project_id}"}
            )
            refusal = _submit_refusal(result["text"], (RPC,))
            if refusal is not None:
                raise refusal
            if result["status"] != 200 or rpc_errors(result["text"]):
                raise NativeVideoEditUnknownError(started)
            acknowledged: set[tuple[str, str]] = set()
            for name, value in parse_frames(result["text"]):
                if name != RPC or not isinstance(value, list) or len(cast(list[Any], value)) < 4:
                    continue
                records: Any = cast(list[Any], value)[3]
                if not isinstance(records, list):
                    continue
                for row in cast(list[Any], records):
                    if (
                        not isinstance(row, list)
                        or len(cast(list[Any], row)) < 3
                        or row[1] != project_id
                    ):
                        raise NativeVideoEditUnknownError(started)
                    record = cast(list[Any], row)
                    if not isinstance(record[0], str) or not isinstance(record[2], str):
                        raise NativeVideoEditUnknownError(started)
                    acknowledged.add((record[0], record[2]))
            if acknowledged != set(zip(started.media_ids, started.workflow_ids, strict=True)):
                raise NativeVideoEditUnknownError(started)
            return started
        except asyncio.CancelledError:
            raise
        except (WafRejectionError, ContentPolicyError):
            raise
        except Exception:
            raise NativeVideoEditUnknownError(started) from None
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def wait_native_video_edit(
    client: FlowApiClient, started: NativeExtensionStarted
) -> tuple[Any, ...]:
    try:
        return await wait_native_extension(client, started)
    except NativeExtensionUnknownError:
        raise NativeVideoEditUnknownError(started) from None


async def list_native_video_edit_models(
    client: FlowApiClient, project_id: str
) -> list[dict[str, Any]]:
    """Account-native edit-capable model keys, not ordinary generation fallback."""
    project = _uuid(project_id)
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native edit models require migrated Flow")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        await page.goto(f"https://flow.google.com/project/{project}", wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
        models = await _read_native(page, "HTrJv", [], project)
        credits = await _read_native(page, "nzlxg", [], project)
        if not isinstance(credits, list) or len(cast(list[Any], credits)) < 4:
            raise ConfigurationError(detail="Native edit account tier was not observed")
        return parse_extension_models(
            models, tier=cast(list[Any], credits)[3], required_requirements=(1, 6, 20)
        )
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
