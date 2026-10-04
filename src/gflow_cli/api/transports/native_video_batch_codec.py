"""Strict current native batch-video request/ack codec, independent of legacy first record."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qsl
from uuid import UUID

from gflow_cli.api.native_extension import assigned_id
from gflow_cli.errors import WireFormatError

VIDEO_RPCS = frozenset(("YhhmEf", "eb1hJf", "nprQif", "MZZa6b"))
_METADATA_INDEX = {"YhhmEf": 4, "eb1hJf": 5, "nprQif": 6, "MZZa6b": 5}


def _uuid(value: object) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("Invalid native video identity")
    result = str(UUID(value))
    if value.lower() != result:
        raise ValueError("Invalid native video identity")
    return result


def _at(value: Any, *indices: int) -> Any:
    for index in indices:
        if not isinstance(value, list) or len(cast(list[Any], value)) <= index:
            return None
        value = cast(list[Any], value)[index]
    return value


@dataclass(frozen=True)
class BatchRequest:
    rpcid: str
    project_id: str
    media_ids: tuple[str, ...]
    workflow_ids: tuple[str | None, ...]


def batch_request(
    body: str,
    *,
    project_id: str,
    count: int,
    rpcid: str,
    start_media_id: str | None = None,
    end_media_id: str | None = None,
    reference_ids: tuple[str, ...] = (),
    character_ids: tuple[str, ...] = (),
) -> BatchRequest:
    """Positive field1 row-vector/context and source-proven metadata UUID assignment."""
    try:
        if (
            type(count) is not int
            or not 2 <= count <= 4
            or rpcid not in VIDEO_RPCS
            or len(body) > 2 * 1024 * 1024
        ):
            raise ValueError()
        project = _uuid(project_id)
        pairs = parse_qsl(body, keep_blank_values=True)
        values = [value for key, value in pairs if key == "f.req"]
        if len(values) != 1:
            raise ValueError()
        frames = json.loads(values[0])
        if (
            not isinstance(frames, list)
            or len(cast(list[Any], frames)) != 1
            or not isinstance(cast(list[Any], frames)[0], list)
            or len(cast(list[Any], frames)[0]) != 1
        ):
            raise ValueError()
        frame: Any = cast(list[Any], cast(list[Any], frames)[0])[0]
        if (
            not isinstance(frame, list)
            or len(cast(list[Any], frame)) != 4
            or cast(list[Any], frame)[0] != rpcid
        ):
            raise ValueError()
        args = json.loads(cast(list[Any], frame)[1])
        rows = _at(args, 0)
        if (
            not isinstance(args, list)
            or len(cast(list[Any], args)) != 3
            or not isinstance(rows, list)
            or len(cast(list[Any], rows)) != count
            or _at(args, 1, 5) != project
        ):
            raise ValueError()
        seeds: list[str] = []
        media: list[str] = []
        workflows: list[str | None] = []
        for row in cast(list[Any], rows):
            seed = _at(row, _METADATA_INDEX[rpcid], 4)
            canonical = _uuid(seed)
            if canonical in seeds:
                raise ValueError()
            seeds.append(canonical)
            media.append(assigned_id(seed))
            workflow_seed = _at(row, _METADATA_INDEX[rpcid], 5)
            if workflow_seed is not None:
                _uuid(workflow_seed)
            workflows.append(assigned_id(workflow_seed) if workflow_seed is not None else None)
            if rpcid in ("eb1hJf", "nprQif") and _at(row, 4, 1) != start_media_id:
                raise ValueError()
            if rpcid == "nprQif" and (end_media_id is None or _at(row, 5, 1) != end_media_id):
                raise ValueError()
            if rpcid == "MZZa6b":
                images: Any = _at(row, 1) or []
                characters: Any = _at(row, 9) or []
                if (
                    not isinstance(images, list)
                    or tuple(_at(item, 1) for item in cast(list[Any], images)) != reference_ids
                ):
                    raise ValueError()
                if (
                    not isinstance(characters, list)
                    or tuple(_at(item, 0) for item in cast(list[Any], characters)) != character_ids
                ):
                    raise ValueError()
        known = [value for value in media + workflows if value is not None]
        if len(known) != len(set(known)) or project in known:
            raise ValueError()
        return BatchRequest(rpcid, project, tuple(media), tuple(workflows))
    except (ValueError, TypeError, IndexError, KeyError):
        raise WireFormatError(
            detail="Native video batch request does not match the exact selected output contract"
        ) from None


def known_batch_pairs(payload: Any, project_id: str) -> tuple[tuple[str, str], ...]:
    """Only actual positive current field4 media/project/workflow rows, never seed guesses."""
    rows = _at(payload, 3)
    if not isinstance(rows, list) or len(cast(list[Any], rows)) > 4:
        return ()
    result: list[tuple[str, str]] = []
    used: set[str] = set()
    for row in cast(list[Any], rows):
        try:
            media, project, workflow = (_uuid(_at(row, i)) for i in range(3))
            if (
                project != project_id
                or len({media, project, workflow}) != 3
                or media in used
                or workflow in used
            ):
                continue
        except (ValueError, TypeError):
            continue
        result.append((media, workflow))
        used.update((media, workflow))
    return tuple(result)


def batch_ack(payload: Any, request: BatchRequest) -> tuple[tuple[str, str], ...]:
    """Exact output cardinality and request-derived media IDs, in requested order."""
    rows = _at(payload, 3)
    try:
        if not isinstance(rows, list) or len(cast(list[Any], rows)) != len(request.media_ids):
            raise ValueError()
        pairs = known_batch_pairs(payload, request.project_id)
        if len(pairs) != len(cast(list[Any], rows)) or {media for media, _ in pairs} != set(
            request.media_ids
        ):
            raise ValueError()
        by_media = dict(pairs)
        for row in cast(list[Any], rows):
            if _at(row, 3) != "CAE":
                raise ValueError()
            if _at(row, 6) is not None or _at(row, 10) is not None:
                raise ValueError()
            if not isinstance(_at(row, 7), list) or _at(row, 7, 0) is None:
                raise ValueError()
        ordered = tuple((media, by_media[media]) for media in request.media_ids)
        if any(
            expected is not None and expected != workflow
            for (_, workflow), expected in zip(ordered, request.workflow_ids, strict=True)
        ):
            raise ValueError()
        return ordered
    except (ValueError, TypeError, KeyError):
        raise WireFormatError(
            detail=(
                "Native video batch acknowledgment is partial, ambiguous "
                "or differs from requested outputs"
            )
        ) from None
