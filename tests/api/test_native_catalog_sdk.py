from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs as module
from gflow_cli.errors import ConfigurationError, WireFormatError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
V = "44444444-4444-4444-8444-444444444444"


def payload():
    image = [M, P, W, "SIGNED_URL", None, [], [None, None, [1024, 1024]]]
    video = [V, P, W, "SIGNED_URL", None, [], None, [None, [1280, 1280, [1]]]]
    return [None, [], [image, video]]


def test_measured_media_arms_dimensions_and_unknown_completeness():
    result = module.parse_media_snapshot(payload(), P)
    assert result["complete"] is None
    assert result["returned_count"] == 2
    assert result["media"] == [
        {
            "media_id": M,
            "project_id": P,
            "workflow_id": W,
            "kind": "image",
            "width": 1024,
            "height": 1024,
        },
        {
            "media_id": V,
            "project_id": P,
            "workflow_id": W,
            "kind": "video",
            "width": 1280,
            "height": 1280,
        },
    ]
    assert "SIGNED_URL" not in str(result)


def test_missing_dims_and_unknown_arms_are_not_guessed():
    data = payload()
    data[2][0][6] = []
    data[2][1][6] = []
    rows = module.parse_media_snapshot(data, P)["media"]
    assert rows[0]["kind"] == "image" and "width" not in rows[0]
    assert rows[1]["kind"] == "unknown"


@pytest.mark.parametrize("change", ["project", "media", "workflow", "duplicate"])
def test_bad_identity_or_duplicates_fail_closed(change):
    data = payload()
    if change == "duplicate":
        data[2].append(data[2][0])
    else:
        data[2][0][{"project": 1, "media": 0, "workflow": 2}[change]] = "bad"
    with pytest.raises(ValueError):
        module.parse_media_snapshot(data, P)


@pytest.mark.asyncio
async def test_projects_validate_cursor_before_checkout():
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.projects_snapshot(client, "x" * 4097)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_returns_page_even_parser_fails(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[None, [], []]))
    result = await module.media_snapshot(client, P)
    assert result["returned_count"] == 0
    client._checkin_page.assert_called_once_with(page)
    client._checkin_page.reset_mock()
    monkeypatch.setattr(
        module, "read_project_payload", AsyncMock(return_value=[None, [], [["bad"]]])
    )
    with pytest.raises(WireFormatError):
        await module.media_snapshot(client, P)
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_labs_override_refuses_without_page():
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="labs.google"), _checkout_page=AsyncMock()
    )
    with pytest.raises(ConfigurationError):
        await module.media_snapshot(client, P)
    client._checkout_page.assert_not_awaited()


@pytest.mark.parametrize("dims", [[True, 1], [-1, 10], [100001, 10], ["1024", 1024], None])
def test_bad_dimensions_are_omitted_without_guess(dims):
    data = payload()
    data[2][0][6][2] = dims
    assert "width" not in module.parse_media_snapshot(data, P)["media"][0]


@pytest.mark.parametrize("data", [None, [], [None, [], None], [None, [], [{}]]])
def test_unrecognized_collection_shape_is_error(data):
    with pytest.raises(ValueError):
        module.parse_media_snapshot(data, P)


@pytest.mark.asyncio
async def test_projects_transports_one_page_and_returns_cursor(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    operation = AsyncMock(
        return_value={"projects": [{"project_id": P, "name": "Name"}], "next_cursor": "opaque"}
    )
    monkeypatch.setattr(module, "list_projects", operation)
    result = await module.projects_snapshot(client, "previous")
    assert result["next_cursor"] == "opaque" and result["returned_count"] == 1
    assert result["complete"] is None
    operation.assert_awaited_once_with(page, "previous")
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_projects_rpc_failure_returns_page_without_retry(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    operation = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(module, "list_projects", operation)
    with pytest.raises(TimeoutError):
        await module.projects_snapshot(client)
    operation.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_media_invalid_project_before_checkout():
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.media_snapshot(client, "bad")
    client._checkout_page.assert_not_awaited()


@pytest.mark.parametrize("competing_kind", [None, "image", "video"])
def test_audio_arm_is_exclusive_and_never_has_image_dimensions(competing_kind):
    row = [M, P, W, None, None, None, None, None, None, None, ["AUDIO_SIGNED_URL"]]
    if competing_kind == "image":
        row[6] = [None, None, [1024, 1024]]
    elif competing_kind == "video":
        row[7] = [None, [1280, 720]]
    result = module.parse_media_snapshot([None, [], [row]], P)
    assert result["media"] == [
        {
            "media_id": M,
            "project_id": P,
            "workflow_id": W,
            "kind": "audio" if competing_kind is None else "unknown",
        }
    ]
    assert "AUDIO_SIGNED_URL" not in str(result)


@pytest.mark.parametrize("foreign", [False, True])
def test_attached_inventory_is_opt_in_and_preserves_origin(foreign):
    row = payload()[2][0]
    if foreign:
        row[1] = V
    row[6] = [None, [None, None, None, "PRIVATE_UPLOAD_URL"], [1024, 1024]]
    data = [None, [], [], [[None, None, None, row]]]
    assert module.parse_media_snapshot(data, P)["media"] == []
    result = module.parse_media_snapshot(data, P, include_attached=True)
    item = result["media"][0]
    assert item["project_id"] == (V if foreign else P)
    assert item["attached_to_project_id"] == P
    assert item["likely_upload"] is True
    assert result["returned_count"] == 1 and result["complete"] is None
    assert "PRIVATE_UPLOAD_URL" not in str(result)


def test_attached_inventory_deduplicates_exact_rows_but_refuses_conflicts():
    data = payload()
    row = data[2][0]
    data.append([[None, None, None, row.copy()]])
    result = module.parse_media_snapshot(data, P, include_attached=True)
    assert result["returned_count"] == 2
    data[3][0][3][6] = [None, None, [2048, 2048]]
    with pytest.raises(ValueError, match="duplicat"):
        module.parse_media_snapshot(data, P, include_attached=True)


@pytest.mark.parametrize("wrapper", [{}, [], [None, None, None, {}]])
def test_attached_inventory_rejects_malformed_wrappers(wrapper):
    with pytest.raises(ValueError):
        module.parse_media_snapshot([None, [], [], [wrapper]], P, include_attached=True)


@pytest.mark.parametrize("uploaded", [None, {}, "not-an-arm", []])
def test_upload_hint_requires_typed_nonempty_exclusive_upload_arm(uploaded):
    data = payload()
    data[2][0][6] = [None, uploaded, [1024, 1024]]
    result = module.parse_media_snapshot(data, P, include_attached=True)
    assert result["media"][0]["likely_upload"] is False


@pytest.mark.asyncio
async def test_read_inventory_includes_foreign_attachment_without_widening_default(monkeypatch):
    row = payload()[2][0]
    row[1] = V
    data = [None, [], [], [[None, None, None, row]], [], []]
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=object()),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=data))
    result = await module.media_snapshot(client, P)
    assert result["media"][0]["project_id"] == V
    assert result["media"][0]["attached_to_project_id"] == P
    assert module.parse_media_snapshot(data, P)["media"] == []
    catalog = module.project_catalog_snapshot(data, P)
    assert catalog["counts"]["media"] == 1 and catalog["counts"]["workflows"] == 0


@pytest.mark.parametrize("generated", [None, ["generated-source"]])
def test_video_upload_hint_requires_exclusive_uploaded_video(generated):
    data = payload()
    data[2][1][7] = [generated, [1280, 720], None, None, ["uploaded-source"]]
    result = module.parse_media_snapshot(data, P, include_attached=True)
    assert result["media"][1]["likely_upload"] is (generated is None)


def test_inventory_deduplicates_repeated_main_rows_without_widening_strict_default():
    data = payload()
    data[2].append(data[2][0].copy())
    assert module.parse_media_snapshot(data, P, include_attached=True)["returned_count"] == 2
    with pytest.raises(ValueError, match="duplicat"):
        module.parse_media_snapshot(data, P)


@pytest.mark.parametrize("seconds", [1700000000, "1700000000"])
def test_inventory_creation_time_uses_source_seconds_and_nanos(seconds):
    data = payload()
    data[2][0][5] = [[seconds, 123456789]]
    item = module.parse_media_snapshot(data, P, include_attached=True)["media"][0]
    assert item["created_time"] == "2023-11-14T22:13:20.123456789Z"


@pytest.mark.parametrize(
    "stamp", [None, [], [True], ["bad"], [-1], [253402300800], [1, True], [1, -1], [1, 1000000000]]
)
def test_inventory_invalid_creation_time_is_omitted(stamp):
    data = payload()
    data[2][0][5] = [stamp]
    item = module.parse_media_snapshot(data, P, include_attached=True)["media"][0]
    assert "created_time" not in item


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ([0], "1970-01-01T00:00:00Z"),
        ([0, 1], "1970-01-01T00:00:00.000000001Z"),
        ([0, 100000000], "1970-01-01T00:00:00.1Z"),
    ],
)
def test_inventory_creation_time_preserves_zero_epoch_and_subseconds(stamp, expected):
    data = payload()
    data[2][0][5] = [stamp]
    item = module.parse_media_snapshot(data, P, include_attached=True)["media"][0]
    assert item["created_time"] == expected


@pytest.mark.parametrize("fault", [None, "name", "type", "detail-id", "sample-name", "sample-url"])
def test_inventory_skips_only_verified_bundled_preset_wrapper(fault):
    detail = (
        ["enceladus"]
        + [None] * 9
        + [
            [
                [
                    "Enceladus",
                    "Male, breathy, low pitch",
                    True,
                    "https://gstatic.com/aitestkitchen/voices/samples/Enceladus.wav",
                ]
            ]
        ]
    )
    wrapper = ["enceladus", 3, "Enceladus", detail]
    if fault == "name":
        wrapper[2] = "UnrecognizedPreset"
    elif fault == "type":
        wrapper[1] = 2
    elif fault == "detail-id":
        detail[0] = "other"
    elif fault == "sample-name":
        detail[10][0][0] = "Other"
    elif fault == "sample-url":
        detail[10][0][3] = "https://example.org/sample.wav"
    data = [None, [], [], [wrapper]]
    if fault is None:
        assert module.parse_media_snapshot(data, P, include_attached=True)["media"] == []
    else:
        with pytest.raises(ValueError):
            module.parse_media_snapshot(data, P, include_attached=True)
