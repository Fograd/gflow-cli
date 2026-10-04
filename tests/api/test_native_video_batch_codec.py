"""Current field4 video batch codec, no browser or paid calls."""

import json
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.native_extension import assigned_id
from gflow_cli.api.transports.native_video_batch_codec import (
    batch_ack,
    batch_request,
    known_batch_pairs,
)
from gflow_cli.errors import WireFormatError

P = "11111111-1111-4111-8111-111111111111"
S = ("22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333")
W = ("44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555")
FRAME = "66666666-6666-4666-8666-666666666666"
END = "77777777-7777-4777-8777-777777777777"


def body(rpc="YhhmEf", seeds=S, project=P):
    index = {"YhhmEf": 4, "eb1hJf": 5, "nprQif": 6, "MZZa6b": 5}[rpc]
    rows = []
    for seed in seeds:
        row = [None] * (index + 1)
        row[index] = [None, None, None, None, seed]
        if rpc in ("eb1hJf", "nprQif"):
            row[4] = [None, FRAME]
        if rpc == "nprQif":
            row[5] = [None, END]
        if rpc == "MZZa6b":
            row[1] = [[None, FRAME]]
        rows.append(row)
    context = [None] * 6
    context[5] = project
    return urlencode(
        {"f.req": json.dumps([[[rpc, json.dumps([rows, context, ["batch"]]), None, "generic"]]])}
    )


def row(media, workflow, project=P):
    details = [None] * 9
    details[8] = [6]
    return [media, project, workflow, "CAE", None, details, None, [[None], None]]


def payload(rows):
    return [None, 1, [], rows]


@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
def test_source_request_and_exact_reply_all_modes_ordered(rpc):
    request = batch_request(
        body(rpc),
        project_id=P,
        count=2,
        rpcid=rpc,
        start_media_id=FRAME,
        end_media_id=END,
        reference_ids=(FRAME,) if rpc == "MZZa6b" else (),
    )
    expected = tuple(assigned_id(seed) for seed in S)
    assert request.media_ids == expected
    reply = payload([row(expected[1], W[1]), row(expected[0], W[0])])
    assert batch_ack(reply, request) == tuple(zip(expected, W, strict=True))


def test_current_field4_decoder_ignores_legacy_recursive_first_record():
    request = batch_request(body(), project_id=P, count=2, rpcid="YhhmEf")
    reply = payload([row(request.media_ids[0], W[0]), row(request.media_ids[1], W[1])])
    reply[2] = [[row(FRAME, END)]]
    assert batch_ack(reply, request)[0][0] == request.media_ids[0]


@pytest.mark.parametrize(
    "variant",
    ["partial", "duplicate", "wrongproject", "foreignmedia", "image", "audio", "contradictory"],
)
def test_ambiguous_or_unmatched_reply_refuses_with_only_actual_known_handles(variant):
    request = batch_request(body(), project_id=P, count=2, rpcid="YhhmEf")
    rows = [row(request.media_ids[0], W[0]), row(request.media_ids[1], W[1])]
    if variant == "partial":
        rows.pop()
    if variant == "duplicate":
        rows[1] = rows[0]
    if variant == "wrongproject":
        rows[1][1] = FRAME
    if variant == "foreignmedia":
        rows[1][0] = FRAME
    if variant == "image":
        rows[1][6] = [[None]]
        rows[1][7] = None
    if variant == "audio":
        rows[1][10:] = [[[None]]]
        rows[1][7] = None
    if variant == "contradictory":
        rows[1][6] = [[None]]
    reply = payload(rows)
    with pytest.raises(WireFormatError):
        batch_ack(reply, request)
    known = known_batch_pairs(reply, P)
    assert all(media in [item[0] for item in rows] for media, _ in known)
    assert request.media_ids[0] in [media for media, _ in known]


@pytest.mark.parametrize("count", [1, 5, True])
def test_bad_count_refuses_request(count):
    with pytest.raises(WireFormatError):
        batch_request(body(), project_id=P, count=count, rpcid="YhhmEf")


def test_repeated_seed_case_alias_refuses_before_dispatch():
    seed = "abcdef12-abcd-4abc-8abc-abcdef123456"
    with pytest.raises(WireFormatError):
        batch_request(body(seeds=(seed, seed.upper())), project_id=P, count=2, rpcid="YhhmEf")


@pytest.mark.parametrize("rpc", ["eb1hJf", "nprQif", "MZZa6b"])
def test_every_row_reference_binding_is_checked(rpc):
    raw = json.loads(json.loads(parse_qs(body(rpc))["f.req"][0])[0][0][1])
    if rpc == "MZZa6b":
        raw[0][1][1] = [[None, END]]
    else:
        raw[0][1][4] = [None, END]
    changed = urlencode({"f.req": json.dumps([[[rpc, json.dumps(raw), None, "generic"]]])})
    with pytest.raises(WireFormatError):
        batch_request(
            changed,
            project_id=P,
            count=2,
            rpcid=rpc,
            start_media_id=FRAME,
            end_media_id=END,
            reference_ids=(FRAME,) if rpc == "MZZa6b" else (),
        )
