import asyncio

from click.testing import CliRunner
from PIL import Image

from gflow_cli import cli_image
from gflow_cli.api.image import Aspect


def test_i2i_auto_resolves_before_generation_and_retains_metadata(tmp_path, monkeypatch):
    first = tmp_path / "first.png"
    Image.new("RGB", (160, 90)).save(first)
    captured = {}

    async def run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli_image, "_run_i2i", run)
    monkeypatch.setattr(cli_image, "_resolve_profile", lambda value: "test")
    monkeypatch.setattr(cli_image, "_make_provider_dir", lambda value: tmp_path)
    monkeypatch.setattr(cli_image, "run_with_handlers", lambda func, **kwargs: asyncio.run(func()))
    result = CliRunner().invoke(
        cli_image.image, ["i2i", "a mug", "--ref", str(first), "--aspect", "auto"]
    )
    assert result.exit_code == 0, result.output
    assert captured["params"].aspect is Aspect.LANDSCAPE
    assert captured["params"].aspect_decision.requested_aspect == "auto"


def test_text_only_auto_explicit_refusal_before_profile(monkeypatch):
    monkeypatch.setattr(
        cli_image, "_resolve_profile", lambda value: (_ for _ in ()).throw(AssertionError())
    )
    result = CliRunner().invoke(cli_image.image, ["t2i", "a mug", "--aspect", "auto"])
    assert result.exit_code == 2
    assert "reference image" in result.output


def test_uuid_first_auto_refuses_even_with_later_local_image(tmp_path, monkeypatch):
    first = tmp_path / "second.png"
    Image.new("RGB", (10, 10)).save(first)
    monkeypatch.setattr(
        cli_image, "_resolve_profile", lambda value: (_ for _ in ()).throw(AssertionError())
    )
    result = CliRunner().invoke(
        cli_image.image,
        [
            "i2i",
            "a mug",
            "--ref",
            "00000000-0000-4000-8000-000000000001",
            "--ref",
            str(first),
            "--aspect",
            "auto",
        ],
    )
    assert result.exit_code == 2
    assert "first reference" in result.output
