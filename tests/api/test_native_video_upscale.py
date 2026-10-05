"""Native promotion request contract, distinct from download/export."""

from dataclasses import replace

import pytest

from gflow_cli.api.native_video_upscale import (
    new_promotion_started,
    parse_promotion_models,
    promotion_args,
)
from gflow_cli.errors import ConfigurationError

PROJECT = "11111111-1111-4111-8111-111111111111"
MEDIA = "22222222-2222-4222-8222-222222222222"
WORKFLOW = "33333333-3333-4333-8333-333333333333"


@pytest.mark.parametrize(("target", "enum"), [("720p", 1), ("1080p", 2), ("4k", 3)])
def test_promotion_dto_and_source_workflow(target, enum):
    started = new_promotion_started(PROJECT, MEDIA, WORKFLOW, target)
    args = promotion_args(
        started, model_key="native-upsample", aspect="16:9", resolution=target, token="test-token"
    )
    row = args[0][0]
    assert row[0] == [None, MEDIA]
    assert row[2] == 2 and row[6] == enum and row[31] == "native-upsample"
    assert row[3] is None  # numeric seed is not the assignment seed
    assert row[4] == [None, WORKFLOW, None, None, started.media_seeds[0]]
    assert started.workflow_ids == (WORKFLOW,)
    assert args[1][5] == PROJECT and args[1][10] == ["test-token", 1]


@pytest.mark.parametrize("target", ["360p", "2k", "4K", "gif", None])
def test_unsupported_promotion_target(target):
    with pytest.raises(ConfigurationError):
        promotion_args(
            new_promotion_started(PROJECT, MEDIA, WORKFLOW),
            model_key="native",
            aspect="16:9",
            resolution=target,
            token="test",
        )


def test_assignment_tampering_refused():
    started = new_promotion_started(PROJECT, MEDIA, WORKFLOW)
    with pytest.raises(ConfigurationError):
        promotion_args(
            replace(started, media_ids=(MEDIA,)),
            model_key="native",
            aspect="16:9",
            resolution="720p",
            token="test",
        )


def fixture_models(task=21, resolution=1, tier=2):
    usage = [None] * 25
    usage[0] = "native-upsample"
    usage[4] = [[tier, [[None, 5]]]]
    usage[7] = [[[[task]]]]
    usage[12] = [[2, 1]]
    usage[23] = [[resolution]]
    family = ["Upsample", [usage], None, "family"]
    return [[None, None, None, None, [family]]]


@pytest.mark.parametrize(
    ("target", "task", "enum"), [("720p", 21, 1), ("1080p", 15, 2), ("4k", 16, 3)]
)
def test_promotion_models_require_task_target_and_tier(target, task, enum):
    rows = parse_promotion_models(fixture_models(task, enum), tier=2, resolution=target)
    assert rows[0]["model_key"] == "native-upsample"
    assert rows[0]["credits"] == 5
    assert rows[0]["target_resolution"] == target
    assert parse_promotion_models(fixture_models(task, enum), tier=1, resolution=target) == []
    assert parse_promotion_models(fixture_models(14, enum), tier=2, resolution=target) == []
    assert parse_promotion_models(fixture_models(task, 99), tier=2, resolution=target) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "bad-aspect", "missing-model"])
async def test_preflight_rejects_before_token(monkeypatch, kind):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import gflow_cli.api.native_video_upscale as module

    client = AsyncMock()
    client._checkin_page = Mock()
    source = SimpleNamespace(
        kind="image" if kind == "image" else "video",
        width=640,
        height=640 if kind == "bad-aspect" else 360,
        workflow_id=WORKFLOW,
    )
    monkeypatch.setattr(module, "read_promotion_source", AsyncMock(return_value=source))

    async def metadata(page, rpc, *args):
        return (
            [None, None, None, 2]
            if rpc == "nzlxg"
            else fixture_models(14 if kind == "missing-model" else 15, 2)
        )

    monkeypatch.setattr(module, "_read_native", metadata)
    mint = AsyncMock(return_value="token")
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", mint)
    with pytest.raises(ConfigurationError):
        await module.upscale_native_video(client, project_id=PROJECT, media_id=MEDIA)
    mint.assert_not_awaited()
    client._checkin_page.assert_called_once()


@pytest.mark.asyncio
async def test_single_dispatch_unknown_preserves_existing_workflow(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import gflow_cli.api.native_video_upscale as module

    client = AsyncMock()
    client._checkin_page = Mock()
    monkeypatch.setattr(
        module,
        "read_promotion_source",
        AsyncMock(
            return_value=SimpleNamespace(kind="video", width=640, height=360, workflow_id=WORKFLOW)
        ),
    )

    async def metadata(page, rpc, *args):
        return [None, None, None, 2] if rpc == "nzlxg" else fixture_models(15, 2)

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="token"))
    events = []

    async def checkpoint(started):
        events.append(("checkpoint", started))

    async def fail(*args):
        events.append(("dispatch", None))
        raise TimeoutError

    client._checkout_page.return_value.evaluate.side_effect = fail
    with pytest.raises(module.NativeVideoUpscaleUnknownError) as caught:
        await module.upscale_native_video(
            client, project_id=PROJECT, media_id=MEDIA, on_started=checkpoint
        )
    assert [x[0] for x in events] == ["checkpoint", "dispatch"]
    assert caught.value.to_problem_details()["workflow_ids"] == [WORKFLOW]
    assert client._checkout_page.return_value.evaluate.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_promotion_acknowledgement_exact_identity(monkeypatch, valid):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import gflow_cli.api.native_video_upscale as module

    client = AsyncMock()
    client._checkin_page = Mock()
    monkeypatch.setattr(
        module,
        "read_promotion_source",
        AsyncMock(
            return_value=SimpleNamespace(kind="video", width=640, height=360, workflow_id=WORKFLOW)
        ),
    )

    async def metadata(page, rpc, *args):
        return [None, None, None, 2] if rpc == "nzlxg" else fixture_models(15, 2)

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="token"))
    assigned = {}

    async def checkpoint(started):
        assigned["started"] = started

    client._checkout_page.return_value.evaluate.return_value = {"status": 200, "text": "response"}
    monkeypatch.setattr(module, "_submit_refusal", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "rpc_errors", lambda *args: [])

    def frames(*args):
        started = assigned["started"]
        return [
            (
                module.RPC,
                [None, None, None, [[started.media_ids[0], PROJECT, WORKFLOW if valid else MEDIA]]],
            )
        ]

    monkeypatch.setattr(module, "parse_frames", frames)
    if valid:
        result = await module.upscale_native_video(
            client, project_id=PROJECT, media_id=MEDIA, on_started=checkpoint
        )
        assert result == assigned["started"]
    else:
        with pytest.raises(module.NativeVideoUpscaleUnknownError):
            await module.upscale_native_video(
                client, project_id=PROJECT, media_id=MEDIA, on_started=checkpoint
            )
    assert client._checkout_page.return_value.evaluate.await_count == 1


@pytest.mark.parametrize("fault", ["identity", "image-arm", "audio-arm", "dimensions"])
def test_fresh_promotion_source_rejects_contradictions(monkeypatch, fault):
    import gflow_cli.api.native_video_upscale as module

    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *args: {"media": [{"media_id": MEDIA, "workflow_id": WORKFLOW, "kind": "video"}]},
    )
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *args: [
            {
                "workflow_id": WORKFLOW,
                "project_id": PROJECT,
                "archived": False,
                "batch_media_ids": [MEDIA],
            }
        ],
    )
    row = [MEDIA, PROJECT, WORKFLOW, None, None, None, None, [None, [640, 360]], None, None, None]
    if fault == "identity":
        row[2] = MEDIA
    if fault == "image-arm":
        row[6] = []
    if fault == "audio-arm":
        row[10] = []
    if fault == "dimensions":
        row[7] = [None, [True, 360]]
    with pytest.raises(ValueError):
        module.promotion_source([], row, project=PROJECT, media=MEDIA)


@pytest.mark.parametrize("fault", ["missing", "archived", "duplicate", "foreign", "nonmember"])
def test_promotion_destination_must_be_active_unique_owned(monkeypatch, fault):
    import gflow_cli.api.native_video_upscale as module

    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *args: {"media": [{"media_id": MEDIA, "workflow_id": WORKFLOW, "kind": "video"}]},
    )
    workflow = {
        "workflow_id": WORKFLOW,
        "project_id": PROJECT,
        "archived": False,
        "batch_media_ids": [MEDIA],
    }
    rows = [workflow]
    if fault == "missing":
        rows = []
    if fault == "archived":
        workflow["archived"] = True
    if fault == "duplicate":
        rows = [workflow, workflow]
    if fault == "foreign":
        workflow["project_id"] = MEDIA
    if fault == "nonmember":
        workflow["batch_media_ids"] = []
    monkeypatch.setattr(module, "project_media", lambda *args: rows)
    metadata = [MEDIA, PROJECT, WORKFLOW, None, None, None, None, [None, [640, 360]]]
    with pytest.raises(ValueError, match="workflow"):
        module.promotion_source([], metadata, project=PROJECT, media=MEDIA)
