"""Native seed control supersedes the upstream UI-only seed removal."""

import asyncio

from click.testing import CliRunner

from gflow_cli.cli import main as cli


def test_cli_seed_flows_to_t2i_and_i2i_params(tmp_path, monkeypatch):
    seen = []

    async def run(**kwargs):
        seen.append(kwargs)

    monkeypatch.setattr("gflow_cli.cli_image._run_t2i", run)
    monkeypatch.setattr("gflow_cli.cli_image._run_i2i", run)
    monkeypatch.setattr("gflow_cli.cli_image._resolve_profile", lambda profile: "fixture")
    monkeypatch.setattr("gflow_cli.cli_image._make_provider_dir", lambda profile: tmp_path)
    monkeypatch.setattr(
        "gflow_cli.cli_image.run_with_handlers", lambda fn, **kwargs: asyncio.run(fn())
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["image", "t2i", "--seed", "42", "-n", "2", "fixture"])
    assert result.exit_code == 0, result.output
    assert seen[0]["req"].seed == 42 and seen[0]["req"].count == 2
    image = tmp_path / "ref.png"
    image.write_bytes(b"fixture")
    result = runner.invoke(cli, ["image", "i2i", "--seed", "43", "--ref", str(image), "fixture"])
    assert result.exit_code == 0, result.output
    assert seen[1]["params"].seed == 43


def test_seed_invalid_ranges_and_multi_prompt_rejected_before_generation():
    runner = CliRunner()
    for args in (
        ["--seed", "-1", "fixture"],
        ["--seed", "2147483647", "-n", "2", "fixture"],
        ["--seed", "42", "first", "second"],
    ):
        result = runner.invoke(cli, ["image", "t2i", *args])
        assert result.exit_code == 2 and "seed" in result.output
