"""Generic one-RPC batch admission with existing private CAPTCHA lifecycle."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost import captcha_routes
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings


@pytest.mark.parametrize("count", [2, 4])
@pytest.mark.parametrize("control", ["captchaOrder", "captchaRetry", "captchaToken"])
def test_batch_captcha_controls_admit_one_job_and_keep_token_private(
    tmp_path, monkeypatch, count, control
):
    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    value = {
        "captchaOrder": "CapSolver",
        "captchaRetry": 2,
        "captchaToken": "synthetic-private-batch-token-abcdefghijklmnop",
    }[control]
    with TestClient(
        create_app(replace(settings(tmp_path), allow_video=True), start_workers=False)
    ) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "prompt": "A blue cup",
                "count": count,
                "model": "veo-3.1-lite",
                "async": True,
                control: value,
            },
        )
        assert response.status_code == 201, response.text
        assert len(client.app.state.store.jobs()) == 1
        with client.app.state.store.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM jobs WHERE id=?", (response.json()["jobId"],)
            ).fetchone()
        payload = json.loads(row["payload"])
        assert payload["count"] == count
        if control == "captchaToken":
            assert value not in row["payload"] and value not in response.text
            paths = list((tmp_path / "captcha-input").glob("*.token"))
            assert len(paths) == 1 and paths[0].read_text() == value
            assert paths[0].stat().st_mode & 0o077 == 0
        else:
            assert payload[control] == value
