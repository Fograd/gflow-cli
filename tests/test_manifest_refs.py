"""Manifest references are refused, never silently dropped (#913).

Every ``ref`` / ``reference_entity`` form was parsed and then ignored: the row ran as a
plain text-to-image with exit 0 (measured live, docs/superpowers/spikes/
2026-10-01-batch-ref-dropped.md). Until a form is actually wired, it is refused at parse
time, before any browser work, naming the row and the field.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from gflow_cli.cli import main as cli_main
from gflow_cli.errors import ConfigurationError
from gflow_cli.image_batch import parse_batch_item_dict

_FORMS = [
    ("ref", "batch:0"),
    ("ref", "./photo.png"),
    ("ref", "11111111-1111-1111-1111-111111111111"),
    ("reference_entity", "11111111-1111-1111-1111-111111111111"),
    ("reference_entity", "batch:0"),
]


@pytest.mark.parametrize(("field", "value"), _FORMS)
def test_parse_refuses_every_reference_form(field: str, value: str) -> None:
    with pytest.raises(ConfigurationError) as info:
        parse_batch_item_dict({"text": "x", field: value}, 1)
    message = str(info.value)
    assert f"prompts[1].{field}" in message
    assert "#913" in message


@pytest.mark.parametrize("field", ["ref", "reference_entity"])
def test_parse_accepts_explicit_null(field: str) -> None:
    item = parse_batch_item_dict({"text": "x", field: None}, 0)
    assert item.ref is None
    assert item.reference_entity is None


def _rows(field: str, value: str) -> list[dict[str, str]]:
    return [{"text": "a red apple"}, {"text": "the same apple, green", field: value}]


@pytest.mark.parametrize(("field", "value"), _FORMS)
def test_run_config_refuses_before_any_browser(tmp_path: Path, field: str, value: str) -> None:
    cfg = tmp_path / "run.json"
    cfg.write_text(json.dumps({"prompts": _rows(field, value)}), encoding="utf-8")
    with patch("gflow_cli.cli_run.FlowApiClient") as client:
        result = CliRunner().invoke(cli_main, ["run", "--config", str(cfg)])
    assert result.exit_code == 11, result.output
    assert f"prompts[1].{field}" in result.output
    client.assert_not_called()


@pytest.mark.parametrize(("field", "value"), _FORMS)
def test_image_batch_refuses_before_any_browser(tmp_path: Path, field: str, value: str) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps(_rows(field, value)), encoding="utf-8")
    with patch("gflow_cli.cli_image.FlowApiClient") as client:
        result = CliRunner().invoke(cli_main, ["image", "batch", str(manifest)])
    # `image batch` reports manifest problems as a usage error (exit 2), as it does for
    # every other malformed manifest field (`_as_usage_error`, cli_image.py).
    assert result.exit_code == 2, result.output
    assert f"prompts[1].{field}" in result.output
    client.assert_not_called()
