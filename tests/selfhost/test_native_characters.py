from __future__ import annotations

import pytest

from gflow_cli.api.transports.migrated_catalog import parse_native_characters, parse_native_voices
from gflow_cli.api.transports.migrated_characters import update_payload

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"


def test_update_only_touches_requested_fields():
    assert update_payload(P, E, personality="") == [
        [P, E, None, [1, None, [None, None, ""]]],
        [["entity_info.character_info.personality_notes"]],
    ]


@pytest.mark.parametrize("kwargs", [{}, {"name": ""}, {"name": 7}, {"personality": []}])
def test_update_rejects_invalid_values_before_rpc(kwargs):
    with pytest.raises(ValueError):
        update_payload(P, E, **kwargs)


def test_character_personality_has_measured_slot():
    rows = parse_native_characters(
        [None, [], [], [], None, [[P, E, None, [1, "Name", [[], None, "Calm"]]]]], P
    )
    assert rows[0]["personality"] == "Calm"


@pytest.mark.parametrize("info", [None, "not-array", 7])
def test_malformed_character_info_is_explicit_error(info):
    with pytest.raises(ValueError):
        parse_native_characters([None, [], [], [], None, [[P, E, None, [1, "Name", info]]]], P)


def test_malformed_voice_detail_is_explicit_error():
    with pytest.raises(ValueError):
        parse_native_voices([None, [], [], [["voice", 3, "Voice", [None] * 11]]])


@pytest.mark.asyncio
async def test_create_requires_owned_reference_before_mutation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    async def read(page, project):
        return [None, [], [], [], None, []]

    async def rpc(*args):
        pytest.fail("Unowned reference must never cause a mutation")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError, match="existing active"):
        await module.mutate_character(
            None, P, "create", name="Name", workflow_id=E, image_reference_confirmed=True
        )


@pytest.mark.asyncio
async def test_update_refuses_cross_project_entity_before_mutation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    async def read(page, project):
        return [None, [], [], [], None, []]

    async def rpc(*args):
        pytest.fail("Unowned entity must never cause a mutation")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError, match="belong"):
        await module.mutate_character(None, P, "update", E, name="Name")


@pytest.mark.asyncio
async def test_binding_failure_preserves_created_identity_for_recovery(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    media = [{"workflow_id": P, "media_id": E, "archived": False}]
    calls = []

    async def read(page, project):
        return [None, [], [], [], None, []]

    async def rpc(page, project, verb, args):
        calls.append(verb)
        if verb == "C4BZMd":
            return [[P, E, None, [1, "Name", []]]]
        raise ValueError("Binding refused")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "project_media", lambda *args: media)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterBindingError) as error:
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            workflow_id=P,
            source_media_id=E,
            image_reference_confirmed=True,
        )
    assert error.value.entity_id == E
    assert calls == ["C4BZMd", "Sc7aEb"]  # No blind create retry or cleanup of uncertain state.


def test_partial_worker_result_retains_recovery_reference(monkeypatch, capsys):
    import json

    from gflow_cli.selfhost import native_worker as module

    async def fail(*args):
        raise module.CharacterBindingError(E)

    monkeypatch.setattr(module, "execute", fail)
    monkeypatch.setattr(
        module.sys, "argv", ["worker", "character-create", "pro1", json.dumps({"project_id": P})]
    )
    module.main()
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "character_binding_outcome_unknown"
    assert result["createdCharacterRef"] == E
    assert result["project_id"] == P


@pytest.mark.asyncio
async def test_post_creation_timeout_preserves_reference_and_never_retries(monkeypatch):
    import asyncio

    from gflow_cli.api.transports import migrated_characters as module

    calls = []

    async def read(page, project):
        return [None, [], [], [], None, []]

    async def rpc(page, project, verb, args):
        calls.append(verb)
        if verb == "C4BZMd":
            return [[P, E, None, [1, "Name", []]]]
        await asyncio.sleep(1)

    monkeypatch.setattr(module, "POST_MUTATION_TIMEOUT", 0.01)
    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *args: [{"workflow_id": P, "media_id": E, "archived": False}],
    )
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterBindingError) as error:
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            workflow_id=P,
            source_media_id=E,
            image_reference_confirmed=True,
        )
    assert error.value.entity_id == E
    assert calls == ["C4BZMd", "Sc7aEb"]


@pytest.mark.asyncio
async def test_initial_personality_validates_before_creating_entity(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    async def read(*args):
        return [None, [], [], [], None, []]

    async def rpc(*args):
        pytest.fail("Invalid initial metadata must not create an orphan")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError, match="Personality"):
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            personality=["invalid"],
            image_reference_confirmed=True,
            source_media_id=E,
        )


@pytest.mark.asyncio
async def test_delete_timeout_has_recoverable_identity_without_retry(monkeypatch):
    import asyncio

    from gflow_cli.api.transports import migrated_characters as module

    calls = []

    async def read(*args):
        return [None, [], [], [], None, [[P, E, None, [1, "Name", []]]]]

    async def rpc(*args):
        calls.append(args[2])
        await asyncio.sleep(1)

    monkeypatch.setattr(module, "POST_MUTATION_TIMEOUT", 0.01)
    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterDeletionError) as error:
        await module.mutate_character(None, P, "delete", E)
    assert error.value.entity_id == E
    assert calls == ["cz8Z4b"]
