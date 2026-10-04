"""Terminal quota is preserved through default queued worker paths without secrets."""

import json

import pytest

from gflow_cli import json_output
from gflow_cli.errors import NativeQuotaError
from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_server import settings

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["images", "videos"])
@pytest.mark.parametrize(
    "reason",
    [
        "PUBLIC_ERROR_USER_REQUESTS_THROTTLED",
        "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC",
    ],
)
async def test_default_worker_quota_safe_projection(tmp_path, monkeypatch, kind, reason):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    store.submit(
        kind,
        "pro1",
        {
            "project": P,
            "prompt": "fixture",
            "aspectRatio": "16:9",
            "count": 1,
            "model": "nano-banana-2" if kind == "images" else "veo-3.1-lite",
        },
        None,
    )
    job = store.claim("pro1")
    envelope = json_output.error_payload(NativeQuotaError(reason, route="batchexecute:example"))
    envelope["error"]["detail"] = "private-captcha-token /private/profile"
    called = []

    async def subprocess(args, timeout, **kwargs):
        called.append(args)
        return 4, json.dumps(envelope).encode()

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    result = await runtime.execute(cfg, store, job)
    assert len(called) == 1
    assert result["error"]["nativeReason"] == reason
    assert result["error"]["retryable"] is False
    assert "nativeModelKey" not in result["error"]
    assert "private" not in repr(result)
    store.finish(job["id"], "failed", result)
    with store.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0]
    assert count == (reason == "PUBLIC_ERROR_USER_REQUESTS_THROTTLED")
