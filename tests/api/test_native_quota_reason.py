import json

import pytest

from gflow_cli.api.transports import batchexecute
from gflow_cli.errors import WireFormatError

REASON = "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED"
RPC = "MZZa6b"


def reply(reason=REASON, code=8, extra=None, typed=True):
    detail = [
        "type.googleapis.com/google.rpc.ErrorInfo" if typed else "private.invalid/decoy",
        [reason],
    ]
    row = ["wrb.fr", RPC, None, None, None, [code, None, [detail]], "generic"]
    return ")]}'\n" + json.dumps([row] + (extra or []))


def classify(text):
    return batchexecute.public_quota_refusal(text, (RPC,))


@pytest.mark.parametrize(
    "reason,code",
    [
        ("PUBLIC_ERROR_USER_QUOTA_REACHED", 8),
        ("PUBLIC_ERROR_USER_REQUESTS_THROTTLED", 8),
        ("PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC", 8),
        (REASON, 8),
        ("PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED_UPGRADEABLE", 8),
        ("PUBLIC_ERROR_MODEL_ACCESS_DENIED", 7),
    ],
)
def test_positive_typed_native_reason(reason, code):
    assert classify(reply(reason, code)) == (RPC, code, reason)


@pytest.mark.parametrize(
    "reason,code,typed",
    [
        (REASON, 7, True),
        (REASON, True, True),
        (REASON, 8, False),
        ("PUBLIC_ERROR_UNUSUAL_ACTIVITY", 7, True),
        ("PUBLIC_ERROR_UNSAFE_GENERATION", 8, True),
        ("PUBLIC_ERROR_WORKSPACE_ACCOUNT_QUOTA_REACHED", 8, True),
    ],
)
def test_unproven_quota_never_classified(reason, code, typed):
    assert classify(reply(reason, code, typed=typed)) is None


@pytest.mark.parametrize("payload", [None, json.dumps(["known-accepted-handle"]), json.dumps([5])])
def test_mixed_same_rpc_remains_unknown(payload):
    extra = [["wrb.fr", RPC, payload, None, None, [5], "generic"]]
    with pytest.raises(WireFormatError):
        classify(reply(extra=extra))


def test_metadata_reason_decoy_is_not_google_errorinfo_reason():
    text = ")]}'\n" + json.dumps(
        [
            [
                "wrb.fr",
                RPC,
                None,
                None,
                None,
                [8, None, [["type.googleapis.com/google.rpc.ErrorInfo", ["different", REASON]]]],
                "generic",
            ]
        ]
    )
    assert classify(text) is None


@pytest.mark.parametrize(
    "enum,reason,code",
    [
        (2, "PUBLIC_ERROR_USER_QUOTA_REACHED", 8),
        (3, "PUBLIC_ERROR_USER_REQUESTS_THROTTLED", 8),
        (32, REASON, 8),
        (34, "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED_UPGRADEABLE", 8),
        (11, "PUBLIC_ERROR_MODEL_ACCESS_DENIED", 7),
        (50, "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC", 8),
    ],
)
def test_primary_public_aitk_enum_reason(enum, reason, code):
    row = [
        "wrb.fr",
        RPC,
        None,
        None,
        None,
        [
            code,
            None,
            [
                [
                    "type.googleapis.com/google.internal.labs.aisandbox.proto.common.v1.PublicAitkError",
                    [enum],
                ]
            ],
        ],
        "generic",
    ]
    assert classify(json.dumps([row])) == (RPC, code, reason)


@pytest.mark.parametrize("enum", [True, 32.0, "32", 48, 70, 71])
def test_unproven_or_other_quota_enum_is_not_mapped_to_local_policy(enum):
    row = [
        "wrb.fr",
        RPC,
        None,
        None,
        None,
        [
            8,
            None,
            [
                [
                    "type.googleapis.com/google.internal.labs.aisandbox.proto.common.v1.PublicAitkError",
                    [enum],
                ]
            ],
        ],
        "generic",
    ]
    assert classify(json.dumps([row])) is None
