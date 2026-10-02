"""Opt-in metadata-only BDD; existing image refs must already be decoded/owned."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_characters import CharacterBindingError, mutate_character
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/selfhost_character_voice_assignment.feature")


@given(
    "an authenticated profile and two owned existing image media for a preset assignment",
    target_fixture="reference_case",
)
def reference_case(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    keys = (
        "PROFILE",
        "HOME",
        "RESOURCES_PROJECT",
        "CHARACTER_FIRST_MEDIA",
        "CHARACTER_SECOND_MEDIA",
    )
    values = {key: os.environ.get(f"GFLOW_CLI_E2E_{key}", "") for key in keys}
    if not all(values.values()):
        pytest.skip("Second-reference BDD requires documented existing image E2E inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return values


async def _exercise(case: dict[str, Any]) -> dict[str, Any]:
    project = case["RESOURCES_PROJECT"]
    first, second = case["CHARACTER_FIRST_MEDIA"], case["CHARACTER_SECOND_MEDIA"]
    entity = ""
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]

        async def guard(route: Any) -> None:
            request = route.request
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                await route.continue_()
                return
            location = urlsplit(request.url)
            if location.hostname == "flow.google.com" and "batchexecute" in location.path:
                try:
                    wrapper = json.loads(parse_qs(request.post_data or "")["f.req"][0])
                    ids = {row[0] for group in wrapper for row in group}
                    allowed = {
                        "UpteDb",
                        "Zzl0ze",
                        "tRARke",
                        "as29s",
                        "ngNC2",
                        "o30O0e",
                        "KV2T2d",
                        "HTrJv",
                        "nzlxg",
                        "Yizz8d",
                        "ve2Lsc",
                        "yBhWQ",
                        "NfrxTb",
                        "cPZSdc",
                        "qJcgMc",
                        "LPzVkd",
                        "mrlkwd",
                        "GN0Bre",
                        "xI9TVb",
                        "C4BZMd",
                        "Sc7aEb",
                        "cz8Z4b",
                        "rzMKMb",
                    }
                    if ids <= allowed:
                        await route.continue_()
                        return
                except (ValueError, KeyError, TypeError):
                    pass
            await route.abort()

        await page.route("**/*", guard)
        try:
            created = await mutate_character(
                page,
                project,
                "create",
                name="Owned preset metadata BDD",
                personality="Calm metadata",
                voice="Charon",
                source_media_id=first,
                second_media_id=second,
                image_reference_confirmed=True,
            )
            entity = created["character"]["entity_id"]
            assert created["character"]["voice"] == "Charon"
            assert created["character"]["personality"] == "Calm metadata"
            updated = await mutate_character(page, project, "update", entity, voice="Charon")
            assert updated["character"]["voice"] == "Charon"
            assert updated["character"]["display_name"] == "Owned preset metadata BDD"
            assert updated["character"]["personality"] == "Calm metadata"
            before_refs = updated["character"]["workflow_ids"]
            cleared = await mutate_character(page, project, "update", entity, personality="")
            assert cleared["character"]["personality"] is None
            assert cleared["character"]["voice"] == "Charon"
            assert cleared["character"]["workflow_ids"] == before_refs
            assert cleared["character"]["display_name"] == "Owned preset metadata BDD"
            refs = cleared["character"]["workflow_ids"]
            assert len(refs) == len(set(refs)) == 2
            data = await read_project_payload(page, project)
            original = [
                row
                for row in project_media(data, project)
                if row["media_id"] in {first, second} and not row["archived"]
            ]
            assert {row["media_id"] for row in original} == {first, second}
            assert set(refs).isdisjoint({row["workflow_id"] for row in original})
            return {"refs": refs, "originals": [first, second]}
        except CharacterBindingError as exc:
            entity = exc.entity_id
            raise
        finally:
            try:
                if entity:
                    await mutate_character(page, project, "delete", entity)
                    final = await read_project_payload(page, project)
                    assert entity not in {
                        row["entity_id"] for row in parse_native_characters(final, project)
                    }
                    active = {
                        row["media_id"]
                        for row in project_media(final, project)
                        if not row["archived"]
                    }
                    assert {first, second} <= active
            finally:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


@when(
    "the native character driver assigns then changes the system preset "
    "and deletes the owned character"
)
def copy_references(reference_case: dict[str, Any]) -> None:
    reference_case["result"] = asyncio.run(_exercise(reference_case))


@then("both presets persisted while metadata and source images were preserved")
def verify_references(reference_case: dict[str, Any]) -> None:
    assert len(reference_case["result"]["refs"]) == 2
    assert len(reference_case["result"]["originals"]) == 2
