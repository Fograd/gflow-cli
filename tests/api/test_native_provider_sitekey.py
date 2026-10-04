"""Run only pure discovery JavaScript against fake script tags; no browser."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from gflow_cli.api.recaptcha import _DISCOVER_SITE_KEY_JS


@pytest.mark.parametrize(
    "script,expected",
    [
        ("https://www.google.com/recaptcha/enterprise.js?render=approved", "approved"),
        ("https://www.recaptcha.net/recaptcha/enterprise.js?render=approved", "approved"),
        ("https://example.test/recaptcha/enterprise.js?render=foreign", None),
        ("http://www.google.com/recaptcha/enterprise.js?render=foreign", None),
        ("https://www.google.com/recaptcha/enterprise.js?render=explicit", None),
        ("https://www.google.com/recaptcha/enterprise.js?render=first&render=second", None),
    ],
)
def test_only_trusted_fresh_script_keys(script, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for pure JavaScript discovery proof")
    code = (
        "globalThis.location={href:'https://flow.google.com/project/test'};"
        "globalThis.document={querySelectorAll:()=>[{getAttribute:()=>"
        + json.dumps(script)
        + "}]};"
        "const value=(" + _DISCOVER_SITE_KEY_JS + ")();process.stdout.write(JSON.stringify(value));"
    )
    result = subprocess.run(
        [node, "-e", code], capture_output=True, text=True, check=True, timeout=5
    )
    assert json.loads(result.stdout) == expected
