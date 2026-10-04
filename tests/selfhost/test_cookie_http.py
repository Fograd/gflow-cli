"""Cookie account activation and refresh invariants, with no browser/network."""

import shutil
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from gflow_cli import auth
from gflow_cli.errors import AuthMissingError
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.profile_import import ImportedProfile
from gflow_cli.selfhost.server import create_app
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
EMAIL = "fixture@example.test"
AUTH = {"Authorization": "Bearer fixture-token"}
COOKIES = "SID\tprivate-cookie-fixture\t.google.com\t/\tSession"


@pytest.fixture
def imported(tmp_path, monkeypatch):
    home = tmp_path / "profiles"
    home.mkdir()
    monkeypatch.setattr(auth, "default_profile_root", lambda: home)
    monkeypatch.setattr(auth, "profile_dir", lambda name: home / ("profile_" + name))
    seen = []

    async def create(table, profile, *, expected_email=None, project_id=None):
        seen.append((profile, expected_email, project_id))
        path = auth.profile_dir(profile)
        path.mkdir(mode=0o700)
        (path / ".gflow_account").write_text(EMAIL)
        identity = (path.stat().st_dev, path.stat().st_ino)
        return ImportedProfile(
            profile=profile,
            email=EMAIL,
            project_id=project_id or P,
            cookie_count=table.count,
            _identity=identity,
        ).recaptured_private_state(path)

    async def cleanup(candidate):
        shutil.rmtree(auth.profile_dir(candidate.profile))
        return True

    monkeypatch.setattr("gflow_cli.selfhost.profile_import.import_cookie_profile", create)
    monkeypatch.setattr(
        "gflow_cli.selfhost.profile_import.discard_imported_profile", cleanup, raising=False
    )
    monkeypatch.setattr(
        "gflow_cli.selfhost.profile_import.reverify_imported_project",
        AsyncMock(return_value=None),
        raising=False,
    )
    return home, seen


def config(tmp_path, old=False):
    return Settings(
        token="fixture-token",
        root=tmp_path / "service",
        sync_wait=0,
        accounts={"original": {"email": "alias", "project": P}} if old else {},
    )


def original():
    path = auth.profile_dir("original")
    path.mkdir()
    (path / ".gflow_account").write_text(EMAIL)
    (path / "Cookies").write_text("original-private-cookie")
    return path


def test_cookie_only_new_account_is_verified_without_secret_echo(tmp_path, imported):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        response = client.post("/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES})
        assert response.status_code == 201
        row = response.json()
        assert row["email"] == EMAIL and row["projectId"] == P
        assert row["verificationSource"] == "native-cookie-verified" and row["health"] == "OK"
        assert "private-cookie-fixture" not in response.text and "sessionCookies" not in row
        assert "accountCookies" not in row and "sessionData" not in row
        assert row["created"].endswith("Z")
        assert len(imported[1]) == 1


def test_alias_refresh_preserves_creation_project_original_and_assets(tmp_path, imported):
    old_path = original()
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        store = client.app.state.store
        before = client.get("/v1/google-flow/accounts/alias", headers=AUTH).json()
        store.asset(OTHER, "original", P, str(tmp_path / "image.png"), "image/png")
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 200
        row = response.json()
        assert row["email"] == "alias" and row["created"] == before["created"]
        assert row["profile"] != "original" and row["projectId"] == P
        assert imported[1][0][1:] == (EMAIL, P)
        assert store.asset_get(OTHER)["profile"] == row["profile"]
        assert old_path.joinpath("Cookies").read_text() == "original-private-cookie"


def test_busy_original_is_rejected_before_import(tmp_path, imported):
    original()
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        client.app.state.store.submit("images", "original", {"prompt": "queued"}, None)
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 409 and imported[1] == []


def test_job_race_after_verification_rolls_back_mapping_and_new_candidate(
    tmp_path, imported, monkeypatch
):
    old_path = original()
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        store = client.app.state.store
        helper = __import__("gflow_cli.selfhost.profile_import", fromlist=["import_cookie_profile"])
        create = helper.import_cookie_profile

        async def racing(*args, **kwargs):
            value = await create(*args, **kwargs)
            store.submit("images", "original", {"prompt": "late"}, None)
            return value

        monkeypatch.setattr(helper, "import_cookie_profile", racing)
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 409
        assert store.accounts()[0]["profile"] == "original"
        assert old_path.exists() and not auth.profile_dir(imported[1][0][0]).exists()


def test_invalid_or_rejected_cookies_never_register(tmp_path, imported, monkeypatch):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        invalid = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": "private-cookie-fixture"}
        )
        assert invalid.status_code == 400 and imported[1] == []
        assert "private-cookie-fixture" not in invalid.text

        async def rejected(*args, **kwargs):
            raise AuthMissingError(detail="private-cookie-fixture")

        monkeypatch.setattr("gflow_cli.selfhost.profile_import.import_cookie_profile", rejected)
        failure = client.post("/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES})
        assert failure.status_code == 400 and "private-cookie-fixture" not in failure.text
        assert client.app.state.store.accounts() == []


def test_atomic_store_refresh_preserves_history_and_refuses_busy(tmp_path):
    store = Store(tmp_path)
    store.account_set("original", "alias", P, True, True)
    prior = store.accounts()[0]
    job = store.submit("images", "original", {"prompt": "old"}, None)
    store.finish(job["jobId"], "completed", {"media": []})
    store.asset(OTHER, "original", P, "/private/local-image", "image/png")
    store.account_activate_import("version", "alias", P, expected_old=prior)
    current = store.accounts()[0]
    assert current["profile"] == "version" and current["created"] == prior["created"]
    assert current["verification_source"] == "native-cookie-verified"
    assert store.asset_get(OTHER)["profile"] == "version"
    assert store.by_idempotency("missing") is None
    with store.connection() as connection:
        assert connection.execute("SELECT profile FROM jobs").fetchone()[0] == "original"
    store.submit("images", "version", {"prompt": "queued"}, None)
    with pytest.raises(ValueError):
        store.account_activate_import("another", "alias", P, expected_old=current)
    assert store.accounts()[0]["profile"] == "version"


def test_changed_candidate_retained_with_safe_cleanup_feedback(tmp_path, imported, monkeypatch):
    helper = __import__("gflow_cli.selfhost.profile_import", fromlist=["import_cookie_profile"])
    create = helper.import_cookie_profile

    async def changed(*args, **kwargs):
        value = await create(*args, **kwargs)
        auth.profile_dir(value.profile).joinpath(".gflow_account").write_text(
            "changed@example.test"
        )
        return value

    cleanup = AsyncMock(return_value=False)
    monkeypatch.setattr(helper, "import_cookie_profile", changed)
    monkeypatch.setattr(helper, "discard_imported_profile", cleanup)
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        response = client.post("/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES})
        assert response.status_code == 409
        assert response.json()["detail"]["cleanupPending"] is True
        assert response.json()["detail"]["candidateProfile"] == imported[1][0][0]
        assert "private-cookie-fixture" not in response.text
        assert client.app.state.store.accounts() == []
        assert auth.profile_dir(imported[1][0][0]).exists()


def test_unrelated_import_result_never_deleted(tmp_path, imported, monkeypatch):
    helper = __import__("gflow_cli.selfhost.profile_import", fromlist=["import_cookie_profile"])
    create = helper.import_cookie_profile

    async def unrelated(table, profile, **kwargs):
        return await create(table, "unrelated", **kwargs)

    cleanup = AsyncMock(return_value=True)
    monkeypatch.setattr(helper, "import_cookie_profile", unrelated)
    monkeypatch.setattr(helper, "discard_imported_profile", cleanup)
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        response = client.post("/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES})
        assert response.status_code == 400
        cleanup.assert_not_awaited()
        assert auth.profile_dir("unrelated").exists()
        assert client.app.state.store.accounts() == []


def test_cookies_alone_refresh_reverifies_preserved_project(tmp_path, imported, monkeypatch):
    from dataclasses import replace

    original()
    helper = __import__("gflow_cli.selfhost.profile_import", fromlist=["import_cookie_profile"])
    create = helper.import_cookie_profile

    async def discovered(*args, **kwargs):
        value = await create(*args, **kwargs)
        return replace(value, project_id=OTHER)

    async def reverify(value, project):
        return replace(value, project_id=project)

    verify = AsyncMock(side_effect=reverify)
    monkeypatch.setattr(helper, "import_cookie_profile", discovered)
    monkeypatch.setattr("gflow_cli.selfhost.account_import.reverify_imported_project", verify)
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        response = client.post("/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES})
        assert response.status_code == 200
        assert response.json()["projectId"] == P and response.json()["email"] == "alias"
        verify.assert_awaited_once()
        assert verify.await_args.args[1] == P


def test_original_lease_contention_refuses_before_import(tmp_path, imported):
    from gflow_cli.profile_lease import ProfileLease

    path = original()
    with (
        ProfileLease(path),
        TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client,
    ):
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 409 and imported[1] == []
        assert client.app.state.store.accounts()[0]["profile"] == "original"


def test_registry_change_after_import_preserves_original(tmp_path, imported, monkeypatch):
    original()
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        helper = __import__("gflow_cli.selfhost.profile_import", fromlist=["import_cookie_profile"])
        create = helper.import_cookie_profile

        async def changed(*args, **kwargs):
            value = await create(*args, **kwargs)
            client.app.state.store.account_set("original", "alias", OTHER, True, True)
            return value

        monkeypatch.setattr(helper, "import_cookie_profile", changed)
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 409
        row = client.app.state.store.accounts()[0]
        assert row["profile"] == "original" and row["project"] == OTHER
        assert not auth.profile_dir(imported[1][0][0]).exists()


def test_v2_accounts_migrate_without_losing_registration_and_persist_source(tmp_path):
    import sqlite3

    path = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE accounts(profile TEXT PRIMARY KEY,"
        "email TEXT NOT NULL COLLATE NOCASE UNIQUE,project TEXT NOT NULL,"
        "enabled INTEGER NOT NULL,verified INTEGER NOT NULL); PRAGMA user_version=2;"
    )
    connection.execute("INSERT INTO accounts VALUES(?,?,?,?,?)", ("original", "alias", P, 1, 1))
    connection.commit()
    connection.close()
    store = Store(tmp_path)
    before = store.accounts()[0]
    assert before["verification_source"] == "operator-attested" and before["created"] > 0
    store.account_activate_import("version", "alias", P, expected_old=before)
    reopened = Store(tmp_path).accounts()[0]
    assert reopened["created"] == before["created"]
    assert reopened["verification_source"] == "native-cookie-verified"
    assert reopened["profile"] == "version"


def test_refresh_replaces_worker_and_preserves_original_profile(tmp_path, imported, monkeypatch):
    import asyncio
    import threading

    old_path = original()
    started = []
    refreshed = threading.Event()

    async def idle_worker(cfg, store, profile):
        started.append(profile)
        if profile != "original":
            refreshed.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("gflow_cli.selfhost.server.worker", idle_worker)
    with TestClient(create_app(config(tmp_path, old=True), start_workers=True)) as client:
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 200
        assert refreshed.wait(2)
        assert started == ["original", response.json()["profile"]]
        assert old_path.joinpath("Cookies").read_text() == "original-private-cookie"


def test_http_refresh_preserves_registered_aliases_and_confirmed_delete_receipts(
    tmp_path, imported, monkeypatch
):
    import hashlib
    import json
    from urllib.parse import quote

    from gflow_cli.api.native_delete_receipts import DeleteReceipts
    from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore

    old_path = original()
    owner = hashlib.sha256(EMAIL.casefold().encode()).hexdigest()
    DeleteReceipts(old_path, owner, P).record(OTHER, "image")
    calls = []

    async def run(argv, timeout):
        calls.append(argv)
        body = json.loads(argv[5])
        return 0, json.dumps(
            {
                "status": "ok",
                "projectId": body["project_id"],
                "mediaGenerationId": body["media_id"],
                "kind": "image",
                "url": "https://flow-content.google/image/owned",
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = config(tmp_path, old=True)
    alias = "user:opaque-email:opaque-image:" + OTHER
    with TestClient(create_app(cfg, start_workers=False)) as client:
        NativeAliasStore(cfg.root).register(
            NativeAlias(alias, "original", "alias", P, OTHER, "image")
        )
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 200
        new_profile = response.json()["profile"]
        assert response.json()["preservedDeleteReceipts"] == 1
        assert DeleteReceipts(auth.profile_dir(new_profile), owner, P).kind(OTHER) == "image"
        assert DeleteReceipts(old_path, owner, P).kind(OTHER) == "image"
        read = client.get("/v1/google-flow/assets/" + quote(alias, safe=""), headers=AUTH)
        assert read.status_code == 200
        assert calls[-1][4] == new_profile
        assert NativeAliasStore(cfg.root).get(alias).profile == "original"
        assert response.json()["updated"] >= response.json()["created"]


def test_http_activation_failure_discards_carried_receipts(tmp_path, imported):
    import hashlib

    from gflow_cli.api.native_delete_receipts import DeleteReceipts

    old_path = original()
    owner = hashlib.sha256(EMAIL.casefold().encode()).hexdigest()
    DeleteReceipts(old_path, owner, P).record(OTHER, "image")
    with TestClient(create_app(config(tmp_path, old=True), start_workers=False)) as client:
        with client.app.state.store.connection() as conn:
            conn.execute(
                "CREATE TRIGGER refuse_activation BEFORE UPDATE ON accounts BEGIN "
                "SELECT RAISE(ABORT, 'synthetic'); END"
            )
        response = client.post(
            "/v1/google-flow/accounts", headers=AUTH, json={"cookies": COOKIES, "email": "alias"}
        )
        assert response.status_code == 409
        candidate = imported[1][-1][0]
        assert not auth.profile_dir(candidate).exists()
        assert DeleteReceipts(old_path, owner, P).kind(OTHER) == "image"
        assert client.app.state.store.account_lookup("alias")["profile"] == "original"
