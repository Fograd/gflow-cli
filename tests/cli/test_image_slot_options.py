from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_image
from gflow_cli.cli import main
from gflow_cli.mcp import tools


@pytest.mark.parametrize(
    "args",
    [
        ["image", "t2i", "@character_1", "--reference-syntax", "slots", "--json"],
        [
            "image",
            "i2i",
            "@reference_2",
            "--ref",
            "11111111-1111-4111-8111-111111111111",
            "--reference-syntax",
            "slots",
            "--json",
        ],
    ],
)
def test_missing_slot_cli_refuses_before_profile(monkeypatch, args):
    resolver = Mock(side_effect=AssertionError("profile must not be resolved"))
    monkeypatch.setattr(cli_image, "_resolve_profile", resolver)
    result = CliRunner().invoke(main, args)
    assert result.exit_code != 0
    assert "not provided" in result.output
    resolver.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_invalid_syntax_refuses_before_profile(monkeypatch):
    resolver = Mock(side_effect=AssertionError("profile must not be resolved"))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolver)
    result = await tools.gflow_generate_image(prompt="plain", reference_syntax="bad")
    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    resolver.assert_not_called()


def test_cli_preflight_accepts_interleaved_explicit_refs(tmp_path):
    from gflow_cli.api.image import GenerateImageRequest, ImageRef

    first = ImageRef("11111111-1111-4111-8111-111111111111")
    last = ImageRef("33333333-3333-4333-8333-333333333333")
    local = tmp_path / "local.png"
    request = GenerateImageRequest(
        prompt="Use @reference_3 with @reference_1 and @reference_2.",
        refs=(first, last),
        ref_paths=(local,),
        reference_syntax="slots",
    )
    cli_image._preflight_image_slots(request, [first, local, last])


@pytest.mark.asyncio
@pytest.mark.parametrize("wait", [False, True])
async def test_mcp_preserves_mixed_slot_order_in_both_task_modes(monkeypatch, tmp_path, wait):
    from pathlib import Path
    from unittest.mock import AsyncMock

    from gflow_cli.worker.codec import build_image_request

    first = "11111111-1111-4111-8111-111111111111"
    last = "33333333-3333-4333-8333-333333333333"
    local = tmp_path / "local.png"
    local.write_bytes(b"fixture; no browser or Auto decode")
    run = AsyncMock(return_value={"status": "completed"})
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "test-profile")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    monkeypatch.setattr(tools, "_run_generation_task", run)
    result = await tools.gflow_generate_image(
        prompt="Use @reference_3 with @reference_1 and @reference_2.",
        reference_images=[first, str(local), last],
        reference_syntax="slots",
        aspect="16:9",
        wait=wait,
    )
    assert result["status"] == "completed"
    assert run.await_args.kwargs["wait"] is wait
    payload = run.await_args.kwargs["payload"]
    decoded = build_image_request(payload)
    assert decoded.local_ref_ids == ("local-reference-2",)
    assert decoded.ref_paths == (Path(local).resolve(),)
    assert decoded.reference_prompt_plan.image_ids == (first, "local-reference-2", last)
