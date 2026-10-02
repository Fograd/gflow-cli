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
