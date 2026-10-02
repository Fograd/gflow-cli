from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"


def client():
    c = FlowApiClient.__new__(FlowApiClient)
    c._page = SimpleNamespace(url="https://flow.google.com/project/" + P)
    c._page_queue = None
    c.settings = SimpleNamespace(flow_host="auto")
    c._get_json = AsyncMock(side_effect=AssertionError("Retired labs read"))
    return c


@pytest.mark.asyncio
async def test_native_list_dispatches_and_excludes_signed_urls(monkeypatch):
    from gflow_cli.api.transports import migrated_resources as module

    read = AsyncMock(
        return_value=[None, [], [], [], None, [[P, E, None, [1, "Name", [[], None, "Calm"]]]]]
    )
    monkeypatch.setattr(module, "read_project_payload", read)
    rows = await client().list_characters(P)
    assert rows[0].entity_id == E
    assert rows[0].personality == "Calm"
    assert rows[0].voice is None
    read.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_create_partial_retains_ref_and_returns_page(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module
    from gflow_cli.errors import CharacterMutationUnknownError, is_retryable

    mutate = AsyncMock(side_effect=module.CharacterBindingError(E))
    monkeypatch.setattr(module, "mutate_character", mutate)
    c = client()
    c._checkin_page = AsyncMock()  # replaced below with sync count collector
    checked = []
    c._checkin_page = checked.append
    with pytest.raises(CharacterMutationUnknownError) as caught:
        await c.create_character_from_images(
            project_id=P, display_name="Name", media_id=M, image_reference_confirmed=True
        )
    assert caught.value.to_problem_details()["character_ref"] == E
    assert caught.value.to_problem_details()["project_id"] == P
    assert not is_retryable(caught.value)
    assert checked == [c._page]
    assert mutate.await_count == 1


@pytest.mark.asyncio
async def test_native_create_requires_decoded_image_assertion_before_page(monkeypatch):
    c = client()
    c._checkout_page = AsyncMock(side_effect=AssertionError("No checkout"))
    with pytest.raises(ConfigurationError):
        await c.create_character_from_images(project_id=P, display_name="Name", media_id=M)


@pytest.mark.asyncio
async def test_native_delete_validates_entire_request_before_mutation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as mutations
    from gflow_cli.api.transports import migrated_resources as module

    monkeypatch.setattr(
        module,
        "read_project_payload",
        AsyncMock(return_value=[None, [], [], [], None, [[P, E, None, [1, "Name", []]]]]),
    )
    mutate = AsyncMock()
    monkeypatch.setattr(mutations, "mutate_character", mutate)
    with pytest.raises(ConfigurationError):
        await client().delete_characters(P, [E, M])
    mutate.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs", [dict(image_reference_2=M), dict(personality="x" * 2001), dict(display_name="")]
)
def test_create_service_input_boundaries(kwargs):
    from gflow_cli.services.native_characters import validate_create_inputs

    values = dict(project_id=P, display_name="Name", image_reference_1=M)
    values.update(kwargs)
    with pytest.raises(ConfigurationError):
        validate_create_inputs(**values)


@pytest.mark.asyncio
async def test_sdk_voice_only_update_forwards_canonical_voice(monkeypatch):
    from gflow_cli.api import native_characters as module

    row = {
        "entity_id": E,
        "project_id": P,
        "display_name": "Name",
        "workflow_ids": [],
        "voice": "Charon",
    }
    mutate = AsyncMock(return_value={"character": row})
    monkeypatch.setattr(module, "mutate_native", mutate)
    char = await client().update_character(project_id=P, entity_id=E, voice=" cHaRoN ")
    assert mutate.await_args.kwargs["voice"] == "Charon"
    assert char.voice == "Charon"


@pytest.mark.asyncio
async def test_native_list_invalid_project_fails_before_page_checkout():
    c = client()
    c._checkout_page = AsyncMock(side_effect=AssertionError("No checkout"))
    with pytest.raises(ConfigurationError):
        await c.list_characters("not-a-uuid")


@pytest.mark.asyncio
async def test_batch_delete_retains_completed_refs_on_second_preflight_refusal(monkeypatch):
    from gflow_cli.api import native_characters as module
    from gflow_cli.api.character import Character
    from gflow_cli.errors import EXIT_CODE_MAP, CharacterBatchPartialError, is_retryable

    c = client()
    c.list_characters = AsyncMock(
        return_value=[
            Character(E, "First", P, (), None, None, None),
            Character(M, "Second", P, (), None, None, None),
        ]
    )
    mutate = AsyncMock(side_effect=[{"deleted": [E]}, ConfigurationError(detail="No longer owned")])
    monkeypatch.setattr(module, "mutate_native", mutate)
    with pytest.raises(CharacterBatchPartialError) as caught:
        await c.delete_characters(P, [E, M])
    detail = caught.value.to_problem_details()
    assert detail["completed_character_refs"] == [E]
    assert detail["character_ref"] == M
    assert detail["failed_before_mutation"] is True
    assert detail["type"].endswith("/character-batch-partial")
    assert EXIT_CODE_MAP[CharacterBatchPartialError] == 40
    assert not is_retryable(caught.value)
    assert mutate.await_count == 2


@pytest.mark.asyncio
async def test_batch_delete_first_preflight_refusal_preserves_configuration_error(monkeypatch):
    from gflow_cli.api import native_characters as module
    from gflow_cli.api.character import Character

    c = client()
    c.list_characters = AsyncMock(
        return_value=[
            Character(E, "First", P, (), None, None, None),
            Character(M, "Second", P, (), None, None, None),
        ]
    )
    mutate = AsyncMock(side_effect=ConfigurationError(detail="No longer owned"))
    monkeypatch.setattr(module, "mutate_native", mutate)
    with pytest.raises(ConfigurationError):
        await c.delete_characters(P, [E, M])
    assert mutate.await_count == 1
