"""Current existing-media metadata keeps native identities distinct from status."""

from copy import deepcopy

import pytest

from gflow_cli.api.transports.native_asset_lookup import existing_asset

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
IMAGE = "https://flow-content.google/image/owned?Expires=1&KeyName=test&Signature=test"
VIDEO = "https://flow-content.google/video/owned?Expires=1&KeyName=test&Signature=test"


def row(kind="image", uploaded=True):
    value = [M, P, W, None, None, [None] * 14, None, None]
    if kind == "image":
        arm = [None, None, [48, 32]]
        if uploaded:
            arm[1] = [None, None, None, IMAGE, 100, None, "image/png"]
        else:
            arm[0] = [None] * 14
            arm[0][13] = IMAGE
        value[6] = arm
    else:
        arm = [None, [48, 32], None, None, None]
        if uploaded:
            arm[4] = ["video/mp4", 100, VIDEO]
        else:
            arm[0] = [None] * 9
            arm[0][8] = VIDEO
        value[7] = arm
    return value


def decode(value, kind="image"):
    return existing_asset(value, project_id=P, media_id=M, workflow_id=W, kind=kind)


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("uploaded", [True, False])
def test_exact_current_identities_and_media_arm(kind, uploaded):
    result = decode(row(kind, uploaded), kind)
    assert (result.media_id, result.project_id, result.workflow_id) == (M, P, W)
    assert result.kind == kind
    assert result.url == (IMAGE if kind == "image" else VIDEO)
    assert (result.width, result.height) == (48, 32)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_unrelated_identity(index):
    value = row()
    value[index] = "44444444-4444-4444-8444-444444444444"
    with pytest.raises(ValueError):
        decode(value)


def test_transposed_historical_order_is_refused():
    value = row()
    value[0], value[2] = value[2], value[0]
    with pytest.raises(ValueError):
        decode(value)


def test_ambiguous_union():
    value = row()
    value[7] = row("video")[7]
    with pytest.raises(ValueError):
        decode(value)


def test_audio_union_is_refused():
    value = row()
    value.extend([None, None, [["audio"]]])
    with pytest.raises(ValueError):
        decode(value)


def test_missing_original_never_uses_thumbnail():
    value = row()
    value[6][1][3] = None
    value[5][10] = IMAGE
    with pytest.raises(ValueError):
        decode(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://flow-content.google/image/a",
        "https://example.com/image/a",
        "https://flow-content.google:8443/image/a",
        "https://user:pass@flow-content.google/image/a",
        "https://flow-content.google/video/a",
    ],
)
def test_untrusted_or_wrong_kind_url(url):
    value = row()
    value[6][1][3] = url
    with pytest.raises(ValueError):
        decode(value)


@pytest.mark.parametrize("dims", [[True, 32], [0, 32], [-1, 32], ["48", 32], [48]])
def test_unavailable_dimensions(dims):
    value = row()
    value[6][2] = dims
    with pytest.raises(ValueError):
        decode(value)


def test_both_original_arms_are_ambiguous():
    value = row()
    value[6][0] = deepcopy(row(uploaded=False)[6][0])
    with pytest.raises(ValueError):
        decode(value)


@pytest.mark.asyncio
async def test_strict_rpc_refuses_duplicate_matching_frames(monkeypatch):
    import json

    from gflow_cli.api.transports import migrated_rpc

    class Page:
        async def evaluate(self, *args):
            frame = ["wrb.fr", "as29s", json.dumps(row()), None, None, None, "generic"]
            return {"status": 200, "text": json.dumps([frame, frame])}

    with pytest.raises(ValueError, match="exactly one"):
        await migrated_rpc.native_rpc(Page(), "as29s", [M], "/project/" + P, require_single=True)


@pytest.mark.asyncio
async def test_strict_rpc_selects_only_expected_rpc(monkeypatch):
    import json

    from gflow_cli.api.transports import migrated_rpc

    expected = row()

    class Page:
        async def evaluate(self, *args):
            return {
                "status": 200,
                "text": json.dumps(
                    [
                        ["wrb.fr", "other", "[]", None, None, None, "generic"],
                        ["wrb.fr", "as29s", json.dumps(expected), None, None, None, "generic"],
                    ]
                ),
            }

    assert (
        await migrated_rpc.native_rpc(Page(), "as29s", [M], "/project/" + P, require_single=True)
        == expected
    )


@pytest.mark.asyncio
async def test_lookup_correlates_fresh_snapshot_before_detail(monkeypatch):
    from gflow_cli.api.transports import native_asset_lookup as module

    calls = []

    async def project(page, project_id):
        calls.append("snapshot")
        return [None, [], [row()]]

    async def rpc(page, name, args, source_path, *, require_single):
        assert calls == ["snapshot"]
        assert (name, args, source_path, require_single) == ("as29s", [M], "/project/" + P, True)
        calls.append("detail")
        return row()

    monkeypatch.setattr(module, "read_project_payload", project)
    monkeypatch.setattr(module, "native_rpc", rpc)
    result = await module.lookup_asset(object(), project_id=P, media_id=M)
    assert result.media_id == M and calls == ["snapshot", "detail"]


@pytest.mark.asyncio
async def test_unresolved_snapshot_never_dispatches_detail(monkeypatch):
    from gflow_cli.api.transports import native_asset_lookup as module

    async def project(page, project_id):
        return [None, [], []]

    async def rpc(*args, **kwargs):
        pytest.fail("Unresolved inventory must not dispatch detail")

    monkeypatch.setattr(module, "read_project_payload", project)
    monkeypatch.setattr(module, "native_rpc", rpc)
    with pytest.raises(ValueError, match="unresolved"):
        await module.lookup_asset(object(), project_id=P, media_id=M)


AUDIO = "https://audio.example.test/playback?token=private"


def audio_row():
    value = [M, P, W, None, None, [None] * 14, None, None, None, None, [[None] * 8]]
    value[10][0][3] = AUDIO
    return value


@pytest.mark.asyncio
async def test_generic_audio_lookup_without_saved_visibility(monkeypatch):
    from gflow_cli.api.transports import native_asset_lookup as module

    async def project(page, project_id):
        return [None, [[W, None, None, ["audio", None, False, None, M], P]], [audio_row()]]

    async def rpc(page, name, args, source_path, *, require_single):
        assert (name, args, source_path, require_single) == ("as29s", [M], "/project/" + P, True)
        return audio_row()

    monkeypatch.setattr(module, "read_project_payload", project)
    monkeypatch.setattr(module, "native_rpc", rpc)
    result = await module.lookup_asset(object(), project_id=P, media_id=M)
    assert result.kind == "audio" and result.url == AUDIO
    assert result.width is None and result.height is None
    assert AUDIO not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["foreign", "archived", "duplicate", "absent"])
async def test_audio_requires_unique_active_owned_workflow(monkeypatch, variant):
    from gflow_cli.api.transports import native_asset_lookup as module

    workflow = [W, None, None, ["audio", None, False, None, M], P]
    if variant == "foreign":
        workflow[4] = M
    elif variant == "archived":
        workflow[3][2] = True
    rows = (
        []
        if variant == "absent"
        else [workflow, workflow]
        if variant == "duplicate"
        else [workflow]
    )

    async def project(page, project_id):
        return [None, rows, [audio_row()]]

    async def rpc(*args, **kwargs):
        pytest.fail("Unowned audio must refuse before GetMedia")

    monkeypatch.setattr(module, "read_project_payload", project)
    monkeypatch.setattr(module, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await module.lookup_asset(object(), project_id=P, media_id=M)


@pytest.mark.asyncio
async def test_audio_download_refuses_before_network_or_directory(tmp_path):
    from gflow_cli.api.transports.native_asset_download import download_asset
    from gflow_cli.api.transports.native_asset_lookup import NativeAudioAsset

    asset = NativeAudioAsset(M, P, W, AUDIO)
    target = tmp_path / "never-created"
    with pytest.raises(ValueError, match="audio.*metadata only"):
        await download_asset(asset, target)
    assert not target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["identity", "mixed", "missing", "unsafe"])
async def test_generic_audio_detail_refuses_inconsistent_or_unavailable_playback(
    monkeypatch, variant
):
    from gflow_cli.api.transports import native_asset_lookup as module

    async def project(page, project_id):
        return [None, [[W, None, None, ["audio", None, False, None, M], P]], [audio_row()]]

    async def rpc(*args, **kwargs):
        value = audio_row()
        if variant == "identity":
            value[2] = M
        elif variant == "mixed":
            value[6] = row()[6]
        elif variant == "missing":
            value[10][0][3] = None
        else:
            value[10][0][3] = "https://user:password@audio.example.test/sample"
        return value

    monkeypatch.setattr(module, "read_project_payload", project)
    monkeypatch.setattr(module, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await module.lookup_asset(object(), project_id=P, media_id=M)
