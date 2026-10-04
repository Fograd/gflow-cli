"""Offline proof of fresh VIDEO reload metadata and retry request identities."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from gflow_cli.api.transports.migrated_image_overrides import reload_metadata
from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides
from gflow_cli.errors import WireFormatError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
KEY = "trusted_sitekey_123456789012345"
TOKEN = "valid-private-test-token-" * 3


def reload_body(action):
    action = action.encode()
    key = KEY.encode()
    return bytes([66, len(action)]) + action + bytes([114, len(key)]) + key


def url():
    return "https://www.google.com/recaptcha/enterprise/reload?k=" + KEY


def test_video_metadata_is_explicit_and_image_default_preserved():
    assert reload_metadata(
        url(), reload_body("VIDEO_GENERATION"), expected_action="VIDEO_GENERATION"
    ) == {"sitekey": KEY, "action": "VIDEO_GENERATION"}
    with pytest.raises(ValueError):
        reload_metadata(url(), reload_body("VIDEO_GENERATION"))
    assert reload_metadata(url(), reload_body("IMAGE_GENERATION"))["action"] == "IMAGE_GENERATION"


@pytest.mark.parametrize(
    "destination",
    [
        "https://www.google.com:443/recaptcha/enterprise/reload",
        "https://user@www.google.com/recaptcha/enterprise/reload",
        "https://example.test/recaptcha/enterprise/reload",
    ],
)
def test_metadata_refuses_nonexact_trusted_origin(destination):
    assert (
        reload_metadata(
            destination + "?k=" + KEY,
            reload_body("VIDEO_GENERATION"),
            expected_action="VIDEO_GENERATION",
        )
        is None
    )


def test_observer_lifecycle_scope_and_method():
    events = {}
    page = SimpleNamespace(
        url="https://flow.google.com/project/" + P,
        on=lambda key, cb: events.update({key: cb}),
        remove_listener=lambda key, cb: events.pop(key),
    )
    override = VideoOverrides(P, 1, token=AsyncMock(), metadata_required=True)
    override.capture_metadata(page)
    request = SimpleNamespace(
        method="GET", url=url(), post_data_buffer=reload_body("VIDEO_GENERATION")
    )
    events["request"](request)
    assert override.metadata is None
    request.method = "POST"
    events["request"](request)
    assert override.metadata["action"] == "VIDEO_GENERATION"
    override.stop_capture(page)
    override.close()
    assert not events and override.metadata is None


def body(rpc, requested=M):
    index = {"YhhmEf": 4, "eb1hJf": 5, "nprQif": 6, "MZZa6b": 5}[rpc]
    row = [None] * (index + 1)
    row[index] = [None, None, None, None, requested]
    ctx = [None] * 11
    ctx[5] = P
    ctx[10] = [TOKEN, 1]
    return urlencode(
        {"f.req": json.dumps([[[rpc, json.dumps([[row], ctx, ["batch"]]), None, "generic"]]])}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
async def test_each_mode_reused_requested_identity_refuses_before_second_token(rpc):
    previous = set()
    mint = AsyncMock(return_value=TOKEN)
    first = VideoOverrides(P, 1, token=mint, previous_request_ids=previous)
    await first.apply(None, body(rpc))
    second = VideoOverrides(P, 1, token=mint, previous_request_ids=previous)
    with pytest.raises(WireFormatError, match="reuse"):
        await second.apply(None, body(rpc))
    assert mint.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
async def test_retry_uuid_case_alias_refuses_before_second_token(rpc):
    previous = set()
    mint = AsyncMock(return_value=TOKEN)
    identifier = "abcdef12-abcd-4abc-8abc-abcdef123456"
    first = VideoOverrides(P, 1, token=mint, previous_request_ids=previous)
    await first.apply(None, body(rpc, identifier))
    second = VideoOverrides(P, 1, token=mint, previous_request_ids=previous)
    with pytest.raises(WireFormatError, match="reuse"):
        await second.apply(None, body(rpc, identifier.upper()))
    assert mint.await_count == 1
