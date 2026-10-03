"""Unknown native image submission survives CLI, queue, and HTTP boundaries."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from gflow_cli.errors import ImageGenerationUnknownError
from gflow_cli.json_output import error_payload
from gflow_cli.selfhost.config import MODEL_ALIASES, Settings
from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.server import create_app

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
OLD = "44444444-4444-4444-8444-444444444444"


@pytest.mark.asyncio
async def test_unknown_cli_image_preserves_uncertainty_handles_through_public_http(
    tmp_path, monkeypatch
):
    cfg = Settings(
        token="fixture", root=tmp_path, accounts={"fixture": {"email": "alias", "project": P}}
    )
    envelope = error_payload(
        ImageGenerationUnknownError(
            project_id=P, media_ids=(M,), workflow_ids=(W,), phase="image_response"
        )
    )
    envelope["error"]["detail"] = "private-token-body"
    envelope["error"]["incident"] = {"path": "/private/credentials"}
    run = AsyncMock(return_value=(40, json.dumps(envelope).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        store = client.app.state.store
        submitted = store.submit(
            "images",
            "fixture",
            {
                "project": P,
                "prompt": "fixture",
                "model": next(iter(MODEL_ALIASES)),
                "aspectRatio": "1:1",
                "count": 1,
            },
            None,
        )
        job = store.claim("fixture")
        store.checkpoint(
            job["id"],
            {
                "knownMediaGenerationIds": [OLD],
                "media": [
                    {
                        "mediaGenerationId": OLD,
                        "downloadPath": f"/v1/google-flow/assets/{OLD}/download",
                    }
                ],
            },
        )
        result = await execute(cfg, store, job)
        store.finish(submitted["jobId"], "failed", result)
        response = client.get(
            "/v1/google-flow/jobs/" + submitted["jobId"],
            headers={"Authorization": "Bearer fixture"},
        )
        record = response.json()
        assert record["outcomeUnknown"] is True and record["retryable"] is False
        assert record["knownMediaGenerationIds"] == [OLD, M]
        assert record["knownWorkflowIds"] == [W]
        assert record["response"]["media"][0]["mediaGenerationId"] == OLD
        assert record["errorDetails"]["phase"] == "image_response"
        assert "private-token-body" not in response.text and "/private" not in response.text
        run.assert_awaited_once()
        with store.connection() as connection:
            raw = json.loads(connection.execute("SELECT result FROM jobs").fetchone()[0])
        assert raw["knownMediaGenerationIds"] == [OLD, M]
        assert "private-token-body" not in repr(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("class", "CharacterMutationUnknownError"),
        ("type", "https://other.invalid/errors"),
        ("outcome_unknown", 1),
        ("exit_code", 9),
        ("project_id", W),
        ("phase", "private-phase"),
    ],
)
def test_only_exact_matching_image_contract_is_promoted(field, value):
    from gflow_cli.selfhost.unknown_image import unknown_image_result

    envelope = error_payload(ImageGenerationUnknownError(project_id=P))
    envelope["error"][field] = value
    assert unknown_image_result(envelope, 40, P) is None


def test_unknown_image_drops_unsafe_handles_and_never_copies_diagnostics():
    from gflow_cli.selfhost.unknown_image import unknown_image_result

    envelope = error_payload(ImageGenerationUnknownError(project_id=P))
    envelope["error"]["media_ids"] = [M, "https://private.invalid/token"]
    envelope["error"]["workflow_ids"] = [W, "/private/account"]
    envelope["error"]["incident"] = {"path": "/private/account"}
    result = unknown_image_result(envelope, 40, P)
    assert result["knownMediaGenerationIds"] == [M] and result["knownWorkflowIds"] == [W]
    assert "private" not in repr(result)
