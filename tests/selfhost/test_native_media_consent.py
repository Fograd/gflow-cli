import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("header", [None, "false", "True", "1"])
def test_mp4_consent_required_before_enqueue(tmp_path, header):
    cfg = Settings(
        token="fixture",
        root=tmp_path,
        sync_wait=0,
        timeout=0,
        accounts={"fixture": {"email": "alias", "project": P}},
    )
    headers = {"Authorization": "Bearer fixture", "Content-Type": "video/mp4"}
    if header is not None:
        headers["X-Flow-Rights-Confirmed"] = header
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/assets/alias", headers=headers, content=b"\x00\x00\x00\x0cftypisom"
        )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []
