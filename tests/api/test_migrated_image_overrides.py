import json
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, rewrite_submit
from gflow_cli.errors import WireFormatError

PROJECT = "11111111-1111-4111-8111-111111111111"


def body(count=1):
    context = [None] * 11
    context[5] = PROJECT
    context[10] = ["browser-token" * 5, 1]
    rows = [[None, None, None, 42, 1, "NARWHAL", None, context.copy()] for _ in range(count)]
    args = [None, rows, count, context, ["batch"]]
    return urlencode(
        {"f.req": json.dumps([[["ogiZ0b", json.dumps(args), None, "generic"]]]), "at": "auth-field"}
    )


def test_seed_and_token_rewrite_preserves_all_other_fields():
    original = body(2)
    result = rewrite_submit(original, project=PROJECT, count=2, seed=0, token="provided-token" * 5)
    args = json.loads(json.loads(parse_qs(result)["f.req"][0])[0][0][1])
    assert [row[3] for row in args[1]] == [0, 1]
    assert args[3][10][0] == "provided-token" * 5
    assert all(row[7][10][0] == "provided-token" * 5 for row in args[1])
    assert parse_qs(result)["at"] == ["auth-field"]
    assert args[1][0][5] == "NARWHAL"


@pytest.mark.parametrize("project,count", [("wrong", 1), (PROJECT, 2)])
def test_wrong_project_or_count_is_refused(project, count):
    with pytest.raises(WireFormatError):
        rewrite_submit(body(), project=project, count=count, seed=3)


def test_corrupt_shape_or_duplicate_form_fields_is_refused():
    for value in ["bad", body() + "&f.req=other"]:
        with pytest.raises(WireFormatError):
            rewrite_submit(value, project=PROJECT, count=1, seed=3)


@pytest.mark.asyncio
async def test_override_is_single_use_and_no_implicit_replay():
    override = ImageOverrides(PROJECT, 1, seed=3)
    await override.apply(None, body())
    with pytest.raises(WireFormatError):
        await override.apply(None, body())


@pytest.mark.asyncio
async def test_submit_guard_uses_captured_override_outside_context():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_composer import _guard_image_submit
    from gflow_cli.api.transports.migrated_image_overrides import active_overrides

    assert active_overrides.get() is None
    override = ImageOverrides(PROJECT, 1, seed=7)
    route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
    request = SimpleNamespace(post_data=body())
    assert await _guard_image_submit(route, request, (), None, override=override) is None
    rewritten = route.continue_.call_args.kwargs["post_data"]
    args = json.loads(json.loads(parse_qs(rewritten)["f.req"][0])[0][0][1])
    assert args[1][0][3] == 7
    assert override.used
    route.abort.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_image_envelope_never_consumes_provider():
    from unittest.mock import AsyncMock

    mint = AsyncMock(return_value="replacement" * 5)
    override = ImageOverrides(PROJECT, 1, token=mint)
    with pytest.raises(WireFormatError):
        await override.apply(None, "invalid")
    mint.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_image_override_consumes_before_provider_await():
    import asyncio
    from types import SimpleNamespace

    entered, release = asyncio.Event(), asyncio.Event()

    async def mint(page):
        entered.set()
        await release.wait()
        return "replacement" * 5

    override = ImageOverrides(PROJECT, 1, token=mint)
    page = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)
    task = asyncio.create_task(override.apply(page, body()))
    await entered.wait()
    try:
        with pytest.raises(WireFormatError):
            await asyncio.wait_for(override.apply(page, body()), timeout=0.05)
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_closed_scope_excludes_late_provider_completion_and_telemetry():
    import asyncio
    from types import SimpleNamespace

    entered, release = asyncio.Event(), asyncio.Event()

    async def mint(page):
        entered.set()
        await release.wait()
        return "replacement" * 5

    phases = []
    override = ImageOverrides(PROJECT, 1, token=mint, observe=phases.append)
    page = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)
    task = asyncio.create_task(override.apply(page, body()))
    await entered.wait()
    override.close()
    release.set()
    with pytest.raises(WireFormatError):
        await task
    override.mark_submitted()
    override.outcome("accepted")
    assert phases == []


@pytest.mark.parametrize("sibling,expected", [("ogiZ0b", 2), ("foreign", 1)])
def test_reply_frame_count_includes_null_masked_siblings_only_exact_rpc(sibling, expected):
    from gflow_cli.api.transports.batchexecute import rpc_reply_frame_count
    from tests.api.test_native_generation_refusal import refusal

    masked = json.dumps([["wrb.fr", sibling, None, None, None, [5], "generic"]])
    assert rpc_reply_frame_count(refusal("ogiZ0b") + "\n" + masked, "ogiZ0b") == expected
