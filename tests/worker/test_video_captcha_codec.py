"""Durable worker video controls strictly validate before browser."""

import pytest

from gflow_cli.errors import QueueSchemaError
from gflow_cli.worker.codec import decode_payload

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "changes",
    [
        {"count": 2},
        {"captchaRetry": True},
        {"captchaRetry": 11},
        {"project": None},
        {"captcha_token": "secret-" * 10},
        {"captchaSecret": "/private/file"},
    ],
)
def test_bad_provider_or_confidential_fields_refuse(changes):
    with pytest.raises(QueueSchemaError):
        decode_payload(
            "t2v", {"prompt": "test", "count": 1, "project": P, "captchaRetry": 2, **changes}
        )


def test_provider_nonsecret_controls_roundtrip():
    payload = {"prompt": "test", "count": 1, "project": P, "captchaOrder": "CapSolver"}
    decoded = decode_payload("t2v", payload)
    assert decoded.fields["captchaOrder"] == "CapSolver"
