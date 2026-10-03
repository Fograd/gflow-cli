from copy import deepcopy

import pytest

from gflow_cli.selfhost.unknown_native_media import unknown_native_media_result

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
N = "33333333-3333-4333-8333-333333333333"


def envelope():
    return {
        "error": {
            "class": "NativeMediaMutationUnknownError",
            "type": "https://gflow-cli.dev/errors/native-media-mutation-unknown",
            "exit_code": 40,
            "project_id": P,
            "operation": "archive",
            "phase": "response",
            "outcome_unknown": True,
            "known_media_ids": [M],
            "pending_media_ids": [N],
            "detail": "/private/cookies TOKEN",
        }
    }


def test_known_partial_archive_is_safe_and_preserves_prior_ack():
    result = unknown_native_media_result(envelope(), 40, P, "archive", {"deleted": [N]})
    assert result["knownMediaGenerationIds"] == [N, M]
    assert result["pendingMediaGenerationIds"] == []
    assert result["outcomeUnknown"] is True and result["error"]["retryable"] is False
    assert "private" not in repr(result) and "TOKEN" not in repr(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("class", "OtherError"),
        ("type", "https://wrong"),
        ("project_id", N),
        ("phase", "bad"),
        ("operation", "upload"),
        ("outcome_unknown", 1),
        ("exit_code", True),
        ("known_media_ids", [M] * 101),
        ("known_media_ids", ["/private/path"]),
        ("pending_media_ids", [M]),
    ],
)
def test_forged_or_invalid_unknown_metadata_refused(field, value):
    raw = deepcopy(envelope())
    raw["error"][field] = value
    assert unknown_native_media_result(raw, 40, P, "archive") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "archive"])
async def test_runtime_typed_unknown_preserves_handles_without_success_asset(
    tmp_path, monkeypatch, operation
):
    import json
    from unittest.mock import AsyncMock

    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.runtime import execute
    from gflow_cli.selfhost.store import Store

    cfg = Settings(
        token="fixture", root=tmp_path, accounts={"fixture": {"email": "alias", "project": P}}
    )
    store = Store(tmp_path)
    path = tmp_path / "input.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    raw = envelope()
    raw["error"]["operation"] = operation
    payload = (
        {"project": P, "input": str(path), "mime": "video/mp4", "rightsConfirmed": True}
        if operation == "upload"
        else {"project": P, "mediaGenerationIds": [M, N]}
    )
    submitted = store.submit(
        "assets" if operation == "upload" else "assets/archive", "fixture", payload, None
    )
    job = store.claim("fixture")
    run = AsyncMock(return_value=(40, json.dumps(raw).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    assert result["knownMediaGenerationIds"] == [M]
    assert result["pendingMediaGenerationIds"] == [N]
    assert "mediaGenerationId" not in result
    store.finish(submitted["jobId"], "failed", result)
    public = store.get_record(submitted["jobId"])
    assert public["outcomeUnknown"] is True
    assert public["response"]["knownMediaGenerationIds"] == [M]
    assert public["response"]["pendingMediaGenerationIds"] == [N]
    assert public["errorDetails"]["operation"] == operation
    assert "private" not in repr(public) and "TOKEN" not in repr(public)
    with pytest.raises(KeyError):
        store.asset_get(M)
    run.assert_awaited_once()
