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
    assert "requires --project" in result.output


def test_uuid_auto_deferred_with_explicit_project(tmp_path, monkeypatch):
    captured = {}

    async def run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli_image, "_run_i2i", run)
    monkeypatch.setattr(cli_image, "_resolve_profile", lambda value: "test")
    monkeypatch.setattr(cli_image, "_make_provider_dir", lambda value: tmp_path)
    monkeypatch.setattr(cli_image, "run_with_handlers", lambda func, **kwargs: asyncio.run(func()))
    result = CliRunner().invoke(
        cli_image.image,
        [
            "i2i",
            "a mug",
            "--ref",
            "22222222-2222-4222-8222-222222222222",
            "--project",
            "11111111-1111-4111-8111-111111111111",
            "--aspect",
            "auto",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["params"].native_auto is True
    assert captured["params"].aspect_decision is None


def test_native_auto_resolution_error_prevents_cli_generation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from gflow_cli.api.image import ImageRef, Model
    from gflow_cli.errors import ConfigurationError

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.resolve_native_image_aspect = AsyncMock(
        side_effect=ConfigurationError(detail="No dimensions")
    )
    generate = AsyncMock()
    monkeypatch.setattr(cli_image, "FlowApiClient", lambda **kwargs: client)
    monkeypatch.setattr(cli_image, "_generate_verify_download", generate)
    monkeypatch.setattr(cli_image.OperationRecorder, "open", lambda settings: MagicMock())
    monkeypatch.setattr(cli_image, "record_failed_operation_safe", lambda *args, **kwargs: None)
    project = "11111111-1111-4111-8111-111111111111"
    media = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setattr(
        cli_image,
        "_resolve_project",
        AsyncMock(return_value=(SimpleNamespace(project_id=project), False)),
    )
    params = cli_image._I2IParams(
        prompt="a mug",
        classified_refs=[ImageRef(media)],
        aspect=Aspect.LANDSCAPE,
        model=Model.from_cli("nano2"),
        reference_entities=(),
        reference_entity_names=(),
        native_auto=True,
    )
    with pytest.raises(ConfigurationError):
        asyncio.run(
            cli_image._run_i2i(
                profile_name="fixture",
                profile_dir=tmp_path,
                headless=True,
                params=params,
                count=1,
                out=None,
                output_root=tmp_path,
                project_id=project,
            )
        )
    client.resolve_native_image_aspect.assert_awaited_once_with(project, media)
    generate.assert_not_awaited()
