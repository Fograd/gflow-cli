import pytest

from gflow_cli.mcp import tools
from gflow_cli.worker.codec import build_image_request


@pytest.mark.parametrize("wait", [True, False])
async def test_mcp_seed_survives_direct_and_queued_codec(wait, monkeypatch):
    seen = []

    async def run(**kwargs):
        seen.append(kwargs)
        return {"status": "completed" if wait else "created"}

    async def acquire():
        return True

    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", acquire)
    result = await tools.gflow_generate_image(
        prompt="fixture", count=2, seed=42, profile="fixture", wait=wait
    )
    assert result["params"]["seed"] == 42
    assert seen[0]["wait"] is wait
    assert build_image_request(seen[0]["payload"]).seed == 42


async def test_bad_mcp_seed_never_queues(monkeypatch):
    async def run(**kwargs):
        pytest.fail("Invalid seed queued")

    monkeypatch.setattr(tools, "_run_generation_task", run)
    result = await tools.gflow_generate_image(prompt="fixture", seed=True)
    assert "error" in result


@pytest.mark.parametrize(
    "choice", [{"model": ""}, {"model": "unknown"}, {"aspect": ""}, {"count": True}, {"count": 1.5}]
)
async def test_invalid_image_controls_precede_profile_or_queue_work(monkeypatch, choice):
    async def acquire():
        pytest.fail("Invalid controls reached rate/profile/queue work")

    monkeypatch.setattr(tools._rate_limiter, "acquire", acquire)
    result = await tools.gflow_generate_image(prompt="fixture", **choice)
    assert "error" in result


@pytest.mark.parametrize("wait", [True, False])
async def test_ten_ordered_lite_references_and_controls_reach_queue_codec(wait, monkeypatch):
    from unittest.mock import AsyncMock
    from uuid import UUID

    from gflow_cli.api.image import Aspect, Model

    refs = [str(UUID(int=index + 1)) for index in range(10)]
    run = AsyncMock(return_value={"status": "created"})
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_generate_image(
        prompt="Use @reference_10 then @reference_1 then @reference_10.",
        model="nano2-lite",
        aspect="3:4",
        count=2,
        seed=42,
        reference_images=refs,
        reference_syntax="slots",
        wait=wait,
    )
    assert result["status"] == "created"
    assert run.await_args.kwargs["wait"] is wait
    req = build_image_request(run.await_args.kwargs["payload"])
    assert tuple(ref.name for ref in req.refs) == tuple(refs)
    assert req.reference_prompt_plan.image_ids == tuple(refs)
    assert req.model is Model.HARBOR_SEAL and req.aspect is Aspect.PORTRAIT_THREE_FOUR
    assert (req.count, req.seed) == (2, 42)
