"""Source-derived Omni edit DTO. Accepted output remains a live-proof obligation."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass
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
from gflow_cli.api.native_video_audio import (
    audio_wire_id,
    normalize_audio_reference,
    validate_audio_presets,
)
from gflow_cli.api.native_video_prompt import encode_video_prompt
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.api.transports.migrated_composer import (
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
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


@dataclass(frozen=True)
class NativeVideoEditStarted(NativeExtensionStarted):
    """Resolved source window; inherited recovery identities remain unchanged."""

    source_duration_seconds: float | None = None
    start_frame: int = 0
    end_frame: int = 240


def source_video_duration(payload: Any, project: str, media: str) -> float:
    """Native AP: video field2 LI, field3 qx Duration; no frontend fallback."""
    try:
        inventory = parse_media_snapshot(payload, project)
        if not any(
            row["media_id"] == media and row["kind"] == "video" for row in inventory["media"]
        ):
            raise ValueError
        rows = cast(list[Any], payload)[2]
        matches = [row for row in rows if row[0] == media]
        if len(matches) != 1:
            raise ValueError
        value = matches[0][7][1][2]
        seconds = value[0]
        nanos = value[1] if len(value) > 1 and value[1] is not None else 0
        if not (
            (
                type(seconds) is int
                or (
                    isinstance(seconds, str)
                    and seconds.isascii()
                    and seconds.isdigit()
                    and len(seconds) <= 18
                )
            )
            and type(nanos) is int
            and 0 <= nanos < 1_000_000_000
        ):
            raise ValueError
        duration = int(seconds) + nanos / 1_000_000_000
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError
        return duration
    except (IndexError, KeyError, TypeError, ValueError, OverflowError):
        raise ConfigurationError(detail="Source video duration was not observed") from None


def resolve_edit_window(duration: float | None, start: int, end: int | None) -> int:
    """An omitted end never exceeds the measured clip or the virtual240-frame cap."""
    if end is not None:
        resolved = end
    else:
        try:
            valid = (
                isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and math.isfinite(duration)
                and duration > 0
            )
        except OverflowError:
            valid = False
        if not valid:
            raise ConfigurationError(detail="Default edit end requires measured source duration")
        duration = cast(float, duration)
        resolved = math.floor(min(duration, 10) * 24)
    if type(start) is not int or type(resolved) is not int or not 0 <= start < resolved <= 240:
        raise ConfigurationError(
            detail="Edit requires a positive virtual24fps frame window in0..240"
        )
    return resolved


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
    character_ids: tuple[str, ...] = (),
    reference_slots: Mapping[str, ReferenceSlot] | None = None,
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
    if (
        len(started.media_ids) != 1
        or len(image_ids) > 5
        or len(audio_ids) > 3
        or len(character_ids) > 7
    ):
        raise ConfigurationError(
            detail="Edit supports one output, five images and three audio references"
        )
    audio_ids = tuple(normalize_audio_reference(value) for value in audio_ids)
    if len(set(image_ids + audio_ids + character_ids)) != len(
        image_ids + audio_ids + character_ids
    ):
        raise ConfigurationError(detail="Edit reference identities must be distinct")
    for values in (image_ids, character_ids):
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
    if image_ids or audio_ids or character_ids or reference_slots is not None:
        row[1] = encode_video_prompt(prompt, image_ids, audio_ids, character_ids, reference_slots)
    if image_ids or audio_ids or character_ids:
        row.extend(
            [
                None,
                None,
                None,
                [[None, value] for value in image_ids],
                [[audio_wire_id(value)] for value in audio_ids],
            ]
        )
    if character_ids:
        row.append([[value] for value in character_ids])
    return args


def validate_edit_audio(payload: Any, project: str, audio_ids: tuple[str, ...]) -> None:
    """Exclusive native audio joined to exactly one active owned workflow."""
    if not audio_ids:
        return
    try:
        project = _uuid(project)
        references = tuple(_uuid(value) for value in audio_ids)
        if len(references) > 3 or len(set(references)) != len(references):
            raise ValueError
        if not isinstance(payload, list) or len(cast(list[Any], payload)) < 3:
            raise ValueError
        workflows, media = cast(list[Any], payload)[1:3]
        if not isinstance(workflows, list) or not isinstance(media, list):
            raise ValueError
        owned: dict[str, list[Any]] = {}
        for candidate in cast(list[Any], workflows):
            if (
                not isinstance(candidate, list)
                or len(cast(list[Any], candidate)) < 5
                or candidate[4] != project
            ):
                raise ValueError
            row = cast(list[Any], candidate)
            identifier = _uuid(row[0])
            if identifier in owned:
                raise ValueError
            owned[identifier] = row
        found: set[str] = set()
        seen: set[str] = set()
        for candidate in cast(list[Any], media):
            if (
                not isinstance(candidate, list)
                or len(cast(list[Any], candidate)) < 3
                or candidate[1] != project
            ):
                raise ValueError
            row = cast(list[Any], candidate)
            identifier, workflow = _uuid(row[0]), _uuid(row[2])
            if identifier in seen:
                raise ValueError
            seen.add(identifier)
            if identifier not in references:
                continue
            if len(row) <= 10 or row[6] is not None or row[7] is not None:
                raise ValueError
            audio = row[10]
            if (
                not isinstance(audio, list)
                or len(cast(list[Any], audio)) != 1
                or not isinstance(audio[0], list)
                or not audio[0]
            ):
                raise ValueError
            parent = owned.get(workflow)
            details = parent[3] if parent is not None else None
            if (
                not isinstance(details, list)
                or len(cast(list[Any], details)) < 5
                or details[2] not in (None, False, 0)
            ):
                raise ValueError
            _uuid(cast(list[Any], details)[4])
            found.add(identifier)
        if found != set(references):
            raise ValueError
    except (ValueError, TypeError, IndexError, ConfigurationError):
        raise ConfigurationError(
            detail="Edit audio requires exclusive active owned native audio media"
        ) from None


async def edit_native_video(
    client: FlowApiClient,
    *,
    project_id: str,
    media_id: str,
    prompt: str,
    model_key: str,
    start_frame: int = 0,
    end_frame: int | None = None,
    image_ids: tuple[str, ...] = (),
    audio_ids: tuple[str, ...] = (),
    character_ids: tuple[str, ...] = (),
    reference_slot_ids: dict[str, str] | None = None,
    on_started: Callable[[NativeExtensionStarted], Awaitable[None]] | None = None,
) -> NativeVideoEditStarted:
    """One source-owned edit dispatch, with preassigned recovery identities."""
    project_id, media_id = _uuid(project_id), _uuid(media_id)
    image_ids, audio_ids, character_ids = (
        tuple(_uuid(v) for v in image_ids),
        tuple(normalize_audio_reference(v) for v in audio_ids),
        tuple(_uuid(v) for v in character_ids),
    )
    slots = (
        None
        if reference_slot_ids is None
        else {
            key: ReferenceSlot(
                "audio"
                if key.startswith("referenceAudio_")
                else "character"
                if key.startswith("character_")
                else "image",
                value,
            )
            for key, value in reference_slot_ids.items()
        }
    )
    started = new_extension_started(project_id, media_id, 1)
    video_edit_args(
        started,
        prompt=prompt,
        model_key=model_key,
        aspect="16:9",
        token="validate",
        start_frame=start_frame,
        end_frame=resolve_edit_window(None, start_frame, end_frame)
        if end_frame is not None
        else 240,
        image_ids=image_ids,
        audio_ids=audio_ids,
        character_ids=character_ids,
        reference_slots=slots,
    )
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native video edit requires migrated Flow")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        payload = await read_project_payload(page, project_id)
        from gflow_cli.api.native_video_characters import (
            character_reference_counts,
            classify_video_slots,
            model_reference_limits,
            reference_capacity,
        )

        if reference_slot_ids is not None:
            slots = classify_video_slots(payload, project_id, reference_slot_ids)
            plan = resolve_reference_markers(prompt, surface="video", slots=slots)
            image_ids, audio_ids, character_ids = plan.image_ids, plan.audio_ids, plan.character_ids
        weights = character_reference_counts(payload, project_id, character_ids)
        rows = parse_media_snapshot(payload, project_id)["media"]
        active = {
            row["media_id"]
            for row in project_media(payload, project_id)
            if row["archived"] is False
        }
        if not {media_id, *image_ids} <= active:
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
        owned_audio = validate_audio_presets(payload, audio_ids)
        validate_edit_audio(payload, project_id, owned_audio)
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
        measured_duration: float | None = None
        if end_frame is None:
            measured_duration = source_video_duration(payload, project_id, media_id)
        end_frame = resolve_edit_window(measured_duration, start_frame, end_frame)
        started = NativeVideoEditStarted(
            **vars(started),
            source_duration_seconds=measured_duration,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        models = await _read_native(page, "HTrJv", [], project_id)
        credits = await _read_native(page, "nzlxg", [], project_id)
        if not isinstance(credits, list) or len(cast(list[Any], credits)) < 4:
            raise ConfigurationError(detail="Native edit account tier was not observed")
        eligible = parse_extension_models(
            models, tier=cast(list[Any], credits)[3], required_requirements=(1, 6, 20)
        )
        if not any(row["model_key"] == model_key for row in eligible):
            raise ConfigurationError(detail="Model key is not an available native edit model")
        if image_ids or audio_ids or character_ids:
            limits = model_reference_limits(models, model_key)
            if not reference_capacity(len(image_ids), len(audio_ids), weights, limits):
                raise ConfigurationError(
                    detail="Edit ingredients exceed the native model capacities"
                )
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
            character_ids=character_ids,
            reference_slots=slots,
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
