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
