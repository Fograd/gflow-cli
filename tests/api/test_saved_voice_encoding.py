import pytest

from gflow_cli.api.transports.native_voices import preview_payload, save_payloads

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def test_preview_matches_frontend_field_numbers():
    payload = preview_payload(
        P,
        preset="charon",
        dialogue="Hello",
        performance="Warm",
        display_name="Guide",
        captcha_token="private-test-token",
    )
    assert payload == [
        [["Hello", [["Charon", "Guide"]], "gemini_v4s_tts_flow", "Warm", 2]],
        [None, 22, None, None, None, P, None, None, None, None, ["private-test-token", 1]],
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("dialogue", ""),
        ("dialogue", "a" * 121),
        ("performance", ""),
        ("performance", "a" * 121),
        ("display_name", ""),
        ("display_name", "a" * 201),
        ("preset", "not-a-preset"),
        ("captcha_token", ""),
    ],
)
def test_invalid_create_fields_rejected(field, value):
    params = dict(
        preset="Charon",
        dialogue="Hello",
        performance="Warm",
        display_name="Guide",
        captcha_token="private-test-token",
    )
    params[field] = value
    with pytest.raises(ValueError):
        preview_payload(P, **params)


def test_save_metadata_distinct_masks():
    media, workflow = save_payloads(P, M, W, "Guide")
    assert media == [
        [M, None, None, None, None, [None] * 9 + [1]],
        [["media.media_metadata.visibility"]],
    ]
    assert workflow == [[W, None, None, ["Guide"], P], [["metadata.display_name"]]]


def test_bad_project_rejected_without_secret_echo():
    with pytest.raises(ValueError) as caught:
        preview_payload(
            "secret-project",
            preset="Charon",
            dialogue="Hello",
            performance="Warm",
            display_name="Guide",
            captcha_token="secret-token",
        )
    assert "secret" not in str(caught.value)


def test_saved_voice_parser_only_owned_visible_audio():
    from gflow_cli.api.transports.native_voices import parse_saved_voices

    metadata = [None] * 9 + [1]
    audio = [[None, "Warm", None, "https://example.invalid/private", None, None, "Hello"]]
    media = [M, P, W, None, None, metadata, None, None, None, None, audio]
    workflow = [W, None, None, ["Guide", None, False, None, M], P]
    payload = [None, [workflow], [media]]
    rows = parse_saved_voices(payload, P)
    assert rows == [
        {
            "ref": M,
            "project_id": P,
            "workflow_id": W,
            "display_name": "Guide",
            "performance": "Warm",
            "dialogue": "Hello",
        }
    ]
    assert "http" not in str(rows)


def test_saved_voice_parser_rejects_foreign_and_ambiguous_union():
    from gflow_cli.api.transports.native_voices import parse_saved_voices

    metadata = [None] * 9 + [1]
    media = [M, P, W, None, None, metadata, [1], None, None, None, [[None, "Warm"]]]
    with pytest.raises(ValueError):
        parse_saved_voices([None, [], [media]], P)


def test_preview_identity_uses_exact_media_context():
    from gflow_cli.api.transports.native_voices import preview_identity

    assert preview_identity([[[M, P, W]], []], P) == (M, W)
    with pytest.raises(ValueError):
        preview_identity([[[M, W, P]], []], P)


def test_delete_confirmation_rejects_before_page_access():
    import asyncio

    from gflow_cli.api.transports.native_voices import delete_saved_voice

    for value in [False, 1, "true"]:
        with pytest.raises(ValueError):
            asyncio.run(delete_saved_voice(None, P, M, value))


@pytest.mark.parametrize("preset", ["Charon", "charon", "CHARON", "cHaRoN"])
def test_preview_preserves_native_canonical_display_case(preset):
    payload = preview_payload(
        P,
        preset=preset,
        dialogue="Hello",
        performance="Warm",
        display_name="Guide",
        captcha_token="token",
    )
    assert payload[0][0][1] == [["Charon", "Guide"]]
