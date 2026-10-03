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
        "missing_primary",
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
    elif mutation == "missing_primary":
        payload[1][0][3][4] = E
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
