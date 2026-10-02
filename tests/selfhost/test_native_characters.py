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


@pytest.mark.asyncio
async def test_second_reference_is_owned_before_any_creation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    async def read(*args):
        return [None, [], [], [], None, []]

    async def rpc(*args):
        pytest.fail("The entire reference set must validate before C4")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *args: [{"workflow_id": P, "media_id": E, "archived": False}],
    )
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError):
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            workflow_id=P,
            source_media_id=E,
            second_media_id=P,
            image_reference_confirmed=True,
        )


def test_owned_batch_member_maps_to_its_active_workflow():
    from gflow_cli.api.transports.migrated_characters import active_media_workflow

    records = [{"workflow_id": P, "media_id": P, "batch_media_ids": [P, E], "archived": False}]
    assert active_media_workflow(records, E) == P
    records[0]["archived"] = True
    with pytest.raises(ValueError):
        active_media_workflow(records, E)


@pytest.mark.asyncio
async def test_second_copy_failure_preserves_created_identity_without_rollback(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    copies = []
    mutations = []

    async def read(*args):
        return [None, [], [], [], None, []]

    async def rpc(page, project, verb, args):
        mutations.append(verb)
        return [[P, E, None, [1, "Name", []]]]

    async def copy(page, project, entity, source, slot):
        copies.append(slot)
        if slot == 1:
            raise ValueError("Secondary copy refused")
        return P, E

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *args: [
            {"workflow_id": P, "media_id": E, "batch_media_ids": [E, P], "archived": False}
        ],
    )
    monkeypatch.setattr(module, "_rpc", rpc)
    monkeypatch.setattr(module, "_copy_image", copy)
    with pytest.raises(module.CharacterBindingError) as error:
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            source_media_id=E,
            second_media_id=P,
            image_reference_confirmed=True,
        )
    assert error.value.entity_id == E
    assert copies == [0, 1]
    assert mutations == ["C4BZMd"]  # No retry, source archive, or uncertain-state deletion.


@pytest.mark.asyncio
async def test_secondary_copy_replacement_is_not_reported_as_success(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    created = False

    async def read(*args):
        entities = [[P, E, None, [1, "Name", [[[E]]]]]] if created else []
        return [None, [], [], [], None, entities]

    async def rpc(*args):
        nonlocal created
        created = True
        return [[P, E, None, [1, "Name", []]]]

    async def copy(page, project, entity, source, slot):
        return (P if slot == 0 else E), E

    monkeypatch.setattr(module, "POST_MUTATION_TIMEOUT", 0.01)
    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *args: [
            {"workflow_id": P, "media_id": E, "batch_media_ids": [E, P], "archived": False}
        ],
    )
    monkeypatch.setattr(module, "_rpc", rpc)
    monkeypatch.setattr(module, "_copy_image", copy)
    with pytest.raises(module.CharacterBindingError):
        await module.mutate_character(
            None,
            P,
            "create",
            name="Name",
            source_media_id=E,
            second_media_id=P,
            image_reference_confirmed=True,
        )


@pytest.mark.asyncio
async def test_private_worker_keeps_both_reference_ids_and_assertion(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from gflow_cli.selfhost import native_worker as module

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def _checkout_page(self):
            return object()

        def _checkin_page(self, page):
            return None

    async def mutate(*args, **kwargs):
        assert kwargs["source_media_id"] == E
        assert kwargs["second_media_id"] == P
        assert kwargs["image_reference_confirmed"] is True
        return {"character": {"entity_id": E}}

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(flow_host="flow.google.com")
    )
    monkeypatch.setattr(module.auth, "profile_dir", lambda _: tmp_path)
    monkeypatch.setattr(module, "FlowApiClient", lambda **kwargs: Client())
    monkeypatch.setattr(module, "mutate_character", mutate)
    result = await module.execute(
        "character-create",
        "profile",
        {
            "project_id": P,
            "media_id": E,
            "second_media_id": P,
            "display_name": "Name",
            "image_reference_confirmed": True,
        },
    )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_create_ack_loss_is_unknown_not_replayable(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    monkeypatch.setattr(
        module,
        "read_project_payload",
        pytest.importorskip("unittest.mock").AsyncMock(return_value=[None, [], [], [], None, []]),
    )
    monkeypatch.setattr(
        module, "project_media", lambda *a: [{"workflow_id": P, "media_id": E, "archived": False}]
    )
    rpc = pytest.importorskip("unittest.mock").AsyncMock(side_effect=ValueError("Lost ack"))
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterCreationError):
        await module.mutate_character(
            None, P, "create", name="Name", source_media_id=E, image_reference_confirmed=True
        )
    assert rpc.await_count == 1


@pytest.mark.asyncio
async def test_update_ack_loss_retains_ref(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    mock = pytest.importorskip("unittest.mock")
    monkeypatch.setattr(
        module,
        "read_project_payload",
        mock.AsyncMock(return_value=[None, [], [], [], None, [[P, E, None, [1, "Name", []]]]]),
    )
    rpc = mock.AsyncMock(return_value=[[P, E, None, [1, "Wrong", []]]])
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterUpdateError) as caught:
        await module.mutate_character(None, P, "update", E, name="Requested")
    assert caught.value.entity_id == E
    assert rpc.await_count == 1


def test_voice_update_measured_mask_and_lowercase():
    assert update_payload(P, E, voice="Charon") == [
        [P, E, None, [1, None, [None, [[None, "charon"]]]]],
        [["entity_info.character_info.audio_references"]],
    ]


@pytest.mark.parametrize("voice", ["", "missing", False, []])
def test_voice_update_rejects_clear_unknown_and_wrong_type(voice):
    with pytest.raises(ValueError):
        update_payload(P, E, voice=voice)


def test_audio_parser_exposes_only_measured_system_identity():
    payload = [
        None,
        [],
        [],
        [],
        None,
        [[P, E, None, [1, "Name", [[], [[None, "charon"]], "Calm"]]]],
    ]
    row = parse_native_characters(payload, P)[0]
    assert row["voice"] == "Charon"
    assert row["preset_voice_id"] == "charon"
    payload[5][0][3][2][1] = [["unmeasured-custom-shape"]]
    assert parse_native_characters(payload, P)[0]["voice"] is None


def voice_project(audio=None):
    details = [None] * 11
    details[10] = [
        [
            "Charon",
            "Description",
            True,
            "https://gstatic.com/aitestkitchen/voices/samples/Charon.wav",
        ]
    ]
    return [
        None,
        [],
        [],
        [["preset", 3, "Charon", details]],
        None,
        [[P, E, None, [1, "Name", [[[P]], audio, "Calm"]]]],
    ]


@pytest.mark.asyncio
async def test_voice_update_ack_and_stale_read_poll_preserve_metadata(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    reads = iter([voice_project(), voice_project(), voice_project([[None, "charon"]])])
    calls = []

    async def read(*args):
        return next(reads)

    async def rpc(page, project, verb, args):
        calls.append(verb)
        assert args == update_payload(P, E, voice="Charon")
        return voice_project([[None, "charon"]])[5]

    async def sleep(*args):
        pass

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    result = await module.mutate_character(None, P, "update", E, voice="Charon")
    assert result["character"]["voice"] == "Charon"
    assert result["character"]["workflow_ids"] == [P]
    assert result["character"]["personality"] == "Calm"
    assert result["character"]["display_name"] == "Name"
    assert calls == ["rzMKMb"]


@pytest.mark.asyncio
async def test_voice_update_wrong_ack_identity_never_replays(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    calls = []

    async def read(*args):
        return voice_project()

    async def rpc(*args):
        calls.append("write")
        rows = voice_project([[None, "charon"]])[5]
        rows[0][1] = P
        return rows

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(module.CharacterUpdateError) as error:
        await module.mutate_character(None, P, "update", E, voice="Charon")
    assert error.value.entity_id == E
    assert calls == ["write"]


@pytest.mark.asyncio
async def test_voice_absent_from_actual_catalog_prevents_all_mutation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    async def read(*args):
        return voice_project()

    async def rpc(*args):
        pytest.fail("Catalog validation precedes mutation")

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError, match="current native"):
        await module.mutate_character(None, P, "update", E, voice="Aoede")


@pytest.mark.asyncio
async def test_voice_rpc_timeout_preserves_identity_without_replay(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    calls = []

    async def read(*args):
        return voice_project()

    async def rpc(*args):
        calls.append("write")
        await module.asyncio.Event().wait()

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    monkeypatch.setattr(module, "POST_MUTATION_TIMEOUT", 0.01)
    with pytest.raises(module.CharacterUpdateError) as error:
        await module.mutate_character(None, P, "update", E, voice="Charon")
    assert error.value.entity_id == E
    assert calls == ["write"]


@pytest.mark.asyncio
async def test_empty_notes_null_ack_and_stale_visibility_are_success(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    cleared = voice_project()
    cleared[5][0][3][2] = [[[P]]]
    reads = iter([voice_project(), cleared, voice_project(), cleared, cleared])
    calls = []

    async def read(*args):
        return next(reads)

    async def rpc(*args):
        calls.append("write")
        return cleared[5]

    async def sleep(*args):
        pass

    monkeypatch.setattr(module, "read_project_payload", read)
    monkeypatch.setattr(module, "_rpc", rpc)
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    result = await module.mutate_character(None, P, "update", E, personality="")
    assert result["character"]["personality"] is None
    assert calls == ["write"]
