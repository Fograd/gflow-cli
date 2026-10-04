"""Local CAPTCHA observations filter without inventing provider acceptance."""

import pytest

from gflow_cli.selfhost.captcha import CaptchaStats
from gflow_cli.selfhost.captcha_events import query_events


def test_events_filter_provider_limit_and_unknown_acceptance(tmp_path):
    stats = CaptchaStats(tmp_path)
    stats.record("CapSolver", "solved")
    stats.record("CapSolver", "submitted")
    stats.record("CapSolver", "rejected")
    stats.record("supplied", "accepted")
    result = query_events(tmp_path, limit=10, provider="CapSolver")
    assert result["total"] == 3
    assert [row["phase"] for row in result["data"]] == ["solved", "submitted", "rejected"]
    assert result["summary"]["accepted"] == 0
    assert result["summary"]["rejected"] == 1
    assert result["summary"]["acceptanceRate"] == 0
    assert query_events(tmp_path, limit=1)["data"][0]["provider"] == "UserProvided"
    assert result["scope"] == "this-self-hosted-instance-event-observations"


def test_date_filter_and_limit_precedence(tmp_path):
    import sqlite3

    stats = CaptchaStats(tmp_path)
    stats.record("CapSolver", "unknown")
    with sqlite3.connect(stats.path) as conn:
        conn.execute("UPDATE events SET timestamp='2026-10-01T10:00:00.000Z'")
    assert query_events(tmp_path, date="2026-10-01")["total"] == 1
    assert query_events(tmp_path, date="2026-10-02")["total"] == 0
    assert query_events(tmp_path, date="2026-10-02", limit=1)["total"] == 1
    result = query_events(tmp_path, date="2026-10-01")
    assert result["summary"]["acceptanceRate"] is None
    assert result["summary"]["unknown"] == 1


@pytest.mark.parametrize(
    "kwargs",
    [{"date": "2026-99-03"}, {"limit": True}, {"limit": 0}, {"limit": 50001}, {"provider": "bad"}],
)
def test_invalid_filters_refuse(tmp_path, kwargs):
    with pytest.raises(ValueError):
        query_events(tmp_path, **kwargs)


def test_http_filters_and_global_unsupported_scope(tmp_path):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import create_app
    from tests.selfhost.test_server import AUTH, settings

    stats = CaptchaStats(tmp_path)
    stats.record("CapSolver", "solved")
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        response = client.get(
            "/v1/google-flow/accounts/captcha-stats?limit=1&provider=CapSolver", headers=AUTH
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["summary"]["acceptanceRate"] is None
        for query in ("date=bad", "limit=50001", "provider=bad", "unknown=x", "anonymized=bad"):
            assert (
                client.get(
                    "/v1/google-flow/accounts/captcha-stats?" + query, headers=AUTH
                ).status_code
                == 400
            )
        assert (
            client.get(
                "/v1/google-flow/accounts/captcha-stats?anonymized=true", headers=AUTH
            ).status_code
            == 501
        )
