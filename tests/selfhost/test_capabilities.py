from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import Settings, create_app


def test_capabilities_separates_local_implementation_from_live_native_proof(tmp_path):
    cfg = Settings(token="test", root=tmp_path, accounts={}, callbacks=())
    with TestClient(create_app(cfg, start_workers=False)) as client:
        path = "/v1/google-flow/capabilities"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    body = response.json()
    assert {
        "accounts/cookie-import",
        "accounts/project-access-health",
        "images/canonical-references",
        "images/canonical-characters",
        "images/aspectRatio-auto-local-policy",
    } <= set(body["implemented"])
    assert "accounts/cookie-import" not in body["notImplemented"]
    assert "aspectRatio/auto" not in body["notImplemented"]
    assert "images/aspectRatio-auto-native" in body["notImplemented"]
    assert body["localPolicies"]["images/aspectRatio-auto"] == {
        "policy": "derived-first-reference-nearest-supported-v1",
        "nativeGoogleAuto": False,
        "requires": "first-owned-image-reference",
    }
    assert {
        "accounts/cookie-import-live-acceptance",
        "captcha-provider-google-acceptance",
        "videos/generic-multi-output-rendering",
        "images/ten-reference-rendering",
        "images/4k-entitlement-and-rendering",
    } <= set(body["verificationPending"])
