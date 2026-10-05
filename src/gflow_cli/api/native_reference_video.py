"""Native image/audio-reference video DTO from deployed Q4a/MZZa6b.

Source-schema implementation; generation acceptance is deferred to final E2E.
"""

from __future__ import annotations

# Private helpers are shared within the native RPC adapter boundary.
# pyright: reportPrivateUsage=false, reportUnnecessaryIsInstance=false
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from gflow_cli.api._engine import page_owned_evaluate_kwargs
from gflow_cli.api.native_captcha import native_captcha_outcome, native_captcha_submission
from gflow_cli.api.native_extension import (
    _NATIVE_FETCH,
    _read_native,
    _uuid,
    assigned_id,
    parse_extension_models,
)
from gflow_cli.api.native_video_audio import (
    audio_wire_id,
    normalize_audio_reference,
    validate_audio_presets,
    validate_owned_audio,
)
from gflow_cli.api.native_video_characters import (
    character_reference_counts,
    classify_video_slots,
    model_reference_limits,
    reference_capacity,
)
from gflow_cli.api.native_video_prompt import encode_video_prompt
from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.api.transports.migrated_composer import (
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.errors import (
    ConfigurationError,
    ContentPolicyError,
    NativeQuotaError,
    NativeVideoGenerationUnknownError,
    WafRejectionError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from gflow_cli.api.client import FlowApiClient


@dataclass(frozen=True)
class NativeReferenceVideoStarted:
    project_id: str
    media_ids: tuple[str, ...]
    workflow_ids: tuple[str, ...]
    media_seeds: tuple[str, ...] = field(default=(), repr=False)
    workflow_seeds: tuple[str, ...] = field(default=(), repr=False)


def new_reference_started(project: str, count: int) -> NativeReferenceVideoStarted:
    if type(count) is not int or count not in range(1, 5):
        raise ConfigurationError(detail="Native video count requires one through four outputs")
    media = tuple(str(uuid4()) for _ in range(count))
    workflows = tuple(str(uuid4()) for _ in range(count))
    return NativeReferenceVideoStarted(
        _uuid(project),
        tuple(map(assigned_id, media)),
        tuple(map(assigned_id, workflows)),
        media,
        workflows,
    )


def _references(
    images: tuple[str, ...], audio: tuple[str, ...], characters: tuple[str, ...] = ()
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if (
        not isinstance(images, tuple)
        or not isinstance(audio, tuple)
        or len(images) > 7
        or not isinstance(characters, tuple)
        or len(characters) > 7
        or not (images or audio or characters)
        or len(audio) > 5
    ):
        raise ConfigurationError(
            detail="Native video requires ingredients: at most seven images/five audio assets"
        )
    result = (
        tuple(_uuid(x) for x in images),
        tuple(normalize_audio_reference(x) for x in audio),
        tuple(_uuid(x) for x in characters),
    )
    if len(set(result[0] + result[1] + result[2])) != len(result[0] + result[1] + result[2]):
        raise ConfigurationError(detail="Native video attachment identifiers must be distinct")
    return result


def reference_args(
    started: NativeReferenceVideoStarted,
    *,
    prompt: str,
    image_ids: tuple[str, ...],
    audio_ids: tuple[str, ...] = (),
    character_ids: tuple[str, ...] = (),
    reference_slots: Mapping[str, ReferenceSlot] | None = None,
    model_key: str,
    aspect: str,
    resolution: str,
    token: str,
) -> list[Any]:
    """Q4a: prompt1/images2/key3/aspect4/metadata6/audio8/resolution12."""
    images, audio, characters = _references(image_ids, audio_ids, character_ids)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10000:
        raise ConfigurationError(detail="Native video requires a bounded nonempty prompt")
    if (
        not isinstance(model_key, str)
        or not 1 <= len(model_key) <= 200
        or aspect not in {"16:9", "9:16", "1:1"}
        or resolution not in {"360p", "720p", "1080p", "4k"}
        or not isinstance(token, str)
        or not token
    ):
        raise ConfigurationError(
            detail="Native video requires supported model/aspect/resolution controls"
        )
    _uuid(started.project_id)
    count = len(started.media_ids)
    if count not in range(1, 5) or any(
        len(values) != count
        for values in (started.workflow_ids, started.media_seeds, started.workflow_seeds)
    ):
        raise ConfigurationError(detail="Native video assignment handles are incomplete")
    for ids, seeds in (
        (started.media_ids, started.media_seeds),
        (started.workflow_ids, started.workflow_seeds),
    ):
        if tuple(assigned_id(_uuid(seed)) for seed in seeds) != ids:
            raise ConfigurationError(detail="Native video assignment handles do not match")
    if len(set(started.media_ids + started.workflow_ids)) != count * 2:
        raise ConfigurationError(detail="Native video assignment handles must be distinct")
    text = encode_video_prompt(prompt, images, audio, characters, reference_slots)
    rows: list[Any] = []
    for media, workflow in zip(started.media_seeds, started.workflow_seeds, strict=True):
        row: list[Any] = [
            text,
            [[None, v] for v in images],
            model_key,
            {"16:9": 2, "9:16": 1, "1:1": 0}[aspect],
            None,
            [None, None, None, None, media, workflow],
            None,
            [[audio_wire_id(v)] for v in audio],
        ]
        if characters:
            row.extend([None, [[v] for v in characters]])
        if resolution != "720p":
            row.extend([None] * (11 - len(row)) + [[{"360p": 4, "1080p": 2, "4k": 3}[resolution]]])
        rows.append(row)
    return [
        rows,
        [None, 22, None, None, None, started.project_id, None, None, None, None, [token, 1]],
        [str(uuid4()), 1],
    ]


def validate_reference_assets(
    payload: Any, project: str, images: tuple[str, ...], audio: tuple[str, ...]
) -> None:
    """Fresh typed image proof and shared active native audio ownership."""
    validate_owned_audio(payload, project, audio, max_refs=5)
    from gflow_cli.api.transports.batchexecute import _at

    if not isinstance(payload, list) or not isinstance(_at(cast(list[Any], payload), 2), list):
        raise ConfigurationError(detail="Native reference ownership could not be verified")
    found: dict[str, str] = {}
    for candidate in cast(list[Any], payload[2]):
        raw: Any = candidate
        if not isinstance(raw, list):
            raise ConfigurationError(detail="Native reference inventory is malformed")
        raw = cast(list[Any], raw)
        if len(raw) < 3 or raw[1] != project:
            raise ConfigurationError(detail="Native reference inventory has unrelated identities")
        media, workflow = _uuid(raw[0]), _uuid(raw[2])
        if media in found or not workflow:
            raise ConfigurationError(detail="Native reference inventory is ambiguous")
        arms = [isinstance(_at(raw, n), list) for n in (6, 7, 10)]
        found[media] = (
            "image"
            if arms == [True, False, False]
            else "audio"
            if arms == [False, False, True]
            else "other"
        )
    if any(found.get(v) != "image" for v in images) or any(found.get(v) != "audio" for v in audio):
        raise ConfigurationError(
            detail="Native video ingredients require owned typed image/audio assets"
        )


def _unknown(
    started: NativeReferenceVideoStarted, phase: str = "video_submit"
) -> NativeVideoGenerationUnknownError:
    return NativeVideoGenerationUnknownError(
        project_id=started.project_id,
        media_ids=started.media_ids,
        workflow_ids=started.workflow_ids,
        phase=cast(Any, phase),
    )


async def list_native_reference_models(
    client: FlowApiClient, project_id: str, *, with_audio: bool = False
) -> list[dict[str, Any]]:
    project = _uuid(project_id)
    page = await client._checkout_page()
    try:
        await page.goto(f"https://flow.google.com/project/{project}", wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
        models = await _read_native(page, "HTrJv", [], project)
        tier = await _read_native(page, "nzlxg", [], project)
        return parse_extension_models(
            models, tier=tier[3], required_requirements=(1, 6, 18, 19) if with_audio else (1, 6)
        )
    finally:
        client._checkin_page(page)


async def generate_native_reference_video(
    client: FlowApiClient,
    *,
    project_id: str,
    prompt: str,
    reference_image_ids: tuple[str, ...] = (),
    reference_audio_ids: tuple[str, ...] = (),
    reference_character_ids: tuple[str, ...] = (),
    reference_slot_ids: Mapping[str, str] | None = None,
    model_key: str | None = None,
    count: int = 1,
    aspect: str = "16:9",
    duration: int | None = None,
    resolution: str = "720p",
    on_started: Callable[[NativeReferenceVideoStarted], Awaitable[None]] | None = None,
) -> NativeReferenceVideoStarted:
    images, audio, characters = _references(
        reference_image_ids, reference_audio_ids, reference_character_ids
    )
    slots = None
    if reference_slot_ids is not None:
        slots = {
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
    started = new_reference_started(project_id, count)
    reference_args(
        started,
        prompt=prompt,
        image_ids=images,
        audio_ids=audio,
        character_ids=characters,
        reference_slots=slots,
        model_key=model_key or "discovery",
        aspect=aspect,
        resolution=resolution,
        token="validation",
    )
    if duration is not None and (type(duration) is not int or not 1 <= duration <= 60):
        raise ConfigurationError(detail="Native duration must match an available model usage")
    page = await client._checkout_page()
    try:
        payload = await read_project_payload(page, started.project_id)
        if reference_slot_ids is not None:
            slots = classify_video_slots(payload, started.project_id, dict(reference_slot_ids))
            plan = resolve_reference_markers(prompt, surface="video", slots=slots)
            images, audio, characters = plan.image_ids, plan.audio_ids, plan.character_ids
            _references(images, audio, characters)
        owned_audio = validate_audio_presets(payload, audio)
        validate_reference_assets(payload, started.project_id, images, owned_audio)
        weights = character_reference_counts(payload, started.project_id, characters)
        models = await _read_native(page, "HTrJv", [], started.project_id)
        tier = await _read_native(page, "nzlxg", [], started.project_id)
        options = parse_extension_models(
            models, tier=tier[3], required_requirements=(1, 6, 18, 19) if audio else (1, 6)
        )
        from gflow_cli.api.transports.batchexecute import _at

        selected: list[dict[str, Any]] = []
        for row in options:
            if model_key is not None and row["model_key"] != model_key:
                continue
            # Alias-free SDK default may select only confirmed Omni Flash family, not Veo.
            if model_key is None and "omni" not in str(row.get("display_name", "")).lower():
                continue
            if model_key is None and "flash" not in str(row.get("display_name", "")).lower():
                continue
            limits = model_reference_limits(models, row["model_key"])
            if not reference_capacity(len(images), len(audio), weights, limits):
                continue
            if {"16:9": 2, "9:16": 1, "1:1": 0}[aspect] not in (row.get("aspect_enums") or []):
                continue
            if duration is not None and row["duration"] != duration:
                continue
            if resolution != "720p" and {"360p": 4, "1080p": 2, "4k": 3}[resolution] not in (
                row.get("resolution_enums") or []
            ):
                continue
            selected.append(row)
        if not selected:
            raise ConfigurationError(
                detail="No available model matches these controls; discover and supply modelKey"
            )
        key = min(selected, key=lambda x: x["credits"])["model_key"]
        from gflow_cli.api._engine import mint_evaluate_kwargs
        from gflow_cli.api.recaptcha import TokenMinter

        token = await TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs()).mint(
            "VIDEO_GENERATION"
        )
        args = reference_args(
            started,
            prompt=prompt,
            image_ids=images,
            audio_ids=audio,
            character_ids=characters,
            reference_slots=slots,
            model_key=key,
            aspect=aspect,
            resolution=resolution,
            token=token,
        )
        if on_started:
            await on_started(started)
        try:
            native_captcha_submission()
            result = await page.evaluate(
                _NATIVE_FETCH,
                {"rpc": "MZZa6b", "args": args, "source": f"/project/{started.project_id}"},
                **page_owned_evaluate_kwargs(),
            )
            refusal = _submit_refusal(
                result["text"], ("MZZa6b",), model_key=key, operation="videos/reference"
            )
            if refusal is not None:
                raise refusal
            if result["status"] != 200 or rpc_errors(result["text"]):
                raise _unknown(started)
            acknowledgments: list[tuple[Any, Any]] = []
            for name, value in parse_frames(result["text"]):
                if name == "MZZa6b":
                    for row in cast(list[Any], _at(value, 3) or []):
                        if _at(row, 1) != started.project_id:
                            raise _unknown(started)
                        acknowledgments.append((_at(row, 0), _at(row, 2)))
            if len(acknowledgments) != count or set(acknowledgments) != set(
                zip(started.media_ids, started.workflow_ids, strict=True)
            ):
                raise _unknown(started)
            native_captcha_outcome("accepted")
            return started
        except NativeVideoGenerationUnknownError:
            raise
        except (WafRejectionError, ContentPolicyError, NativeQuotaError):
            native_captcha_outcome("rejected")
            raise
        except Exception:
            raise _unknown(started) from None
    finally:
        client._checkin_page(page)


async def wait_native_reference_video(
    client: FlowApiClient, started: NativeReferenceVideoStarted, *, timeout_s: float = 600
) -> tuple[Any, ...]:

    import asyncio
    import math

    from gflow_cli.api.transports.batchexecute import GenerationRecord, _at

    if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 900:
        raise ConfigurationError(detail="Native video wait requires a finite bounded timeout")
    page = await client._checkout_page()
    deadline = asyncio.get_running_loop().time() + timeout_s
    completed: dict[str, GenerationRecord] = {}
    try:
        while len(completed) < len(started.media_ids):
            for media, workflow in zip(started.media_ids, started.workflow_ids, strict=True):
                if media in completed:
                    continue
                try:
                    result = await page.evaluate(
                        _NATIVE_FETCH,
                        {
                            "rpc": "as29s",
                            "args": [media],
                            "source": f"/project/{started.project_id}",
                        },
                        **page_owned_evaluate_kwargs(),
                    )
                    if result["status"] != 200 or rpc_errors(result["text"]):
                        raise _unknown(started, "video_poll")
                    for name, row in parse_frames(result["text"]):
                        if name != "as29s":
                            continue
                        if not isinstance(row, list) or row[:3] != [
                            media,
                            started.project_id,
                            workflow,
                        ]:
                            raise _unknown(started, "video_poll")
                        row = cast(list[Any], row)
                        status = _at(row, 5, 8, 0)
                        if status in {4, 5, 7}:
                            raise _unknown(started, "video_poll")
                        url = _at(row, 7, 0, 8)
                        if status == 3 and isinstance(url, str) and url.startswith("https://"):
                            completed[media] = GenerationRecord(
                                workflow, started.project_id, media, status, video_url=url
                            )
                except NativeVideoGenerationUnknownError:
                    raise
                except Exception:
                    raise _unknown(started, "video_poll") from None
            remaining = deadline - asyncio.get_running_loop().time()
            if len(completed) < len(started.media_ids):
                if remaining <= 0:
                    raise _unknown(started, "video_poll")
                await asyncio.sleep(min(5, remaining))
        return tuple(completed[media] for media in started.media_ids)
    finally:
        client._checkin_page(page)
