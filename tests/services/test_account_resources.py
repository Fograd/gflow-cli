"""Bounded observed account enumeration with real private SQLite checkpoints."""

import asyncio
import importlib
import json
import sqlite3

import pytest

P1 = "00000000-0000-4000-8000-000000000001"
P2 = "00000000-0000-4000-8000-000000000002"
I1 = "00000000-0000-4000-8000-000000000011"
I2 = "00000000-0000-4000-8000-000000000012"
W = "00000000-0000-4000-8000-000000000021"


def module():
    return importlib.import_module("gflow_cli.services.account_resources")


def catalog(project, identifier):
    return {
        "project_id": project,
        "characters": [
            {
                "entity_id": identifier,
                "project_id": project,
                "workflow_ids": [W],
                "personality": "PRIVATE_PERSONALITY",
            }
        ],
        "user_voices": [
            {
                "ref": identifier,
                "project_id": project,
                "workflow_id": W,
                "source": "user",
                "dialogue": "PRIVATE_DIALOGUE",
                "audio_url": "https://private.invalid/signed-secret",
            }
        ],
    }


class Client:
    def __init__(self, projects=None, catalogs=None):
        self.pages = projects or {None: ([P1, P2], None)}
        self.catalogs = catalogs or {P1: catalog(P1, I1), P2: catalog(P2, I2)}
        self.calls = []

    async def list_native_projects(self, cursor=None, **kwargs):
        self.calls.append((cursor, kwargs))
        if kwargs:
            assert kwargs == {
                "include_catalogs": True,
                "catalog_project_ids": [kwargs["catalog_project_ids"][0]],
                "max_projects": 1,
            }
            project = kwargs["catalog_project_ids"][0]
            return {"project_catalogs": [self.catalogs[project]]}
        projects, following = self.pages[cursor]
        return {
            "projects": [{"project_id": item} for item in projects],
            "next_cursor": following,
            "pagination_exhausted": following is None,
        }


async def read(client, root, **kwargs):
    return await module().list_account_resources(
        client,
        root,
        profile="one",
        account="operator@example.test",
        kind=kwargs.pop("kind", "character"),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_budget_resume_and_strict_typed_rows(tmp_path):
    client = Client()
    first = await read(client, tmp_path, max_projects=1)
    assert first["returned_count"] == 1 and first["pending_project_count"] == 1
    assert first["pages_read"] == 1 and first["catalog_projects_read"] == 1
    assert first["complete"] is None and not first["deletion_authority"]
    assert first["truncated"] and not first["traversal_finished"]
    row = first["resources"][0]
    assert row == {
        "kind": "character",
        "native_id": I1,
        "origin_project_id": P1,
        "observed_in_project_ids": [P1],
        "workflow_ids": [W],
    }
    second = await read(client, tmp_path, cursor=first["next_cursor"], max_projects=1)
    assert second["resources"][0]["native_id"] == I2
    assert second["returned_count"] == 1 and second["observed_count"] == 2
    assert second["traversal_finished"] and second["next_cursor"] is None
    assert second["complete"] is None


@pytest.mark.asyncio
async def test_typed_voice_is_not_character_or_system_preset(tmp_path):
    result = await read(Client(), tmp_path, kind="voice")
    assert result["resources"][0] == {
        "kind": "voice",
        "native_id": I1,
        "origin_project_id": P1,
        "observed_in_project_ids": [P1],
        "workflow_id": W,
    }
    disk = (tmp_path / "account_resources.sqlite3").read_bytes()
    assert not any(
        secret in disk
        for secret in (
            b"PRIVATE_DIALOGUE",
            b"PRIVATE_PERSONALITY",
            b"signed-secret",
            b"operator@example.test",
        )
    )
    assert (tmp_path / "account_resources.sqlite3").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_native_cursor_is_private_and_pages_bounded(tmp_path):
    client = Client(
        projects={None: ([P1], "native-secret-cursor"), "native-secret-cursor": ([P2], None)}
    )
    result = await read(client, tmp_path, max_pages=1)
    assert result["next_cursor"] and "native-secret" not in json.dumps(result)
    assert result["cursor_count"] == 1 and result["pages_read"] == 1
    result = await read(client, tmp_path, cursor=result["next_cursor"])
    assert result["pages_read"] == 1 and result["total_pages_read"] == 2


@pytest.mark.asyncio
async def test_stale_and_wrong_scope_cursor_before_native_read(tmp_path):
    client = Client()
    old = await read(client, tmp_path, max_projects=1)
    await read(client, tmp_path)
    before = len(client.calls)
    with pytest.raises(ValueError, match="cursor"):
        await read(client, tmp_path, cursor=old["next_cursor"])
    with pytest.raises(ValueError, match="cursor"):
        await read(client, tmp_path, kind="voice", cursor=old["next_cursor"])
    with pytest.raises(ValueError, match="cursor"):
        await module().list_account_resources(
            client,
            tmp_path,
            profile="other",
            account="operator@example.test",
            kind="character",
            cursor=old["next_cursor"],
        )
    assert len(client.calls) == before


@pytest.mark.asyncio
async def test_fresh_epoch_empty_does_not_delete_old_observation(tmp_path):
    await read(Client(), tmp_path)
    empty = Client(projects={None: ([], None)})
    result = await read(empty, tmp_path)
    assert result["resources"] == [] and result["observed_count"] == 0
    assert result["complete"] is None and result["traversal_finished"]
    with sqlite3.connect(tmp_path / "account_resources.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_conflicting_origin_rejects_and_preserves_committed_page(tmp_path):
    client = Client(catalogs={P1: catalog(P1, I1), P2: catalog(P2, I1)})
    first = await read(client, tmp_path, max_projects=1)
    with pytest.raises(ValueError, match="origin"):
        await read(client, tmp_path, cursor=first["next_cursor"])
    with sqlite3.connect(tmp_path / "account_resources.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_cancellation_does_not_commit_partial_catalog(tmp_path):
    client = Client()
    first = await read(client, tmp_path, max_projects=1)
    original = client.list_native_projects

    async def cancel(*args, **kwargs):
        if kwargs:
            raise asyncio.CancelledError()
        return await original(*args, **kwargs)

    client.list_native_projects = cancel
    with pytest.raises(asyncio.CancelledError):
        await read(client, tmp_path, cursor=first["next_cursor"])
    client.list_native_projects = original
    result = await read(client, tmp_path, cursor=first["next_cursor"])
    assert result["resources"][0]["native_id"] == I2


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_projects", True),
        ("max_projects", 0),
        ("max_projects", 21),
        ("max_pages", True),
        ("max_pages", 101),
        ("max_seconds", 181),
        ("max_seconds", 0),
        ("kind", "all"),
        ("cursor", "not-a-cursor"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_control_before_storage_and_native_access(tmp_path, field, value):
    root = tmp_path / "absent"
    client = Client()
    with pytest.raises(ValueError):
        await read(client, root, **{field: value})
    assert not root.exists() and client.calls == []


@pytest.mark.asyncio
async def test_cursor_cycle_is_not_exhaustion(tmp_path):
    client = Client(projects={None: ([], "cycle"), "cycle": ([], "cycle")})
    first = await read(client, tmp_path)
    with pytest.raises(ValueError, match="cycle"):
        await read(client, tmp_path, cursor=first["next_cursor"])


@pytest.mark.asyncio
async def test_result_drain_is_bounded_without_more_native_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(module(), "RESULT_LIMIT", 1)
    client = Client()
    first = await read(client, tmp_path)
    assert first["returned_count"] == 1 and first["pending_result_count"] == 1
    before = len(client.calls)
    final = await read(client, tmp_path, cursor=first["next_cursor"])
    assert final["resources"][0]["native_id"] == I2
    assert final["next_cursor"] is None and len(client.calls) == before
    assert final["pages_read"] == 0 and final["catalog_projects_read"] == 0


@pytest.mark.asyncio
async def test_timeout_only_returns_committed_rows_and_reusable_cursor(tmp_path):
    client = Client()
    original = client.list_native_projects

    async def slow(cursor=None, **kwargs):
        if kwargs and kwargs["catalog_project_ids"] == [P2]:
            await asyncio.sleep(2)
        return await original(cursor, **kwargs)

    client.list_native_projects = slow
    first = await read(client, tmp_path, max_seconds=1)
    assert first["timed_out"] and first["returned_count"] == 1
    assert first["pending_project_count"] == 1 and first["next_cursor"]
    client.list_native_projects = original
    final = await read(client, tmp_path, cursor=first["next_cursor"])
    assert final["observed_count"] == 2 and final["resources"][0]["native_id"] == I2


@pytest.mark.asyncio
async def test_same_uuid_in_distinct_resource_kinds_is_not_collapsed(tmp_path):
    await read(Client(), tmp_path)
    result = await read(Client(), tmp_path, kind="voice")
    assert result["observed_count"] == 2
    with sqlite3.connect(tmp_path / "account_resources.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 4


@pytest.mark.asyncio
async def test_concurrent_epoch_advance_is_rejected(tmp_path):
    arrived, release = asyncio.Event(), asyncio.Event()
    client = Client()
    original = client.list_native_projects

    async def blocked(*args, **kwargs):
        arrived.set()
        await release.wait()
        return await original(*args, **kwargs)

    client.list_native_projects = blocked
    task = asyncio.create_task(read(client, tmp_path))
    await arrived.wait()
    await read(Client(projects={None: ([], None)}), tmp_path)
    release.set()
    with pytest.raises(ValueError, match="concurrently"):
        await task


@pytest.mark.asyncio
async def test_concurrent_epoch_before_output_cannot_adopt_another_scan(tmp_path, monkeypatch):
    from gflow_cli.services.account_resource_checkpoint import ResourceCheckpoint

    original = ResourceCheckpoint.current

    def superseded(store):
        store.load(None)
        return original(store)

    monkeypatch.setattr(ResourceCheckpoint, "current", superseded)
    with pytest.raises(ValueError, match="concurrently"):
        await read(Client(), tmp_path)
