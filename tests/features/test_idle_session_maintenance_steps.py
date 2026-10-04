"""Scheduling is a local queue behavior; no browser or Google is involved."""

from pytest_bdd import given, scenarios, then, when

from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
scenarios("idle_session_maintenance.feature")


@given("an enabled due profile and an idle durable queue", target_fixture="case")
def case(tmp_path, monkeypatch):
    clock = [1_800_000_000.0]
    monkeypatch.setattr("gflow_cli.selfhost.store.time.time", lambda: clock[0])
    store = Store(tmp_path)
    store.account_seed({"fixture": {"email": "account", "project": P}})
    clock[0] += 1800
    return {"store": store, "root": tmp_path}


@when("maintenance admission is checked twice across a restart")
def admission(case):
    assert case["store"].enqueue_idle_health("fixture", 1800) is True
    assert Store(case["root"]).enqueue_idle_health("fixture", 1800) is False


@when("the maintenance interval is disabled")
def disabled(case):
    assert case["store"].enqueue_idle_health("fixture", 0) is False


@when("generation already occupies the profile queue")
def busy(case):
    case["store"].submit("images", "fixture", {"project": P}, None)
    assert case["store"].enqueue_idle_health("fixture", 1800) is False


@then("only one native project-access health job is accepted")
def single(case):
    job = case["store"].claim("fixture")
    assert job["kind"] == "accounts/health"
    assert len(case["store"].jobs()) == 1


@then("no maintenance job is accepted")
def none(case):
    with case["store"].connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='accounts/health'").fetchone()[0]
            == 0
        )
