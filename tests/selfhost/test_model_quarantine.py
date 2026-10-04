from datetime import UTC, datetime

import pytest

from gflow_cli import json_output
from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.account_scheduler import select_account
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_account_scheduler import configuration

KEY = "veo_3_1_r2v_4s"
DAILY = "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED"
THROTTLE = "PUBLIC_ERROR_USER_REQUESTS_THROTTLED"


def refusal(reason, model=KEY, operation="videos/reference"):
    from gflow_cli.errors import NativeQuotaError

    err = NativeQuotaError(
        reason, route="batchexecute:MZZa6b", model_key=model, operation=operation
    )
    return {"error": runtime.native_refusal_error(json_output.error_payload(err), 4)}


def fail(store, profile, reason, model=KEY, operation="videos/reference"):
    job = store.submit(operation, profile, {}, None)
    store.finish(job["jobId"], "failed", refusal(reason, model, operation))
    return job["jobId"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    from gflow_cli.selfhost import model_quarantine

    now = [datetime(2026, 10, 4, 12, tzinfo=UTC).timestamp()]
    monkeypatch.setattr(model_quarantine.time, "time", lambda: now[0])
    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    return store, cfg, now


def test_typed_daily_exact_model_until_midnight(env):
    store, cfg, now = env
    fail(store, "one", DAILY)
    assert select_account(store, cfg.accounts, operation="videos/reference", model_key=KEY) == "two"
    # Force the quarantined account to win scores without changing its observation.
    with store.connection() as conn:
        conn.execute("UPDATE jobs SET updated=?", (now[0] - 901,))
    assert select_account(store, cfg.accounts, operation=None, model_key=KEY) == "one"
    assert (
        select_account(store, cfg.accounts, operation="videos/reference", model_key=None) == "one"
    )
    assert (
        select_account(store, cfg.accounts, operation="videos/reference", model_key="veo_other")
        == "one"
    )
    now[0] = datetime(2026, 10, 5, tzinfo=UTC).timestamp()
    assert select_account(store, cfg.accounts, operation="videos/reference", model_key=KEY) == "one"


def test_throttle_global_generation_only_and_expiry(env):
    store, cfg, now = env
    fail(store, "one", THROTTLE, model=None)
    now[0] += 901
    assert select_account(store, cfg.accounts, operation="images") == "two"
    assert select_account(store, cfg.accounts) == "one"
    now[0] += 900
    assert select_account(store, cfg.accounts, operation="images") == "one"


def test_single_account_bypasses_policy(env):
    store, cfg, now = env
    fail(store, "one", THROTTLE, model=None)
    store.account_delete("two")
    assert select_account(store, {"one": cfg.accounts["one"]}, operation="videos") == "one"


def test_all_quarantined_has_earliest_remaining_and_source(env):
    from gflow_cli.selfhost.model_quarantine import POLICY, NoEligibleAccount

    store, cfg, now = env
    fail(store, "one", THROTTLE, model=None)
    now[0] += 60
    fail(store, "two", THROTTLE, model=None)
    with pytest.raises(NoEligibleAccount) as e:
        select_account(store, cfg.accounts, operation="images")
    assert e.value.retry_after == 1740
    assert e.value.policy == POLICY
    assert {x["model"] for x in e.value.skip_reasons} == {"*"}


def test_idempotent_job_preserves_first_seen_and_deadline(env):
    store, cfg, now = env
    job = fail(store, "one", THROTTLE, model=None)
    with store.connection() as conn:
        first = dict(conn.execute("SELECT * FROM model_quarantines").fetchone())
    now[0] += 60
    store.finish(job, "failed", refusal(THROTTLE, model=None))
    with store.connection() as conn:
        same = dict(conn.execute("SELECT * FROM model_quarantines").fetchone())
    assert first == same
    fail(store, "one", THROTTLE, model=None)
    with store.connection() as conn:
        renewed = dict(conn.execute("SELECT * FROM model_quarantines").fetchone())
    assert renewed["first_seen"] == first["first_seen"]
    assert renewed["until"] == now[0] + 1800


def test_refresh_follows_policy_delete_reregister_does_not(env):
    store, cfg, now = env
    fail(store, "one", DAILY)
    old = store.account_lookup("public-one")
    store.account_activate_import("fresh", "public-one", old["project"], expected_old=old)
    configured = {"fresh": cfg.accounts["one"], "two": cfg.accounts["two"]}
    assert select_account(store, configured, operation="videos/reference", model_key=KEY) == "two"
    store.account_delete("fresh")
    with pytest.raises(ValueError, match="Historical"):
        store.account_set("fresh", "public-one", old["project"], True, True)
    # Also cover a future explicit cleanup of retired physical account rows.
    with store.connection() as conn:
        conn.execute("DELETE FROM accounts WHERE enabled=-1")
    now[0] += 1
    store.account_set("replacement", "public-one", old["project"], True, True)
    configured = {"replacement": cfg.accounts["one"], "two": cfg.accounts["two"]}
    now[0] += 901
    assert (
        select_account(store, configured, operation="videos/reference", model_key=KEY)
        == "replacement"
    )


@pytest.mark.parametrize(
    "error",
    [
        {"exit_code": 4, "nativeReason": DAILY, "nativeModelKey": KEY},
        {"exit_code": 10, "nativeReason": THROTTLE},
        {
            "code": "submission_outcome_unknown",
            "exit_code": 4,
            "nativeReason": THROTTLE,
            "nativeProof": "single-typed-native-rpc-v1",
            "nativeGrpcCode": 8,
        },
    ],
)
def test_unproven_or_unknown_never_quarantines(env, error):
    store, cfg, now = env
    job = store.submit("videos", "one", {}, None)
    store.finish(job["jobId"], "failed", {"error": error})
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


@pytest.mark.parametrize(
    "reason,seconds",
    [
        ("PUBLIC_ERROR_USER_QUOTA_REACHED", 1800),
        ("PUBLIC_ERROR_MODEL_ACCESS_DENIED", 3600),
        ("PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED_UPGRADEABLE", 43200),
    ],
)
def test_supported_remaining_policy_expiry(env, reason, seconds):
    store, cfg, now = env
    fail(store, "one", reason)
    with store.connection() as conn:
        row = conn.execute("SELECT * FROM model_quarantines").fetchone()
    assert row["until"] == now[0] + seconds
    now[0] += 901
    assert select_account(store, cfg.accounts, operation="videos/reference", model_key=KEY) == "two"
    now[0] = row["until"]
    assert select_account(store, cfg.accounts, operation="videos/reference", model_key=KEY) == "one"


@pytest.mark.parametrize("model,operation", [(None, "videos/reference"), (KEY, "videos/edit")])
def test_model_policy_requires_exact_proven_operation_and_key(env, model, operation):
    store, cfg, now = env
    job = store.submit("videos/reference", "one", {}, None)
    store.finish(job["jobId"], "failed", refusal(DAILY, model, operation))
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


def test_overlapping_quarantines_retry_when_a_complete_account_becomes_available(env):
    from gflow_cli.selfhost.model_quarantine import NoEligibleAccount

    store, cfg, now = env
    fail(store, "one", DAILY)
    fail(store, "one", THROTTLE, model=None)
    fail(store, "two", "PUBLIC_ERROR_MODEL_ACCESS_DENIED")
    with pytest.raises(NoEligibleAccount) as caught:
        select_account(store, cfg.accounts, operation="videos/reference", model_key=KEY)
    assert caught.value.retry_after == 3600


@pytest.mark.parametrize(
    "field,value",
    [
        ("nativeOperation", []),
        ("nativeModelKey", {}),
        ("nativeGrpcCode", True),
        ("exit_code", True),
        ("code", "google_flow_native_quota"),
        ("outcome_unknown", True),
    ],
)
def test_malformed_or_inconsistent_worker_metadata_fails_closed(env, field, value):
    store, cfg, now = env
    raw = refusal("PUBLIC_ERROR_MODEL_ACCESS_DENIED")["error"]
    raw[field] = value
    job = store.submit("videos/reference", "one", {}, None)
    store.finish(job["jobId"], "failed", {"error": raw})
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


def test_positive_traffic_refusal_never_quarantines_account_or_model(env):
    store, cfg, now = env
    fail(store, "one", "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC")
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


def test_late_duplicate_job_does_not_refresh_after_another_event(env):
    store, cfg, now = env
    first = fail(store, "one", THROTTLE, model=None)
    now[0] += 60
    fail(store, "one", THROTTLE, model=None)
    with store.connection() as conn:
        before = dict(conn.execute("SELECT * FROM model_quarantines").fetchone())
    now[0] += 60
    store.finish(first, "failed", refusal(THROTTLE, model=None))
    with store.connection() as conn:
        after = dict(conn.execute("SELECT * FROM model_quarantines").fetchone())
    assert after == before


def test_policy_and_job_terminal_change_roll_back_together(env, monkeypatch):
    store, cfg, now = env
    job = store.submit("videos/reference", "one", {}, None)
    monkeypatch.setattr(
        store, "_callback", lambda *args: (_ for _ in ()).throw(RuntimeError("fixture"))
    )
    with pytest.raises(RuntimeError):
        store.finish(job["jobId"], "failed", refusal(DAILY))
    assert store.get(job["jobId"])["status"] == "created"
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


def test_top_level_unknown_result_never_creates_policy(env):
    store, cfg, now = env
    job = store.submit("videos/reference", "one", {}, None)
    result = refusal(DAILY)
    result["outcomeUnknown"] = True
    store.finish(job["jobId"], "failed", result)
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0


def test_deleted_scope_cannot_record_late_old_job_into_reregistration(env):
    store, cfg, now = env
    job = store.submit("videos/reference", "one", {}, None)
    old = store.account_lookup("public-one")
    store.account_delete("one")
    now[0] += 1
    with pytest.raises(ValueError, match="Historical"):
        store.account_set("one", "public-one", old["project"], True, True)
    # Also cover a future explicit cleanup of retired physical account rows.
    with store.connection() as conn:
        conn.execute("DELETE FROM accounts WHERE enabled=-1")
    now[0] += 1
    store.account_set("unrelated", "public-one", old["project"], True, True)
    store.finish(job["jobId"], "failed", refusal(DAILY))
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_quarantines").fetchone()[0] == 0
