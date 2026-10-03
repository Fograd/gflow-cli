"""Character reference ownership must be joined before fresh URL reads."""

from copy import deepcopy

import pytest

from gflow_cli.api.transports.character_details import character_image_handles

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
W2 = "55555555-5555-4555-8555-555555555555"
M2 = "66666666-6666-4666-8666-666666666666"


def fixture():
    entity = [P, E, None, [1, "Guide", [[[W2], [W]], None, "Notes"]], M]
    workflows = [
        [W, None, None, ["Portrait", None, False, None, M], P, E],
        [W2, None, None, ["Body", None, False, None, M2], P, E],
    ]
    media = [
        [M, P, W, None, None, None, [None, None, [32, 32]]],
        [M2, P, W2, None, None, None, [None, None, [32, 48]]],
    ]
    return [None, workflows, media, None, None, [entity]]


def test_order_follows_entity_not_timeline():
    result = character_image_handles(fixture(), project_id=P, entity_id=E)
    assert result["references"] == [
        {"workflow_id": W2, "media_id": M2},
        {"workflow_id": W, "media_id": M},
    ]
    assert result["thumbnail"] == {"workflow_id": W, "media_id": M}


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_project",
        "foreign_parent",
        "duplicate_workflow",
        "duplicate_entity",
        "wrong_kind",
        "duplicate_ref",
    ],
)
def test_ambiguous_or_unowned_relationship_refuses(mutation):
    payload = deepcopy(fixture())
    if mutation == "foreign_project":
        payload[1][0][4] = E
    elif mutation == "foreign_parent":
        payload[1][0][5] = P
    elif mutation == "duplicate_workflow":
        payload[1].append(deepcopy(payload[1][0]))
    elif mutation == "duplicate_entity":
        payload[5].append(deepcopy(payload[5][0]))
    elif mutation == "wrong_kind":
        payload[2][0][6] = None
    else:
        payload[5][0][3][2][0].append([W])
    with pytest.raises(ValueError):
        character_image_handles(payload, project_id=P, entity_id=E)


def test_unprojected_thumbnail_is_unresolved_not_reference_zero():
    payload = fixture()
    payload[5][0][4] = P
    with pytest.raises(ValueError, match="thumbnail"):
        character_image_handles(payload, project_id=P, entity_id=E)


@pytest.mark.asyncio
async def test_fresh_detail_respects_reference_order_and_reuses_thumbnail(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports import character_details as module
    from gflow_cli.api.transports.native_asset_lookup import NativeAsset

    snapshot = AsyncMock(return_value=fixture())
    rpc = AsyncMock(side_effect=[["body"], ["portrait"]])
    monkeypatch.setattr(module, "read_project_payload", snapshot)
    monkeypatch.setattr(module, "native_rpc", rpc)

    def decode(payload, **kwargs):
        return NativeAsset(
            kwargs["media_id"],
            P,
            kwargs["workflow_id"],
            "image",
            "https://flow-content.google/image/" + payload[0],
            32,
            32,
        )

    monkeypatch.setattr(module, "existing_asset", decode)
    result = await module.lookup_character(None, project_id=P, name="Guide")
    assert [r["media_id"] for r in result["image_references"]] == [M2, M]
    assert result["thumbnail_url"].endswith("/portrait")
    assert snapshot.await_count == 1
    assert [c.args[2] for c in rpc.await_args_list] == [[M2], [M]]
    assert all(c.kwargs["require_single"] is True for c in rpc.await_args_list)


THUMBNAIL = "77777777-7777-4777-8777-777777777777"
THUMBNAIL_WORKFLOW = "88888888-8888-4888-8888-888888888888"


def nonprojected_thumbnail_fixture():
    value = fixture()
    value[5][0][4] = THUMBNAIL
    value[1].append(
        [THUMBNAIL_WORKFLOW, None, None, ["Thumbnail", None, False, None, THUMBNAIL], P, E]
    )
    return value


def image_detail(media, workflow):
    return [
        media,
        P,
        workflow,
        None,
        None,
        None,
        [None, [None, None, None, "https://flow-content.google/image/" + media], [32, 32]],
        None,
        None,
        None,
        None,
    ]


@pytest.mark.asyncio
async def test_nonprojected_owned_thumbnail_is_verified_before_url_disclosure(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports import character_details as module

    snapshot = AsyncMock(return_value=nonprojected_thumbnail_fixture())
    rpc = AsyncMock(
        side_effect=[
            image_detail(M2, W2),
            image_detail(M, W),
            image_detail(THUMBNAIL, THUMBNAIL_WORKFLOW),
        ]
    )
    monkeypatch.setattr(module, "read_project_payload", snapshot)
    monkeypatch.setattr(module, "native_rpc", rpc)
    result = await module.lookup_character(None, project_id=P, entity_id=E)
    assert result["thumbnail_url"].endswith("/" + THUMBNAIL)
    assert [row["media_id"] for row in result["image_references"]] == [M2, M]
    snapshot.assert_awaited_once_with(None, P)
    assert [call.args[2] for call in rpc.await_args_list] == [[M2], [M], [THUMBNAIL]]
    assert all(call.kwargs["require_single"] is True for call in rpc.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "foreign_project",
        "foreign_workflow_project",
        "unknown_workflow",
        "foreign_parent",
        "archived",
        "duplicate",
        "missing",
        "wrong_media",
        "mixed_kind",
        "wrong_kind",
    ],
)
async def test_nonprojected_thumbnail_refuses_unproven_parent_or_media(monkeypatch, fault):
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports import character_details as module

    value = nonprojected_thumbnail_fixture()
    row = image_detail(THUMBNAIL, THUMBNAIL_WORKFLOW)
    parent = value[1][-1]
    if fault == "foreign_project":
        row[1] = E
    elif fault == "foreign_workflow_project":
        parent[4] = E
    elif fault == "unknown_workflow":
        row[2] = E
    elif fault == "foreign_parent":
        parent[5] = P
    elif fault == "archived":
        parent[3][2] = True
    elif fault == "duplicate":
        value[1].append(deepcopy(parent))
    elif fault == "missing":
        value[1].pop()
    elif fault == "wrong_media":
        row[0] = M2
    elif fault == "mixed_kind":
        row[10] = [[None, None, None, "https://flow-content.google/audio/synthetic"]]
    else:
        row[6] = None
        row[7] = [
            None,
            [32, 32],
            None,
            None,
            [None, None, "https://flow-content.google/video/synthetic"],
        ]
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=value))
    monkeypatch.setattr(
        module, "native_rpc", AsyncMock(side_effect=[image_detail(M2, W2), image_detail(M, W), row])
    )
    with pytest.raises(ValueError):
        await module.lookup_character(None, project_id=P, entity_id=E)


@pytest.mark.parametrize("count,refuses", [(15, False), (16, True)])
def test_nonprojected_thumbnail_consumes_one_of_sixteen_reads(count, refuses):
    from uuid import UUID

    value = nonprojected_thumbnail_fixture()
    value[1] = []
    value[2] = []
    references = []
    for index in range(count):
        workflow = str(UUID(int=100 + index))
        media = str(UUID(int=200 + index))
        references.append([workflow])
        value[1].append([workflow, None, None, ["Owned", None, False, None, media], P, E])
    value[5][0][3][2][0] = references
    if refuses:
        with pytest.raises(ValueError, match="budget"):
            character_image_handles(value, project_id=P, entity_id=E)
    else:
        result = character_image_handles(value, project_id=P, entity_id=E)
        assert len(result["references"]) == count
        assert result["thumbnail"] == {"workflow_id": None, "media_id": THUMBNAIL}
