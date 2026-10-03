from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.image import ImageRef
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ReferenceNotFoundError

ID = "00000000-0000-4000-8000-000000000001"


class Grid:
    def __init__(self, *, found_after=1, invalid=False, restore_error=False):
        self.found_after = found_after
        self.invalid = invalid
        self.restore_error = restore_error
        self.moves = 0
        self.restored = False
        self.wait_for_timeout = AsyncMock()

    async def evaluate(self, script, args):
        if not isinstance(args, dict):
            return ""
        action = args["action"]
        if action == "restore":
            self.restored = True
            if self.restore_error:
                raise RuntimeError("restore")
            return True
        if action == "step":
            self.moves += 1
        return {
            "tokens": {ID: "exact-token"} if self.moves >= self.found_after else {},
            "valid": not self.invalid,
            "can_scroll": True,
            "moved": self.moves < 12,
        }


@pytest.mark.asyncio
async def test_virtualized_exact_image_discovered_and_scroll_restored():
    page = Grid()
    result = await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert result == {ID: "exact-token"}
    assert page.moves == 1
    assert page.restored


@pytest.mark.asyncio
async def test_navigation_refuses_and_restores_without_returning_stale_token():
    page = Grid(invalid=True, restore_error=True)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert page.restored


@pytest.mark.asyncio
async def test_no_progress_stops_bounded_and_restores():
    page = Grid(found_after=99)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert page.moves == 12
    assert page.restored


@pytest.mark.asyncio
async def test_successful_discovery_with_failed_restore_refuses():
    page = Grid(found_after=0, restore_error=True)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert page.restored


@pytest.mark.asyncio
async def test_cancellation_stays_cancelled_and_restoration_attempted():
    import asyncio

    page = Grid()
    page.wait_for_timeout.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert page.restored


@pytest.mark.asyncio
async def test_enclosing_deadline_does_not_restart_discovery(monkeypatch):
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.transports import migrated_composer as subject

    monkeypatch.setattr(subject, "EXISTING_REF_WAIT_S", 0)
    composer = MigratedComposer()

    async def delay(*args):
        import asyncio

        await asyncio.sleep(2)

    composer._reference_existing_until = AsyncMock(side_effect=delay)
    with pytest.raises(ReferenceNotFoundError):
        await composer.reference_existing(Grid(), "project", GenerateImageRequest(prompt="x"))
    assert composer._reference_existing_until.call_count == 1


@pytest.mark.asyncio
async def test_nested_settings_timeout_is_preserved():
    from gflow_cli.api.image import GenerateImageRequest

    composer = MigratedComposer()
    original = TimeoutError("nested settings timeout")
    composer._reference_existing_until = AsyncMock(side_effect=original)
    with pytest.raises(TimeoutError) as raised:
        await composer.reference_existing(Grid(), "project", GenerateImageRequest(prompt="x"))
    assert raised.value is original


@pytest.mark.asyncio
async def test_distinct_ids_with_same_picker_token_refuse():
    second = "00000000-0000-4000-8000-000000000002"
    page = Grid(found_after=0)
    original = page.evaluate

    async def collide(script, args):
        data = await original(script, args)
        if isinstance(data, dict):
            data["tokens"][second] = "exact-token"
        return data

    page.evaluate = collide
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID), ImageRef(second)))
    assert page.restored


@pytest.mark.asyncio
async def test_immediate_scroll_no_progress_stops_after_one_step():
    page = Grid(found_after=99)
    original = page.evaluate

    async def stalled(script, args):
        result = await original(script, args)
        if isinstance(args, dict) and args["action"] == "step":
            result["moved"] = False
        return result

    page.evaluate = stalled
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(ID),))
    assert page.moves == 1
    assert page.restored
