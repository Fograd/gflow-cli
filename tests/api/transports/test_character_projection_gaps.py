"""Missing projections require strict reads; contradictions still refuse."""

from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports.character_details import character_image_handles
from tests.api.transports.test_character_details import M2, W2, E, M, P, W, fixture

W3 = "77777777-7777-4777-8777-777777777777"
M3 = "88888888-8888-4888-8888-888888888888"


def test_absent_projection_keeps_owned_workflow_candidate():
    payload = fixture()
    payload[2] = []
    result = character_image_handles(payload, project_id=P, entity_id=E)
    assert result["references"] == [
        {"workflow_id": W2, "media_id": M2},
        {"workflow_id": W, "media_id": M},
    ]


def test_separate_projected_thumbnail_keeps_reference_order():
    payload = fixture()
    payload[5][0][4] = M3
    payload[1].append([W3, None, None, ["Poster", None, False, None, M3], P, E])
    payload[2].append([M3, P, W3, None, None, None, [None, None, [32, 32]]])
    result = character_image_handles(payload, project_id=P, entity_id=E)
    assert [row["media_id"] for row in result["references"]] == [M2, M]
    assert result["thumbnail"] == {"workflow_id": W3, "media_id": M3}


@pytest.mark.parametrize(
    "mutation", ["wrong_kind", "wrong_workflow", "foreign_thumbnail_parent", "archived_thumbnail"]
)
def test_contradictory_projection_refuses(mutation):
    payload = fixture()
    if mutation == "wrong_kind":
        payload[2][0][6] = None
    elif mutation == "wrong_workflow":
        payload[2][0][2] = W2
    else:
        payload[5][0][4] = M3
        payload[1].append(
            [
                W3,
                None,
                None,
                ["Poster", None, mutation == "archived_thumbnail", None, M3],
                P,
                P if mutation == "foreign_thumbnail_parent" else E,
            ]
        )
        payload[2].append([M3, P, W3, None, None, None, [None, None, [32, 32]]])
    with pytest.raises(ValueError):
        character_image_handles(payload, project_id=P, entity_id=E)


@pytest.mark.asyncio
async def test_absent_projection_never_exposes_url_when_strict_media_refuses(monkeypatch):
    from gflow_cli.api.transports import character_details as module

    payload = fixture()
    payload[2] = []
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload))
    rpc = AsyncMock(return_value=["not-typed-media"])
    monkeypatch.setattr(module, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await module.lookup_character(None, project_id=P, entity_id=E)
    rpc.assert_awaited_once_with(None, "as29s", [M2], "/project/" + P, require_single=True)


def test_separate_thumbnail_counts_toward_total_sixteen_read_budget():
    payload = fixture()
    payload[1] = []
    payload[2] = [[M3, P, W3, None, None, None, [None, None, [32, 32]]]]
    refs = []
    for index in range(16):
        workflow = f"10000000-0000-4000-8000-{index:012d}"
        media = f"20000000-0000-4000-8000-{index:012d}"
        refs.append([workflow])
        payload[1].append([workflow, None, None, ["Ref", None, False, None, media], P, E])
    payload[1].append([W3, None, None, ["Poster", None, False, None, M3], P, E])
    payload[5][0][3][2][0] = refs
    payload[5][0][4] = M3
    with pytest.raises(ValueError, match="budget"):
        character_image_handles(payload, project_id=P, entity_id=E)


@pytest.mark.asyncio
async def test_separate_thumbnail_is_strictly_read_without_inserting_reference(monkeypatch):
    from gflow_cli.api.transports import character_details as module
    from gflow_cli.api.transports.native_asset_lookup import NativeAsset

    payload = fixture()
    payload[5][0][4] = M3
    payload[1].append([W3, None, None, ["Poster", None, False, None, M3], P, E])
    payload[2].append([M3, P, W3, None, None, None, [None, None, [32, 32]]])
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload))
    rpc = AsyncMock(return_value=[])
    monkeypatch.setattr(module, "native_rpc", rpc)
    monkeypatch.setattr(
        module,
        "existing_asset",
        lambda data, **kwargs: NativeAsset(
            kwargs["media_id"],
            P,
            kwargs["workflow_id"],
            "image",
            "https://flow-content.google/image/" + kwargs["media_id"],
            32,
            32,
        ),
    )
    result = await module.lookup_character(None, project_id=P, entity_id=E)
    assert [row["media_id"] for row in result["image_references"]] == [M2, M]
    assert result["thumbnail_url"].endswith(M3)
    assert [call.args[2] for call in rpc.await_args_list] == [[M2], [M], [M3]]
    assert all(call.kwargs["require_single"] is True for call in rpc.await_args_list)
