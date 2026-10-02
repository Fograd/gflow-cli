# PLAN — a busy catalog after a successful generation is not a failed generation (#900)

**Evidence (offline, real SQLite, 2026-10-02).** With a second connection holding the write
lock, `update_operation_status` and `update_asset_status` waited the 5 s `busy_timeout` and
raised a raw `sqlite3.OperationalError: database is locked`; a nested `transaction()` raised
a raw "cannot start a transaction within a transaction". None is a `DataStoreError`. End to
end, `gflow video t2v` on a successful (faked) generation exited **1** as
`error_unhandled OperationalError`.

**Root cause.** `DataStore.transaction()` (`data/store.py`) — the one context every catalog
write goes through — lets raw sqlite errors escape. Every success-recording site already
catches `DataStoreError` and warns instead of failing (`cli_video.py` ×4, `cli_image.py`,
`cli_movie.py`, `image_batch._record_row_success`); an untyped error misses all of them.
`chain_repo.py:129` already translates by hand at its own call site.

**Fix at the root.** `transaction()` re-raises `sqlite3.Error` as `DataStoreError`
(route `data.transaction`), except `sqlite3.IntegrityError`, which callers translate into
`DataIntegrityError` with their own routes. Non-sqlite exceptions pass through unchanged.
Not a transport/auth/selector/schema change: no predict.

**Not in scope.** Whether a recording failure should also leave the STARTED row as
`started` is the status-model cluster (#898). No reentrancy (savepoints): no nested caller
exists; a nested BEGIN now fails typed. No Flow surface: the real thing here is SQLite, and
the tests use a real file and a real second connection.

## Scenarios

1. A write blocked past `busy_timeout` raises `DataStoreError` (cause: the sqlite error).
2. A nested `transaction()` raises `DataStoreError`.
3. An `IntegrityError` still reaches callers raw (their `DataIntegrityError` routes hold).
4. A non-sqlite exception inside the block passes through unchanged, and rolls back.
5. `gflow video t2v`: a successful generation whose recording is blocked exits 0 with the
   persistence warning, and no `failed` operation row.
6. MCP/worker: the daemon already logs-and-continues on recording errors (`daemon.py`); no change.

## Tasks

- [x] 1. RED: scenarios 1–5.
- [x] 2. GREEN: translate in `transaction()`.
- [x] 3. Docs: CHANGELOG Fixed; USAGE exit 16 bullets.
- [ ] 4. `/gflow:check`, PR, council, Sonar.
