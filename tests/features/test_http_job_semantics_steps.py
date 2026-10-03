"""BDD binding for HTTP-local contracts; no browser or upstream generation."""

import json

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenarios, then, when

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

scenarios("http_job_semantics.feature")

AUTH = {"Authorization": "Bearer fixture-token"}


@pytest.fixture
def case(tmp_path):
    cfg = Settings(
        token="fixture-token",
        root=tmp_path,
        sync_wait=0,
        allow_video=True,
        callbacks=("callbacks.example",),
        accounts={
            "fixture": {"email": "fixture", "project": "11111111-1111-4111-8111-111111111111"}
        },
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield {"client": client, "store": client.app.state.store}


@given("an authenticated local adapter with generation workers disabled")
def adapter(case):
    assert case["store"].jobs() == []


@when("a caller submits an asynchronous video request")
def asynchronous(case):
    case["response"] = case["client"].post(
        "/v1/google-flow/videos", headers=AUTH, json={"prompt": "fixture", "async": True}
    )


@then("the adapter returns 201 and a matching polling record")
def polling(case):
    response = case["response"]
    assert response.status_code == 201
    record = response.json()
    assert record["jobid"] == record["jobId"] and record["status"] == "created"
    assert case["client"].get(response.headers["location"], headers=AUTH).json() == record


@when("a synchronous request expires and its caller switches to async with the same key")
def expire(case):
    headers = {**AUTH, "Idempotency-Key": "one-generation"}
    case["timeout"] = case["client"].post(
        "/v1/google-flow/videos", headers=headers, json={"prompt": "fixture"}
    )
    case["response"] = case["client"].post(
        "/v1/google-flow/videos", headers=headers, json={"prompt": "fixture", "async": True}
    )


@then("the adapter reports 408 followed by 201 for exactly one durable job")
def one_job(case):
    assert case["timeout"].status_code == 408 and case["response"].status_code == 201
    assert case["timeout"].json()["processingContinues"] is True
    assert case["timeout"].json()["jobId"] == case["response"].json()["jobId"]
    assert len(case["store"].jobs()) == 1


@when("a queued job is marked interrupted after a worker stop")
def interrupted(case):
    store = case["store"]
    case["identifier"] = store.submit(
        "images",
        "fixture",
        {"replyUrl": "https://callbacks.example/hook", "replyRef": "caller"},
        None,
    )["jobId"]
    store.claim("fixture")
    store.finish(
        case["identifier"],
        "interrupted",
        {"error": {"code": "submission_outcome_unknown", "retryable": False}},
    )


@then("polling and the terminal callback have the same nonretryable unknown outcome")
def outcome(case):
    identifier = case["identifier"]
    record = case["client"].get(f"/v1/google-flow/jobs/{identifier}", headers=AUTH).json()
    assert record["status"] == "failed" and record["outcomeUnknown"] is True
    assert record["retryable"] is False and case["store"].claim("fixture") is None
    with case["store"].connection() as connection:
        callback = json.loads(
            connection.execute(
                "SELECT payload FROM callbacks WHERE job=? AND state='interrupted'", (identifier,)
            ).fetchone()[0]
        )
    assert callback == record
