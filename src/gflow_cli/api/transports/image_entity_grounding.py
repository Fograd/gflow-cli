"""Correlate the measured native image entity chunks before Google can act."""

from __future__ import annotations

import json
from typing import Any, cast
from urllib.parse import parse_qs


def entity_submit_problem(
    body: str, project: str, entities: tuple[str, ...], names: tuple[str, ...]
) -> str | None:
    """Require both positional entity chunks and the deduplicated entity vector.

    Measured ogiZ0b row[8] and row[10], 2026-10-03 abort-only capture. No tokens,
    prompts, signed URLs or actual identifiers appear in failure messages.
    """
    problem = "migrated host: image character grounding could not be confirmed before submit"
    if not entities or len(entities) != len(names) or any(not name for name in names):
        return problem
    try:
        rows = image_submit_rows(body, project)
        expected = list(zip(entities, names, strict=True))
        for row in rows:
            if row[7][5] != project or not isinstance(row[10], list):
                return problem
            vector = cast(list[Any], row[10])
            if any(
                not isinstance(item, list) or len(cast(list[Any], item)) != 1 for item in vector
            ):
                return problem
            if {item[0] for item in vector} != set(entities):
                return problem
            inline: list[tuple[str, str]] = []
            for group in row[8]:
                for chunk in group:
                    if (
                        isinstance(chunk, list)
                        and len(cast(list[Any], chunk)) == 2
                        and chunk[0] is None
                        and isinstance(chunk[1], list)
                        and len(cast(list[Any], chunk[1])) == 3
                        and chunk[1][0] is None
                        and chunk[1][1] is None
                    ):
                        entity: Any = cast(list[Any], chunk[1])[2]
                        if (
                            not isinstance(entity, list)
                            or len(cast(list[Any], entity)) != 2
                            or not all(isinstance(item, str) for item in cast(list[Any], entity))
                        ):
                            return problem
                        inline.append((cast(list[str], entity)[0], cast(list[str], entity)[1]))
            if inline != expected:
                return problem
    except (ValueError, TypeError, KeyError, IndexError):
        return problem
    return None


def image_submit_rows(body: str, project: str) -> list[Any]:
    """Read exactly one correlated image RPC without exposing its private envelope."""
    fields = parse_qs(body, keep_blank_values=True)
    encoded = fields["f.req"]
    if len(encoded) != 1:
        raise ValueError("Image submit envelope is ambiguous")
    frames: Any = json.loads(encoded[0])
    if len(frames) != 1 or len(frames[0]) != 1 or frames[0][0][0] != "ogiZ0b":
        raise ValueError("Image submit RPC is ambiguous")
    args: Any = json.loads(frames[0][0][1])
    if args[3][5] != project or not isinstance(args[1], list) or not args[1]:
        raise ValueError("Image submit project or rows do not agree")
    rows = cast(list[Any], args[1])
    if any(row[7][5] != project for row in rows):
        raise ValueError("Image output context belongs to another project")
    return rows
