import pytest

from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, reload_metadata

KEY = "k" * 40
KEY_BYTES = KEY.encode()
URL = "https://www.google.com/recaptcha/enterprise/reload?k=" + KEY


def protobuf_field(number, value):
    assert len(value) < 128
    return bytes([number << 3 | 2, len(value)]) + value


def envelope(action=b"IMAGE_GENERATION", key=KEY_BYTES):
    return protobuf_field(8, action) + protobuf_field(14, key)


def test_observed_protobuf_metadata_is_public_only():
    raw = protobuf_field(2, b"private-token") + envelope()
    assert reload_metadata(URL, raw) == {"sitekey": KEY, "action": "IMAGE_GENERATION"}
    assert (
        reload_metadata("https://untrusted.example/recaptcha/enterprise/reload?k=" + KEY, raw)
        is None
    )


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"x" * 65537,
        envelope()[:-1],
        envelope() + protobuf_field(8, b"IMAGE_GENERATION"),
        envelope(action=b"VIDEO_GENERATION"),
        envelope(key=b"wrong"),
        b"\x00",
        b"\x42\x80",
    ],
)
def test_metadata_schema_drift_refuses_solver_tasks(body):
    with pytest.raises(ValueError):
        reload_metadata(URL, body)


def test_metadata_listener_cleanup_and_supplied_bypass():
    from types import SimpleNamespace

    class Page:
        url = "https://flow.google.com/project/project"
        listener = None

        def on(self, name, callback):
            assert name == "request"
            self.listener = callback

        def remove_listener(self, name, callback):
            assert self.listener is callback
            self.listener = None

    async def token(page):
        return "t" * 30

    page = Page()
    override = ImageOverrides("project", 1, token=token)
    override.capture_metadata(page)
    page.listener(SimpleNamespace(url=URL, post_data_buffer=envelope()))
    assert override.metadata == {"sitekey": KEY, "action": "IMAGE_GENERATION"}
    override.stop_capture(page)
    assert page.listener is None
    supplied = ImageOverrides("project", 1, token=token, metadata_required=False)
    supplied.capture_metadata(page)
    assert page.listener is None


async def test_supplied_token_needs_no_browser_metadata():
    async def supplied(page):
        return "t" * 30

    override = ImageOverrides("project", 1, token=supplied, metadata_required=False)
    assert not override.metadata_required


def test_explicit_image_provider_controls_enqueue_without_acceptance_claim(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.server import create_app

    class Keys:
        def public(self):
            return {"CapSolver": {"configured": True}}

    monkeypatch.setattr("gflow_cli.selfhost.captcha_routes.provider_keys", lambda: Keys())
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "first", "project": "11111111-1111-4111-8111-111111111111"}},
    )
    cfg.sync_wait = 0
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for field, value in (
            ("captchaOrder", "CapSolver"),
            ("captchaRetry", 1),
            ("captchaRetry", 10),
        ):
            result = client.post(
                "/v1/google-flow/images",
                headers={"Authorization": "Bearer test"},
                json={"prompt": "fixture", field: value, "async": True},
            )
            assert result.status_code == 201, result.text
            assert "captchaProvider" not in result.text
        jobs = client.app.state.store.job_page(limit=100)["jobs"]
        assert len(jobs) == 3
        assert all(job["status"] == "created" for job in jobs)
