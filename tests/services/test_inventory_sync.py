"""Durable native sync resumes verified reads without absence-based deletion."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.services.inventory_sync import sync_native_inventory

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"
W = "44444444-4444-4444-8444-444444444444"


def page(ids, cursor=None):
    return {
        "projects": [{"project_id": p, "name": "SECRET"} for p in ids],
        "next_cursor": cursor,
        "pagination_exhausted": cursor is None,
    }


def catalog(p=P):
    return {
        "project_id": p,
        "media": [
            {
                "media_id": M,
                "project_id": p,
                "workflow_id": W,
                "kind": "image",
                "url": "https://SECRET",
            }
        ],
        "workflows": [
            {
                "media_id": M,
                "workflow_id": W,
                "project_id": p,
                "archived": False,
                "batch_media_ids": [M],
            }
        ],
        "characters": [],
        "user_voices": [],
    }


def history(ids=(), cursor=None):
    return {
        "workflows": [{"workflow_id": W, "project_id": p} for p in ids],
        "media": [],
        "pages_read": 1,
        "next_cursor": cursor,
        "pagination_exhausted": cursor is None,
    }


def client(projects=(), histories=None):
    return SimpleNamespace(
        list_native_projects=AsyncMock(side_effect=projects),
        list_native_history=AsyncMock(side_effect=histories or [history()]),
    )


async def run(c, root, **kw):
    return await sync_native_inventory(c, root, profile="p", account="acct@example.test", **kw)


@pytest.mark.asyncio
async def test_checkpoint_resumes_pending_catalog_before_next_discovery(tmp_path):
    c = client([page([P], "next"), {"project_catalogs": [catalog()]}, page([])])
    first = await run(c, tmp_path, max_steps=1)
    assert first["pending_project_count"] == 1 and first["steps_read"] == 1
    second = await run(c, tmp_path, max_steps=10)
    assert second["traversal_finished"] is True and second["complete"] is None
    assert second["observations"]["project_catalog"]["media"] == 1
    assert c.list_native_projects.await_args_list[1].kwargs == {
        "include_catalogs": True,
        "catalog_project_ids": [P],
        "max_projects": 1,
    }
    assert c.list_native_projects.await_args_list[2].kwargs == {"cursor": "next"}
    assert "SECRET" not in (tmp_path / "native_inventory_sync.sqlite3").read_bytes().decode(
        errors="ignore"
    )
    assert all(item["complete"] is None for item in second["resource_scopes"].values())


@pytest.mark.asyncio
async def test_failure_keeps_checkpoint_and_empty_restart_never_deletes(tmp_path):
    c = client([page([P]), RuntimeError("interrupted")])
    with pytest.raises(RuntimeError):
        await run(c, tmp_path)
    resumed = client([{"project_catalogs": [catalog()]}])
    assert (await run(resumed, tmp_path))["traversal_finished"]
    empty = client([page([])])
    result = await run(empty, tmp_path, restart=True)
    assert result["observations"]["project_catalog"]["media"] == 1


@pytest.mark.asyncio
async def test_history_only_project_is_hydrated_then_history_resumes(tmp_path):
    c = client(
        [page([]), {"project_catalogs": [catalog(Q)]}], [history([Q], "history-next"), history()]
    )
    result = await run(c, tmp_path)
    assert result["traversal_finished"]
    assert c.list_native_projects.await_args_list[1].kwargs["catalog_project_ids"] == [Q]
    assert c.list_native_history.await_args_list[1].kwargs == {"cursor": "history-next"}
    assert result["observations"]["native_history"]["workflows"] == 1


@pytest.mark.asyncio
async def test_scope_isolation_and_private_modes(tmp_path):
    c = client([page([]), page([])])
    await run(c, tmp_path, max_steps=1)
    result = await sync_native_inventory(
        c, tmp_path, profile="q", account="acct@example.test", max_steps=1
    )
    assert result["steps_read"] == 1
    assert (tmp_path / "native_inventory_sync.sqlite3").stat().st_mode & 0o077 == 0
    with sqlite3.connect(tmp_path / "native_inventory_sync.sqlite3") as conn:
        assert conn.execute("select count(*) from checkpoints").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_cycle_is_detected_across_invocations(tmp_path):
    c = client([page([], "cycle"), page([], "cycle")])
    await run(c, tmp_path, max_steps=1)
    with pytest.raises(ValueError, match="cycle"):
        await run(c, tmp_path, max_steps=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options", [{"max_steps": 0}, {"max_steps": True}, {"max_seconds": 0}, {"restart": "yes"}]
)
async def test_invalid_controls_precede_storage_and_google(tmp_path, options):
    c = client([])
    with pytest.raises(ValueError):
        await run(c, tmp_path / "uncreated", **options)
    c.list_native_projects.assert_not_awaited()
    assert not (tmp_path / "uncreated").exists()


@pytest.mark.asyncio
async def test_time_cap_does_not_advance_unverified_catalog(tmp_path):
    import asyncio

    c = client([page([P])])
    await run(c, tmp_path, max_steps=1)

    async def delayed(**kwargs):
        await asyncio.sleep(2)
        return {"project_catalogs": [catalog()]}

    c.list_native_projects.side_effect = delayed
    result = await run(c, tmp_path, max_seconds=1)
    assert result["timed_out"] and result["steps_read"] == 0
    assert result["pending_project_count"] == 1


@pytest.mark.asyncio
async def test_concurrent_resume_rejects_stale_checkpoint(tmp_path):
    import asyncio

    arrived = asyncio.Event()
    release = asyncio.Event()

    async def delayed(**kwargs):
        arrived.set()
        await release.wait()
        return page([])

    c1 = client([])
    c1.list_native_projects.side_effect = delayed
    task = asyncio.create_task(run(c1, tmp_path, max_steps=1))
    await arrived.wait()
    await run(client([page([])]), tmp_path, max_steps=1)
    release.set()
    with pytest.raises(ValueError, match="concurrently"):
        await task


@pytest.mark.asyncio
async def test_unrelated_catalog_rows_fail_without_advancing_checkpoint(tmp_path):
    bad = catalog()
    bad["media"][0]["project_id"] = Q
    c = client([page([P]), {"project_catalogs": [bad]}])
    with pytest.raises(ValueError, match="attachment"):
        await run(c, tmp_path)
    c = client([{"project_catalogs": [catalog()]}])
    result = await run(c, tmp_path)
    assert result["observations"]["project_catalog"]["media"] == 1


@pytest.mark.asyncio
async def test_real_catalog_fixture_and_attachments_keep_origin_scope(tmp_path):
    from gflow_cli.api.native_catalogs import project_catalog_snapshot
    from tests.api.transports.test_character_details import P as FIXTURE_PROJECT
    from tests.api.transports.test_character_details import fixture

    real = project_catalog_snapshot(fixture(), FIXTURE_PROJECT)
    c = client([page([FIXTURE_PROJECT]), {"project_catalogs": [real]}])
    result = await run(c, tmp_path)
    assert result["observations"]["project_catalog"]["characters"] == real["counts"]["characters"]
    with sqlite3.connect(tmp_path / "native_inventory_sync.sqlite3") as conn:
        rows = conn.execute("SELECT metadata FROM observations").fetchall()
    assert not any("https:" in row[0] or "caption" in row[0] for row in rows)


@pytest.mark.asyncio
async def test_already_exhausted_sync_is_a_noop(tmp_path):
    await run(client([page([])]), tmp_path)
    c = client([])
    result = await run(c, tmp_path)
    assert result["steps_read"] == 0 and result["traversal_finished"]
    c.list_native_projects.assert_not_awaited()
    c.list_native_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_known_kind_cannot_change_and_prior_metadata_survives(tmp_path):
    await run(client([page([P]), {"project_catalogs": [catalog()]}]), tmp_path)
    changed = catalog()
    changed["media"][0]["kind"] = "audio"
    c = client([page([P]), {"project_catalogs": [changed]}])
    with pytest.raises(ValueError, match="kind"):
        await run(c, tmp_path, restart=True)
    resumed = await run(client([{"project_catalogs": [catalog()]}]), tmp_path)
    assert resumed["observations"]["project_catalog"]["media"] == 1


@pytest.mark.asyncio
async def test_same_identity_cannot_move_to_a_different_origin_project(tmp_path):
    await run(client([page([P]), {"project_catalogs": [catalog()]}]), tmp_path)
    c = client([page([Q]), {"project_catalogs": [catalog(Q)]}])
    with pytest.raises(ValueError, match="project"):
        await run(c, tmp_path, restart=True)


@pytest.mark.asyncio
async def test_multiple_attachments_and_character_workflows_survive_fresh_scan(tmp_path):
    import json

    attached = catalog(Q)
    attached["media"][0].update(project_id=P, attached_to_project_id=Q)
    attached["workflows"] = []
    attached["characters"] = [{"entity_id": M, "project_id": Q, "workflow_ids": [W]}]
    other = catalog(M)
    other["media"][0].update(project_id=P, attached_to_project_id=M)
    other["workflows"] = []
    other["characters"] = []
    c = client([page([Q, M]), {"project_catalogs": [attached]}, {"project_catalogs": [other]}])
    result = await run(c, tmp_path)
    assert result["retained_unique_counts"]["media"] == 1
    assert result["project_pages_read"] == result["history_pages_read"] == 1
    assert result["deletion_authority"] is False
    prior_scan = result["scan_id"]
    prior_version = result["checkpoint_version"]
    attached["characters"][0]["workflow_ids"] = [P]
    fresh = await run(client([page([Q]), {"project_catalogs": [attached]}]), tmp_path, restart=True)
    assert fresh["scan_id"] != prior_scan and fresh["checkpoint_version"] > prior_version
    with sqlite3.connect(tmp_path / "native_inventory_sync.sqlite3") as conn:
        rows = {
            r[0]: json.loads(r[1])
            for r in conn.execute(
                "SELECT resource,metadata FROM observations "
                "WHERE resource IN ('media','characters')"
            )
        }
    assert set(rows["media"]["attached_to_project_ids"]) == {Q, M}
    assert set(rows["characters"]["workflow_ids"]) == {W, P}
    assert rows["media"]["project_id"] == P


@pytest.mark.asyncio
async def test_duplicate_rows_do_not_inflate_counts_and_account_markers_separate(tmp_path):
    c = client([page([P, P]), {"project_catalogs": [catalog()]}])
    result = await run(c, tmp_path)
    assert result["retained_unique_counts"]["projects"] == 1
    assert result["catalog_projects_read"] == 1
    separate = await sync_native_inventory(
        client([page([])]), tmp_path, profile="p", account="different@example.test"
    )
    assert separate["retained_unique_counts"]["media"] == 0


@pytest.mark.asyncio
async def test_scope_change_after_read_refuses_before_commit(tmp_path):
    checks = 0

    def verify():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise ValueError("identity changed")

    with pytest.raises(ValueError, match="identity changed"):
        await run(client([page([P])]), tmp_path, verify_scope=verify)
    resumed = await run(client([page([])]), tmp_path, max_steps=1)
    assert resumed["pending_project_count"] == 0
    assert resumed["retained_unique_counts"]["projects"] == 0


@pytest.mark.asyncio
async def test_sdk_rechecks_recorded_principal_after_native_read(tmp_path, monkeypatch):
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.errors import ConfigurationError

    scopes = iter(
        [(tmp_path, "p", "acct@example.test")] * 3 + [(tmp_path, "p", "other@example.test")]
    )
    monkeypatch.setattr(
        "gflow_cli.services.account_resources.account_resource_scope", lambda _: next(scopes)
    )
    with pytest.raises(ConfigurationError, match="identity changed"):
        await FlowApiClient.sync_native_inventory(client([page([P])]), max_steps=1)
    with sqlite3.connect(tmp_path / "native_inventory_sync.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_legacy_checkpoint_and_single_attachment_upgrade_without_loss(tmp_path):
    import json

    attached = catalog(Q)
    attached["workflows"] = []
    attached["media"][0].update(project_id=P, attached_to_project_id=Q)
    await run(client([page([Q]), {"project_catalogs": [attached]}]), tmp_path)
    db = tmp_path / "native_inventory_sync.sqlite3"
    with sqlite3.connect(db) as conn:
        state = json.loads(conn.execute("SELECT state FROM checkpoints").fetchone()[0])
        for field in ("scan_id", "project_pages_read", "history_pages_read"):
            state.pop(field)
        conn.execute("UPDATE checkpoints SET state=?", (json.dumps(state),))
        metadata = json.loads(
            conn.execute("SELECT metadata FROM observations WHERE resource='media'").fetchone()[0]
        )
        metadata.pop("attached_to_project_ids")
        conn.execute(
            "UPDATE observations SET metadata=? WHERE resource='media'", (json.dumps(metadata),)
        )
    first = await run(client([]), tmp_path)
    second = await run(client([]), tmp_path)
    assert first["scan_id"] == second["scan_id"] and second["traversal_finished"]
    attached["project_id"] = M
    attached["media"][0]["attached_to_project_id"] = M
    await run(client([page([M]), {"project_catalogs": [attached]}]), tmp_path, restart=True)
    with sqlite3.connect(db) as conn:
        metadata = json.loads(
            conn.execute("SELECT metadata FROM observations WHERE resource='media'").fetchone()[0]
        )
    assert set(metadata["attached_to_project_ids"]) == {Q, M}
