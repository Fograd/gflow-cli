"""All canonical requested identities are checked before solving the shared token."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides
from gflow_cli.errors import WireFormatError
from tests.api.test_native_video_batch_codec import P, S, body

TOKEN = "valid-private-test-token-" * 3


def cap_body(rpc, seeds=S):
    values = parse_qs(body(rpc, seeds=seeds))
    frames = json.loads(values["f.req"][0])
    args = json.loads(frames[0][0][1])
    args[1] = [None] * 11
    args[1][5] = P
    args[1][10] = [TOKEN, 1]
    frames[0][0][1] = json.dumps(args)
    return urlencode({"f.req": json.dumps(frames)})


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
async def test_entire_vector_fresh_and_one_common_token(rpc):
    previous = set()
    mint = AsyncMock(return_value=TOKEN)
    override = VideoOverrides(P, 2, mint, previous_request_ids=previous)
    changed = await override.apply(
        SimpleNamespace(url="https://flow.google.com/project/" + P), cap_body(rpc)
    )
    assert previous == set(S) and mint.await_count == 1
    frame = json.loads(parse_qs(changed)["f.req"][0])[0][0]
    args = json.loads(frame[1])
    assert len(args[0]) == 2 and args[1][10] == [TOKEN, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
@pytest.mark.parametrize("bad", ["reused_first", "reused_second", "case_duplicate"])
async def test_any_bad_member_refuses_without_solving_or_consuming_set(rpc, bad):
    previous = {S[0]} if bad == "reused_first" else {S[1]} if bad == "reused_second" else set()
    original = set(previous)
    mint = AsyncMock(return_value=TOKEN)
    override = VideoOverrides(P, 2, mint, previous_request_ids=previous)
    seed = "abcdef12-abcd-4abc-8abc-abcdef123456"
    seeds = (seed, seed.upper()) if bad == "case_duplicate" else S
    with pytest.raises(WireFormatError):
        await override.apply(
            SimpleNamespace(url="https://flow.google.com/project/" + P), cap_body(rpc, seeds)
        )
    mint.assert_not_awaited()
    assert previous == original
