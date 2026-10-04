"""REST CAPTCHA integration refuses invalid tokens before persistence or queueing."""

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

TOKEN = "synthetic-native-captcha-private-token"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize(
    "route,payload",
    [
        ("images", {"prompt": "fixture"}),
        ("videos", {"prompt": "fixture", "count": 1}),
        ("images/upscale", {"mediaGenerationId": M, "resolution": "2k"}),
    ],
)
@pytest.mark.parametrize("whitespace", [" ", "\t", "\n", "\u00a0"])
def test_whitespace_token_refuses_before_private_file_or_queue(
    tmp_path, route, payload, whitespace
):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/" + route,
            headers=AUTH,
            json={**payload, "captchaToken": TOKEN + whitespace + "suffix", "async": True},
        )
        assert response.status_code == 422, response.text
        assert TOKEN not in response.text
        assert client.app.state.store.jobs() == []
        assert not list((cfg.root / "captcha-input").glob("*.token"))
