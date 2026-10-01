"""`batch:N` reaches the child's request, and the catalog records the lineage (#913).

SCENARIO #11, #31a (asset link), #41. The request side uses the fake client from
test_batch_outcomes; the catalog side writes to a real temporary store.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from gflow_cli.config import Settings
from gflow_cli.data.recorder import OperationRecorder
from gflow_cli.image_batch import BatchPromptItem, run_image_batch
from tests.test_batch_outcomes import FakeClient


class RecordingClient(FakeClient):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.requests: dict[str, Any] = {}

    async def generate_image(self, project_id: str, req: Any) -> Any:
        self.requests[req.prompt] = req
        return await super().generate_image(project_id, req)


def _run(
    tmp_path: Path,
    rows: list[BatchPromptItem],
    *,
    recorder: Any = None,
    fail_generate: set[str] | None = None,
) -> tuple[list[Any], RecordingClient]:
    client = RecordingClient(fail_generate=fail_generate or set(), fail_download=set())
    outcomes = asyncio.run(
        run_image_batch(
            profile_dir=tmp_path,
            headless=True,
            transport=None,
            prompts=tuple(rows),
            output_dir=tmp_path / "out",
            continue_on_error=True,
            project_title="t",
            client_factory=lambda **_: client,
            jitter_range=(0, 0),
            _profile_name="p" if recorder else None,
            _recorder=recorder,
            _command="run",
        )
    )
    return outcomes, client


def test_the_child_request_carries_the_parent_image(tmp_path: Path) -> None:
    _, client = _run(
        tmp_path,
        [BatchPromptItem("red", index=0), BatchPromptItem("green", index=1, ref="batch:0")],
    )
    refs = client.requests["green"].refs
    assert [(r.name, r.display_name) for r in refs] == [("media-red", "caption media-red")]
    assert not refs[0].local_path  # never a re-upload fallback
    assert client.requests["red"].refs == ()


def test_two_children_share_one_parent(tmp_path: Path) -> None:
    rows = [
        BatchPromptItem("red", index=0),
        BatchPromptItem("green", index=1, ref="batch:0"),
        BatchPromptItem("blue", index=2, ref="batch:0"),
    ]
    _, client = _run(tmp_path, rows)
    assert client.generated.count("red") == 1
    assert (
        client.requests["green"].refs[0].name == client.requests["blue"].refs[0].name == "media-red"
    )


@pytest.fixture
def recorder(tmp_path: Path) -> OperationRecorder:
    settings = Settings(home=tmp_path / "home", db_path=tmp_path / "gflow.db")
    return OperationRecorder.open(settings)


def _rows(db: Path, sql: str) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as con:
        return con.execute(sql).fetchall()


def test_the_catalog_links_the_child_to_its_parent(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    rows = [BatchPromptItem("red", index=0), BatchPromptItem("green", index=1, ref="batch:0")]
    _run(tmp_path, rows, recorder=recorder)
    db = tmp_path / "gflow.db"
    modes = dict(_rows(db, "SELECT prompt, mode FROM operations"))
    assert modes == {"red": "t2i", "green": "i2i"}
    links = _rows(
        db,
        "SELECT o.prompt, a.flow_media_id, l.role FROM operation_assets l "
        "JOIN operations o ON o.id = l.operation_id JOIN assets a ON a.id = l.asset_id "
        "WHERE l.role = 'input'",
    )
    assert links == [("green", "media-red", "input")]


def test_a_failed_child_is_recorded_as_image_to_image(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    rows = [BatchPromptItem("red", index=0), BatchPromptItem("green", index=1, ref="batch:0")]
    _run(tmp_path, rows, recorder=recorder, fail_generate={"green"})
    db = tmp_path / "gflow.db"
    failed = _rows(db, "SELECT prompt, mode, status FROM operations WHERE status = 'failed'")
    assert failed == [("green", "i2i", "failed")]
