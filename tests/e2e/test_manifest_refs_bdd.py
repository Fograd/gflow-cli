"""E2E: `"ref": "batch:N"` on `gflow run --config`, against live Flow (#913).

Binds ``tests/features/manifest_refs_live.feature``. Selected by ``-m e2e_image``; see
``docs/E2E_TESTING.md`` § BDD-bound e2e.

**Why an e2e.** Offline tests pin our wiring with a fake page. Only a live run proves Flow
still lists the parent in the ``@`` picker under its reply caption, that the picker
option's thumbnail token still equals the grid tile's, and that the submit Flow accepts
carries the parent's media id (the route guard aborts it otherwise).

**Cost.** Four images of daily quota, zero Veo credits. Prints each run's
``mention_miss`` count: the search-lag measurement PLAN Task 8 asks for.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

scenarios("../features/manifest_refs_live.feature")

_ROWS = [
    {"text": "a single red apple on a wooden table", "aspect_ratio": "1:1"},
    {"text": "the same apple, now green", "aspect_ratio": "1:1", "ref": "batch:0"},
    {"text": "the same apple, cut in half", "aspect_ratio": "1:1", "ref": "batch:0"},
    {"text": "the green apple on a blue plate", "aspect_ratio": "1:1", "ref": "batch:1"},
]
_PARENT = {1: 0, 2: 0, 3: 1}


@given(
    "a run config with row 0 plain, rows 1 and 2 referencing row 0, and row 3 referencing row 1",
    target_fixture="world",
)
def _config(tmp_path: Path, e2e_env: dict[str, str]) -> dict[str, Any]:
    cfg = tmp_path / "run.json"
    cfg.write_text(json.dumps({"prompts": _ROWS}), encoding="utf-8")
    return {"cfg": cfg, "env": e2e_env, "out": tmp_path / "run_out"}


@when("gflow run executes it on the live profile")
def _run(world: dict[str, Any]) -> None:
    env = {**world["env"], "GFLOW_CLI_LOG_FORMAT": "json"}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "gflow_cli",
            "run",
            "--config",
            str(world["cfg"]),
            "--output-dir",
            str(world["out"]),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=1500,
    )
    events: list[dict[str, Any]] = []
    for line in proc.stderr.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    world.update(proc=proc, events=events)
    log = world["out"].parent / "run.log"
    log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    for e in events:
        if e.get("level") in ("error", "warning"):
            print(f"[#913 event] {json.dumps(e)[:600]}")
    print(f"[#913 log] {log}")
    misses = sum(1 for e in events if e.get("event") == "migrated.mention_miss")
    print(f"\n[#913 lag] mention_miss across 3 referencing rows: {misses}")


@then("every row succeeds and saves its image")
def _all_ok(world: dict[str, Any]) -> None:
    proc = world["proc"]
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    saved = sorted(p.name for p in world["out"].glob("prompt_*"))
    assert [n.split("_")[1] for n in saved] == ["0", "1", "2", "3"], saved


@then("each referencing row attached its parent in place, with no upload")
def _in_place(world: dict[str, Any]) -> None:
    names = [e.get("event") for e in world["events"]]
    assert names.count("migrated.existing_references_attached") == len(_PARENT), names
    assert "migrated.references_attached" not in names  # the upload path never ran


@then("the catalog records each referencing row as image-to-image with its parent as input")
def _lineage(world: dict[str, Any]) -> None:
    db = Path(world["env"]["GFLOW_CLI_DB_PATH"])
    with sqlite3.connect(db) as con:
        ops = dict(con.execute("SELECT prompt, mode FROM operations").fetchall())
        out_media = dict(
            con.execute(
                "SELECT o.prompt, a.flow_media_id FROM operation_assets l "
                "JOIN operations o ON o.id = l.operation_id "
                "JOIN assets a ON a.id = l.asset_id WHERE l.role = 'output'"
            ).fetchall()
        )
        inputs = dict(
            con.execute(
                "SELECT o.prompt, a.flow_media_id FROM operation_assets l "
                "JOIN operations o ON o.id = l.operation_id "
                "JOIN assets a ON a.id = l.asset_id WHERE l.role = 'input'"
            ).fetchall()
        )
    texts = [r["text"] for r in _ROWS]
    assert ops[texts[0]] == "t2i"
    for child, parent in _PARENT.items():
        assert ops[texts[child]] == "i2i", ops
        assert inputs[texts[child]] == out_media[texts[parent]], (child, inputs, out_media)
