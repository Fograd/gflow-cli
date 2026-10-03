from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.character_validation import normalize_preset_voice
from gflow_cli.api.transports.migrated_characters import update_payload

P = "11111111-1111-4111-8111-111111111111"
C = "22222222-2222-4222-8222-222222222222"
V = "ABCDEFAB-1234-4234-8234-ABCDEFABCDEF"


def test_saved_voice_normalizes_uuid_before_shared_preflight():
    assert normalize_preset_voice(V) == V.lower()


def test_saved_voice_uses_media_oneof_not_preset_oneof():
    payload = update_payload(P, C, voice=V)
    assert payload[0][3][2][1] == [[V.lower()]]


def test_system_preset_encoding_unchanged():
    assert update_payload(P, C, voice="Charon")[0][3][2][1] == [[None, "charon"]]


@pytest.mark.asyncio
async def test_unowned_saved_voice_refuses_before_character_mutation(monkeypatch):
    from gflow_cli.api.transports import migrated_characters as module

    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    proof = AsyncMock(side_effect=ValueError("Saved voice ownership unavailable"))
    monkeypatch.setattr(module, "get_saved_voice", proof)
    rpc = AsyncMock()
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(ValueError, match="ownership"):
        await module.mutate_character(None, P, "update", entity_id=C, voice=V)
    proof.assert_awaited_once_with(None, P, V.lower())
    rpc.assert_not_awaited()
