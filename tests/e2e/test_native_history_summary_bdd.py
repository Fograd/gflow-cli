"""Zero-generation real-account proof of the REST native inventory defaults."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.native_observations import NativeObservationStore
from gflow_cli.selfhost.server import create_app

scenarios("../features/native_history_summary.feature")


def require(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


@given(
    "an opted-in owned image and a REST server without generation workers", target_fixture="case"
)
def configured(tmp_path, monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_HISTORY_SUMMARY") != "1":
        pytest.skip("Explicit authenticated inventory read opt-in required")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    project = os.getenv("GFLOW_CLI_E2E_HISTORY_SUMMARY_PROJECT", "")
    image = os.getenv("GFLOW_CLI_E2E_HISTORY_SUMMARY_IMAGE", "")
    profile = os.getenv("GFLOW_CLI_E2E_HISTORY_SUMMARY_PROFILE", "")
    require(bool(home and project and image and profile), "Owned native image fixture required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    environment = Settings.environment()
    require(profile in environment.accounts, "Explicit account must be configured")
    account = environment.accounts[profile]["email"]
    cfg = replace(
        environment,
        root=tmp_path,
        token=uuid4().hex,
        accounts={profile: {"email": account, "project": project}},
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield {
            "client": client,
            "headers": {"Authorization": "Bearer " + cfg.token},
            "account": account,
            "profile": profile,
            "project": project,
            "image": image,
            "root": tmp_path,
        }


@when("the default project summary and media inventory are read")
def read(case):
    client = case["client"]
    for name, route in (("summary", "projects"), ("media", "media")):
        response = client.get(
            "/v1/google-flow/assets/" + route + "/" + case["account"], headers=case["headers"]
        )
        require(
            response.status_code == 200,
            f"Fresh native {route} inventory read failed (HTTP {response.status_code})",
        )
        case[name] = response.json()


@then("generated counts and native media are returned with private observations")
def verify(case):
    summary = case["summary"]
    require(
        summary["email"] == case["account"]
        and type(summary["scanned"]) is int
        and 0 < summary["scanned"] <= 1000
        and type(summary["truncated"]) is bool
        and summary["complete"] is None,
        "Native summary traversal bounds or completeness changed",
    )
    projects = summary["projects"]
    require(
        len({row["projectId"] for row in projects}) == len(projects)
        and sum(row["total"] for row in projects) <= summary["scanned"],
        "Generated project summary identities or counts are inconsistent",
    )
    for row in projects:
        require(str(UUID(row["projectId"])) == row["projectId"], "Project ID is not canonical")
        require(
            set(row["byType"]) == {"IMAGE", "VIDEO"}
            and sum(row["byType"].values()) == row["total"]
            and row["total"] > 0,
            "Generated summary must count only images and videos",
        )
        if "oldest" in row and "newest" in row:
            require(
                datetime.fromisoformat(row["oldest"].replace("Z", "+00:00"))
                <= datetime.fromisoformat(row["newest"].replace("Z", "+00:00")),
                "Native date range is reversed",
            )
    owned = [row for row in projects if row["projectId"] == case["project"]]
    require(
        len(owned) == 1 and owned[0]["isCurrent"] is True and owned[0]["byType"]["IMAGE"] > 0,
        "Existing generated image project was not summarized",
    )
    require(
        "https://" not in json.dumps(summary) and "prompt" not in json.dumps(summary),
        "Summary must omit native content URLs and prompts",
    )
    if summary["truncated"]:
        require(bool(summary.get("cursor")), "Partial history requires a resumable cursor")
    else:
        require("cursor" not in summary, "Exhausted history must not advertise continuation")
    media = case["media"]
    require(
        media["projectId"] == case["project"]
        and media["scope"] == "google-project-library"
        and media["complete"] is None
        and media["observedCount"] >= media["count"] > 0,
        "Default media inventory must read the native project",
    )
    require(
        any(row["mediaGenerationId"] == case["image"] for row in media["media"]),
        "Existing generated image is absent from fresh native project media",
    )
    observations = NativeObservationStore(case["root"])
    counts = observations.counts(case["profile"], case["account"])
    require(
        counts["media"] > 0 and counts["workflows"] > 0 and counts["complete"] is None,
        "Scoped native history observations were not persisted",
    )
    require(
        stat.S_IMODE(observations.path.stat().st_mode) == 0o600,
        "Observed native metadata storage must be private",
    )
    require(
        case["client"].app.state.store.claim(case["profile"]) is None,
        "Read-only inventory calls must not create generation jobs",
    )
