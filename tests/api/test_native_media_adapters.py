from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.errors import ConfigurationError

PROJECT = "11111111-1111-4111-8111-111111111111"
MEDIA = "22222222-2222-4222-8222-222222222222"


def client():
    value = FlowApiClient.__new__(FlowApiClient)
    value.settings = SimpleNamespace(flow_host="flow.google.com")
    value._checkout_page = AsyncMock(side_effect=AssertionError("must not open browser"))
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("rights", [False, 1, "true", None])
async def test_upload_rights_before_checkout(tmp_path, rights):
    value = client()
    with pytest.raises(ConfigurationError):
        await value.upload_native_video(
            project_id=PROJECT, path=tmp_path / "missing.mp4", rights_confirmed=rights
        )
    value._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation", [False, 1, "true", None])
async def test_archive_confirmation_before_checkout(confirmation):
    value = client()
    with pytest.raises(ConfigurationError):
        await value.archive_native_media(
            project_id=PROJECT, media_ids=[MEDIA], confirm_archive=confirmation
        )
    value._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[], [MEDIA, MEDIA.upper()], ["bad"], [MEDIA] * 101])
async def test_archive_all_identifiers_before_checkout(ids):
    value = client()
    with pytest.raises(ConfigurationError):
        await value.archive_native_media(project_id=PROJECT, media_ids=ids, confirm_archive=True)
    value._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "archive"])
async def test_native_mutation_unknown_is_single_attempt_and_checked_in(
    tmp_path, monkeypatch, operation
):
    from unittest.mock import Mock

    from gflow_cli.errors import NativeMediaMutationUnknownError

    value = client()
    page = object()
    value._checkout_page = AsyncMock(return_value=page)
    value._checkin_page = Mock()
    error = NativeMediaMutationUnknownError(
        operation=operation, phase="response", project_id=PROJECT, known_media_ids=(MEDIA,)
    )
    call = AsyncMock(side_effect=error)
    if operation == "upload":
        monkeypatch.setattr(
            "gflow_cli.api.transports.migrated_video_upload._upload_video_snapshot", call
        )
        path = tmp_path / "one.mp4"
        path.write_bytes(b"\x00\x00\x00\x0cftypisom")
        with pytest.raises(NativeMediaMutationUnknownError) as caught:
            await value.upload_native_video(project_id=PROJECT, path=path, rights_confirmed=True)
        assert not call.call_args.args[2].exists()
    else:
        monkeypatch.setattr("gflow_cli.api.transports.migrated_resources.trash_media", call)
        with pytest.raises(NativeMediaMutationUnknownError) as caught:
            await value.archive_native_media(
                project_id=PROJECT, media_ids=[MEDIA], confirm_archive=True
            )
    assert caught.value is error
    call.assert_awaited_once()
    value._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_upload_bad_local_file_never_checks_out(tmp_path):
    value = client()
    with pytest.raises(ConfigurationError):
        await value.upload_native_video(
            project_id=PROJECT, path=tmp_path / "missing.mp4", rights_confirmed=True
        )
    value._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_acknowledged_upload_handle(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import Mock

    from gflow_cli.errors import NativeMediaMutationUnknownError

    @contextmanager
    def failed_cleanup(path, *, rights_confirmed):
        yield path
        raise ValueError("private cleanup refused")

    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_snapshot.snapshot_video", failed_cleanup
    )
    value = client()
    value._checkout_page = AsyncMock(return_value=object())
    value._checkin_page = Mock()
    call = AsyncMock(return_value=(MEDIA, "private caption"))
    monkeypatch.setattr(
        "gflow_cli.api.transports.migrated_video_upload._upload_video_snapshot", call
    )
    with pytest.raises(NativeMediaMutationUnknownError) as caught:
        await value.upload_native_video(
            project_id=PROJECT, path=tmp_path / "one.mp4", rights_confirmed=True
        )
    assert caught.value.known_media_ids == (MEDIA,)
    assert caught.value.retryable is False
    assert "private" not in str(caught.value)
    call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "archive"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_outer_client_teardown_preserves_known_media(
    tmp_path, monkeypatch, operation, cancel
):
    import asyncio

    from gflow_cli.errors import NativeMediaMutationUnknownError
    from gflow_cli.services import native_media

    failure = asyncio.CancelledError() if cancel else OSError("private teardown detail")

    class ClosingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise failure

        async def _upload_native_video_snapshot(self, project, private):
            return {"media_id": MEDIA, "project_id": PROJECT}

        async def archive_native_media(self, **kwargs):
            return {"archived_media_ids": [MEDIA], "project_id": PROJECT}

    monkeypatch.setattr(native_media, "FlowApiClient", lambda **kwargs: ClosingClient())
    expected = asyncio.CancelledError if cancel else NativeMediaMutationUnknownError
    with pytest.raises(expected) as caught:
        if operation == "upload":
            await native_media.upload_private_snapshot("fixture", PROJECT, tmp_path / "private.mp4")
        else:
            await native_media.archive_media("fixture", PROJECT, (MEDIA,))
    typed = vars(caught.value)["gflow_native_media_unknown"] if cancel else caught.value
    assert typed.known_media_ids == (MEDIA,) and typed.retryable is False
    assert typed.operation == operation
    assert "private" not in str(typed)


@pytest.mark.asyncio
async def test_sdk_checkin_failure_preserves_upload_handle(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from gflow_cli.errors import NativeMediaMutationUnknownError

    value = client()
    value._checkout_page = AsyncMock(return_value=object())
    value._checkin_page = Mock(side_effect=OSError("private checkin detail"))
    monkeypatch.setattr(
        "gflow_cli.api.transports.migrated_video_upload._upload_video_snapshot",
        AsyncMock(return_value=(MEDIA, "caption")),
    )
    source = tmp_path / "one.mp4"
    source.write_bytes(b"\x00\x00\x00\x0cftypisom")
    with pytest.raises(NativeMediaMutationUnknownError) as caught:
        await value.upload_native_video(project_id=PROJECT, path=source, rights_confirmed=True)
    assert caught.value.known_media_ids == (MEDIA,)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_primary_transport_unknown_survives_secondary_checkin(tmp_path, monkeypatch, cancel):
    import asyncio
    from unittest.mock import Mock

    from gflow_cli.errors import NativeMediaMutationUnknownError

    typed = NativeMediaMutationUnknownError(
        operation="upload", phase="response", project_id=PROJECT, known_media_ids=(MEDIA,)
    )
    primary = asyncio.CancelledError() if cancel else typed
    if cancel:
        vars(primary)["gflow_native_media_unknown"] = typed
    value = client()
    value._checkout_page = AsyncMock(return_value=object())
    value._checkin_page = Mock(side_effect=OSError("private secondary checkin"))
    call = AsyncMock(side_effect=primary)
    monkeypatch.setattr(
        "gflow_cli.api.transports.migrated_video_upload._upload_video_snapshot", call
    )
    source = tmp_path / "one.mp4"
    source.write_bytes(b"\x00\x00\x00\x0cftypisom")
    with pytest.raises(type(primary)) as caught:
        await value.upload_native_video(project_id=PROJECT, path=source, rights_confirmed=True)
    assert caught.value is primary
    recovered = vars(caught.value)["gflow_native_media_unknown"] if cancel else caught.value
    assert recovered.known_media_ids == (MEDIA,)
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_primary_archive_unknown_survives_secondary_client_close(monkeypatch):
    from gflow_cli.errors import NativeMediaMutationUnknownError
    from gflow_cli.services import native_media

    primary = NativeMediaMutationUnknownError(
        operation="archive", phase="response", project_id=PROJECT, known_media_ids=(MEDIA,)
    )

    class ClosingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise OSError("private client close")

        async def archive_native_media(self, **kwargs):
            raise primary

    monkeypatch.setattr(native_media, "FlowApiClient", lambda **kwargs: ClosingClient())
    with pytest.raises(NativeMediaMutationUnknownError) as caught:
        await native_media.archive_media("fixture", PROJECT, (MEDIA,))
    assert caught.value is primary and caught.value.known_media_ids == (MEDIA,)


@pytest.mark.asyncio
async def test_valid_video_downstream_value_error_is_not_a_file_validation_error(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    value = client()
    value._checkout_page = AsyncMock(return_value=object())
    value._checkin_page = Mock()
    error = ValueError("Video rights dialog changed; confirm in the browser")
    call = AsyncMock(side_effect=error)
    monkeypatch.setattr(
        "gflow_cli.api.transports.migrated_video_upload._upload_video_snapshot", call
    )
    path = tmp_path / "valid.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    with pytest.raises(ValueError) as caught:
        await value.upload_native_video(project_id=PROJECT, path=path, rights_confirmed=True)
    assert caught.value is error
    call.assert_awaited_once()
    assert not call.call_args.args[2].exists()
    value._checkin_page.assert_called_once()
