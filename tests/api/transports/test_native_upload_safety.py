from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import migrated_resources
from gflow_cli.api.transports import migrated_video_upload as upload
from gflow_cli.errors import NativeMediaMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
@pytest.mark.parametrize("rights", [False, None, 1, "true"])
async def test_strict_rights_before_any_browser_action(tmp_path, rights):
    page = AsyncMock()
    with pytest.raises(upload.UploadRightsRequiredError):
        await upload.upload_video(page, P, tmp_path / "missing.mp4", rights_confirmed=rights)
    assert page.mock_calls == []


class Request:
    url = f"https://flow.google.com/upload/v1/flow/upload/video/{P}"
    method = "POST"


class ChooserContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @property
    async def value(self):
        return self.chooser


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_dispatch_loss_preserves_unknown_and_cleans_observers(tmp_path, monkeypatch, cancel):
    import asyncio
    from unittest.mock import MagicMock

    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    monkeypatch.setattr(migrated_resources, "read_project_payload", AsyncMock())
    page = MagicMock()
    listeners = {}
    page.on.side_effect = lambda event, callback: listeners.update({event: callback})
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    context = ChooserContext()
    context.chooser = MagicMock()

    async def lost(*args):
        listeners["request"](Request())
        raise asyncio.CancelledError() if cancel else RuntimeError("SECRET transport body")

    context.chooser.set_files = AsyncMock(side_effect=lost)
    page.expect_file_chooser.return_value = context
    page.remove_listener.side_effect = OSError("SECRET secondary cleanup")
    expected = asyncio.CancelledError if cancel else NativeMediaMutationUnknownError
    with pytest.raises(expected) as info:
        await upload.upload_video(page, P, path, rights_confirmed=True)
    typed = vars(info.value)["gflow_native_media_unknown"] if cancel else info.value
    assert typed.operation == "upload"
    assert typed.project_id == P
    assert "SECRET" not in str(info.value)
    assert "incomplete" in info.value.__notes__[0]
    assert context.chooser.set_files.await_count == 1
    assert page.remove_listener.call_count == 2


@pytest.mark.asyncio
async def test_known_upload_handle_survives_later_failure(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock

    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    monkeypatch.setattr(migrated_resources, "read_project_payload", AsyncMock())
    page = MagicMock()
    listeners = {}
    page.on.side_effect = lambda event, callback: listeners.update({event: callback})
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    context = ChooserContext()
    context.chooser = MagicMock()
    response = MagicMock(url=Request.url, request=Request(), status=200)
    response.text = AsyncMock(
        return_value=json.dumps({"mediaId": M, "media": {"name": M, "projectId": P}})
    )

    async def accepted_then_lost(*args):
        listeners["request"](Request())
        await listeners["response"](response)
        raise RuntimeError("SECRET later failure")

    context.chooser.set_files = AsyncMock(side_effect=accepted_then_lost)
    page.expect_file_chooser.return_value = context
    with pytest.raises(NativeMediaMutationUnknownError) as info:
        await upload.upload_video(page, P, path, rights_confirmed=True)
    assert info.value.known_media_ids == (M,)
    assert context.chooser.set_files.await_count == 1
    assert "SECRET" not in str(info.value)


@pytest.mark.asyncio
async def test_listener_cleanup_fault_preserves_known_upload(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock

    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    monkeypatch.setattr(migrated_resources, "read_project_payload", AsyncMock())
    page = MagicMock()
    listeners = {}
    page.on.side_effect = lambda event, callback: listeners.update({event: callback})
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    context = ChooserContext()
    context.chooser = MagicMock()
    response = MagicMock(url=Request.url, request=Request(), status=200)
    response.text = AsyncMock(
        return_value=json.dumps({"mediaId": M, "media": {"name": M, "projectId": P}})
    )

    async def accepted(*args):
        listeners["request"](Request())
        await listeners["response"](response)

    context.chooser.set_files = AsyncMock(side_effect=accepted)
    page.expect_file_chooser.return_value = context
    page.remove_listener.side_effect = OSError("SECRET cleanup")
    with pytest.raises(NativeMediaMutationUnknownError) as info:
        await upload.upload_video(page, P, path, rights_confirmed=True)
    assert info.value.known_media_ids == (M,)
    assert page.remove_listener.call_count == 2
    assert "SECRET" not in str(info.value)


@pytest.mark.asyncio
async def test_native_project_readiness_precedes_upload_controls(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    page = MagicMock()
    ready = AsyncMock(side_effect=ValueError("Project unavailable"))
    monkeypatch.setattr(migrated_resources, "read_project_payload", ready)
    with pytest.raises(ValueError, match="Project unavailable"):
        await upload.upload_video(page, P, path, rights_confirmed=True)
    ready.assert_awaited_once_with(page, P)
    page.locator.assert_not_called()
    page.on.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mount_count", [1, 4])
async def test_rights_dialog_waits_for_one_time_button_before_counting(
    tmp_path, monkeypatch, mount_count
):
    import json
    from unittest.mock import MagicMock

    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    monkeypatch.setattr(migrated_resources, "read_project_payload", AsyncMock())
    page = MagicMock()
    listeners = {}
    page.on.side_effect = lambda event, callback: listeners.update({event: callback})
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.count = AsyncMock(side_effect=[0, 1, 1])
    buttons = page.locator.return_value.nth.return_value.get_by_role.return_value
    ready = False

    async def wait(**kwargs):
        nonlocal ready
        ready = True

    counts = iter([mount_count, 3])

    async def count():
        return next(counts, 3) if ready else 1

    buttons.count = AsyncMock(side_effect=count)
    buttons.nth.return_value.wait_for = AsyncMock(side_effect=wait)
    response = MagicMock(url=Request.url, request=Request(), status=200)
    response.text = AsyncMock(
        return_value=json.dumps({"mediaId": M, "media": {"name": M, "projectId": P}})
    )

    async def accept(**kwargs):
        assert ready
        listeners["request"](Request())
        await listeners["response"](response)

    buttons.nth.return_value.click = AsyncMock(side_effect=accept)
    chooser = ChooserContext()
    chooser.chooser = MagicMock(set_files=AsyncMock())
    page.expect_file_chooser.return_value = chooser
    result = await upload._upload_video_snapshot(page, P, path, rights_confirmed=True)
    assert result[0] == M
    page.locator.return_value.nth.assert_called_once_with(0)
    page.locator.return_value.last.get_by_role.assert_not_called()
    buttons.nth.return_value.wait_for.assert_awaited_once()
    assert all(call.args == (2,) for call in buttons.nth.call_args_list)
    buttons.nth.return_value.click.assert_awaited_once()
