"""Offline public adapter and codec BDD; no Flow surface or solver."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.mcp import tools
from gflow_cli.worker.codec import decode_payload, encode_payload

scenarios("generic_image_captcha_mirrors.feature")
PROJECT = "11111111-1111-4111-8111-111111111111"
TOKEN = "synthetic-private-image-token-" * 3


@pytest.fixture
def state():
    return {}


@given("a synthetic queued image tool with no browser")
def synthetic_tool(monkeypatch, state):
    state["queue"] = AsyncMock(return_value={"status": "queued", "task_id": "fixture"})
    monkeypatch.setattr(tools, "_run_generation_task", state["queue"])
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    state["registered"] = tools.server._tool_manager.get_tool("gflow_generate_image")


def call(state, **controls):
    data = state["registered"].fn_metadata.arg_model.model_validate(
        {
            "prompt": "Fixture",
            "project": PROJECT,
            "count": 2,
            "wait": False,
            **controls,
        }
    )
    state["result"] = asyncio.run(state["registered"].fn(**data.model_dump()))


@when("a registered image call requests CapSolver and one total attempt")
def requested_controls(state):
    call(state, captcha_order="CapSolver", captcha_retry=1)


@then("the image queue codec retains only nonsecret provider controls")
def retained_controls(state):
    assert state["result"]["status"] == "queued"
    fields = state["queue"].await_args.kwargs["payload"]
    encoded = encode_payload("t2i", decode_payload("t2i", fields))
    assert encoded["captchaOrder"] == "CapSolver" and encoded["captchaRetry"] == 1
    assert "captcha_token" not in encoded and "captchaSecret" not in encoded


@when("a registered image call supplies a confidential token")
def supplied_token(state):
    call(state, captcha_token=TOKEN)


@then("no confidential image input reaches the durable queue")
def refused_token(state):
    assert state["result"]["status"] == "error" and TOKEN not in str(state["result"])
    state["queue"].assert_not_called()
