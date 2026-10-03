"""Measured native character identities and system voice presets (no signed URLs)."""

from __future__ import annotations

from typing import Any, cast

from gflow_cli.api.character import VOICE_NAMES
from gflow_cli.api.transports.migrated_video_upload import is_uuid


def _collection(payload: Any, index: int) -> list[Any]:
    if not isinstance(payload, list) or len(cast("list[Any]", payload)) <= index:
        raise ValueError("Native catalog has an unsupported shape")
    value: Any = cast("list[Any]", payload)[index]
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Native catalog collection is not an array")
    return cast("list[Any]", value)


def parse_native_characters(payload: Any, project_id: str) -> list[dict[str, Any]]:
    if not is_uuid(project_id):
        raise ValueError("Invalid project identifier")
    result: list[dict[str, Any]] = []
    for candidate in _collection(payload, 5):
        if not isinstance(candidate, list):
            raise ValueError("Native entity is not an array")
        row = cast("list[Any]", candidate)
        if len(row) < 4 or row[0] != project_id or not is_uuid(row[1]):
            raise ValueError("Native entity belongs to an unrelated project")
        meta = row[3]
        if not isinstance(meta, list) or len(cast("list[Any]", meta)) < 3:
            raise ValueError("Native entity metadata is unsupported")
        if meta[0] != 1:
            continue
        if not isinstance(meta[2], list):
            raise ValueError("Native character info is not an array")
        info = cast("list[Any]", meta[2])
        refs: list[str] = []
        if info and isinstance(info[0], list):
            for ref in cast("list[Any]", info[0]):
                if isinstance(ref, list) and ref:
                    workflow: Any = cast("list[Any]", ref)[0]
                    if not is_uuid(workflow):
                        raise ValueError("Invalid character reference")
                    refs.append(str(workflow))
        voice = None
        preset_id = None
        audio: Any = info[1] if len(info) > 1 else None
        if isinstance(audio, list) and len(cast("list[Any]", audio)) == 1:
            reference: Any = cast("list[Any]", audio)[0]
            if isinstance(reference, list) and len(cast("list[Any]", reference)) == 1:
                media_voice: Any = cast("list[Any]", reference)[0]
                if is_uuid(media_voice):
                    voice = str(media_voice).lower()
            if isinstance(reference, list) and len(cast("list[Any]", reference)) == 2:
                candidate_id: Any = cast("list[Any]", reference)[1]
                if reference[0] is None and isinstance(candidate_id, str):
                    voice = next((v for v in VOICE_NAMES if v.lower() == candidate_id), None)
                    preset_id = candidate_id if voice else None
        result.append(
            {
                "entity_id": row[1],
                "project_id": project_id,
                "display_name": meta[1] if isinstance(meta[1], str) else "",
                "workflow_ids": refs,
                "voice": voice,
                "preset_voice_id": preset_id,
                "personality": info[2] if len(info) > 2 and isinstance(info[2], str) else None,
                "thumbnail_media_id": row[4] if len(row) > 4 and is_uuid(row[4]) else None,
            }
        )
    return result


def parse_native_voices(payload: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in _collection(payload, 3):
        if not isinstance(candidate, list):
            raise ValueError("Native voice is not an array")
        row = cast("list[Any]", candidate)
        if len(row) < 4 or row[1] != 3 or not isinstance(row[2], str):
            continue
        name = row[2]
        details = row[3]
        if not isinstance(details, list) or len(cast("list[Any]", details)) <= 10:
            raise ValueError("Native voice details are unsupported")
        if not isinstance(details[10], list) or not details[10]:
            raise ValueError("Native voice samples are not an array")
        sample: Any = cast("list[Any]", cast("list[Any]", details)[10])[0]
        if not isinstance(sample, list) or len(cast("list[Any]", sample)) < 4:
            raise ValueError("Native voice sample is unsupported")
        item: dict[str, Any] = {
            "voice": name,
            "source": "system",
            "description": sample[1] if isinstance(sample[1], str) else "",
        }
        expected = f"https://gstatic.com/aitestkitchen/voices/samples/{name}.wav"
        if sample[3] == expected:
            item["sample_url"] = expected
        result.append(item)
    return result
