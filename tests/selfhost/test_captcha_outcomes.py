import pytest

from gflow_cli.errors import MediaDownloadError, TransportTimeoutError, WafRejectionError
from gflow_cli.selfhost.image_worker import failure_phase


def test_google_known_refusal_is_rejected_during_generation():
    assert failure_phase(WafRejectionError(detail="redacted"), generating=True) == "rejected"


def test_timeout_or_download_failure_is_unknown():
    assert failure_phase(TransportTimeoutError(detail="redacted"), generating=True) == "unknown"
    assert failure_phase(MediaDownloadError(detail="redacted"), generating=False) == "unknown"


def test_waf_after_generation_is_not_claimed_google_submit_rejection():
    assert failure_phase(WafRejectionError(detail="redacted"), generating=False) == "unknown"


async def run_failure(monkeypatch, tmp_path, error, *, download=False):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import gflow_cli.selfhost.image_worker as worker
    from gflow_cli.selfhost.captcha import CaptchaStats

    path = tmp_path / "jobs" / "one" / "request.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "prompt": "sphere",
                "model": "nano2",
                "aspectRatio": "1:1",
                "count": 1,
                "captchaOrder": "CapSolver",
            }
        )
    )
    monkeypatch.setattr(worker.ProviderKeys, "get", lambda *_: "private-test-key")
    monkeypatch.setattr(
        worker.Solver, "solve", AsyncMock(return_value=SimpleNamespace(token="private-test-token"))
    )
    monkeypatch.setattr(worker, "_make_provider_dir", lambda _: tmp_path)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(headless=False))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_images_batch(self, **kwargs):
            override = worker.active_overrides.get()
            override.metadata = {"sitekey": "public-key", "action": "IMAGE_GENERATION"}
            await override.token(SimpleNamespace(url="https://flow.google.com/project/test"))
            override.used = True
            if not download:
                raise error
            return [SimpleNamespace(media_name="test", seed=42)]

        async def download_image(self, *args):
            raise error

    monkeypatch.setattr(worker, "FlowApiClient", Client)
    import pytest

    with pytest.raises(type(error)):
        await worker.generate("pro1", "test", path)
    return CaptchaStats(tmp_path).public()["providers"]["CapSolver"]


@pytest.mark.asyncio
async def test_worker_records_known_refusal_without_second_solve(monkeypatch, tmp_path):
    counts = await run_failure(monkeypatch, tmp_path, WafRejectionError(detail="redacted"))
    assert counts == {"solveStarted": 1, "solved": 1, "submitted": 1, "rejected": 1}


@pytest.mark.asyncio
async def test_worker_download_failure_is_unknown_not_rejected(monkeypatch, tmp_path):
    counts = await run_failure(
        monkeypatch, tmp_path, MediaDownloadError(detail="redacted"), download=True
    )
    assert counts == {"solveStarted": 1, "solved": 1, "submitted": 1, "unknown": 1}
