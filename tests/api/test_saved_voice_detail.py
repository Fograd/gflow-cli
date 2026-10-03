"""Source-derived saved-TTS detail must retain exact ownership and base preset."""

from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import native_voices as module

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def detail():
    metadata = [None] * 10
    metadata[9] = 1
    return [
        M,
        P,
        W,
        None,
        None,
        metadata,
        None,
        None,
        None,
        None,
        [
            [
                "Guide",
                "Warm",
                False,
                "https://flow-content.google/audio/test",
                "charon",
                None,
                "Hello",
                "Expressive",
            ]
        ],
    ]


@pytest.mark.asyncio
async def test_detail_uses_strict_rpc_and_refreshes_full_fields(monkeypatch):
    from gflow_cli.api.transports import migrated_rpc

    monkeypatch.setattr(
        module,
        "list_saved_voices",
        AsyncMock(
            return_value={
                "voices": [{"ref": M, "project_id": P, "workflow_id": W, "display_name": "Guide"}]
            }
        ),
    )
    rpc = AsyncMock(return_value=detail())
    monkeypatch.setattr(migrated_rpc, "native_rpc", rpc)
    result = await module.get_saved_voice(None, P, M)
    assert result["preset_voice"] == "Charon"
    assert result["dialogue"] == "Hello"
    assert result["performance"] == "Warm"
    assert result["description"] == "Expressive"
    assert result["audio_url"].startswith("https://flow-content.google/audio/")
    rpc.assert_awaited_once_with(None, "as29s", [M], "/project/" + P, require_single=True)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_foreign_audio_identity_refuses(index):
    row = detail()
    row[index] = "44444444-4444-4444-8444-444444444444"
    with pytest.raises(ValueError):
        module.saved_voice_detail_fields(row, project_id=P, media_id=M, workflow_id=W)


def test_missing_playback_is_optional_without_fabricated_url():
    row = detail()
    row[10][0][3] = None
    result = module.saved_voice_detail_fields(row, project_id=P, media_id=M, workflow_id=W)
    assert "audio_url" not in result and result["preset_voice"] == "Charon"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/a",
        "https://user:pass@example.org/a",
        "https://example.org:8443/a",
        "https://example.org/a#fragment",
    ],
)
def test_malformed_playback_refuses(url):
    row = detail()
    row[10][0][3] = url
    with pytest.raises(ValueError):
        module.saved_voice_detail_fields(row, project_id=P, media_id=M, workflow_id=W)


def test_audio_union_is_exclusive():
    row = detail()
    row[6] = [[]]
    with pytest.raises(ValueError):
        module.saved_voice_detail_fields(row, project_id=P, media_id=M, workflow_id=W)


def test_base_voice_uses_source_speaker_fallback_without_guessing_title():
    row = detail()
    row[10][0][4] = None
    row[10][0].extend([None, None, None, [["voices/charon"]]])
    result = module.saved_voice_detail_fields(row, project_id=P, media_id=M, workflow_id=W)
    assert result["preset_voice"] == "Charon"
    row[10][0][11] = [["unknown-custom-name"]]
    assert "preset_voice" not in module.saved_voice_detail_fields(
        row, project_id=P, media_id=M, workflow_id=W
    )
