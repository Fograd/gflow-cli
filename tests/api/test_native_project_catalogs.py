"""Cross-project catalogs are typed observations, not deletion authority."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs as module
from gflow_cli.errors import ConfigurationError, WireFormatError
from tests.api.transports.test_character_details import E, P, fixture

P2 = "99999999-9999-4999-8999-999999999999"


def test_measured_null_empty_catalog_is_observation_not_mutation_authority():
    from gflow_cli.api.transports.migrated_resources import project_media

    payload = [None, None, None, [], None, None, None, []]
    result = module.project_catalog_snapshot(payload, P)
    assert result["counts"] == {"media": 0, "workflows": 0, "characters": 0, "user_voices": 0}
    assert result["complete"] is None
    assert payload[1] is payload[2] is None
    with pytest.raises(ValueError, match="unsupported shape"):
        project_media(payload, P)


@pytest.mark.parametrize("index,value", [(1, "bad"), (2, "bad"), (3, None), (5, "bad"), (7, None)])
def test_unknown_null_catalog_variants_still_refuse(index, value):
    payload = [None, None, None, [], None, None, None, []]
    payload[index] = value
    with pytest.raises(ValueError):
        module.project_catalog_snapshot(payload, P)


def test_one_payload_projects_typed_catalogs_without_urls():
    payload = fixture()
    payload[2][0][3] = "SIGNED_URL"
    payload[1][0][1] = "SIGNED_URL"
    result = module.project_catalog_snapshot(payload, P)
    assert result["counts"] == {"media": 2, "workflows": 2, "characters": 1, "user_voices": 0}
    assert result["complete"] is None and result["project_id"] == P
    assert "SIGNED_URL" not in repr(result)
    assert result["characters"][0]["entity_id"] == E


@pytest.mark.parametrize(
    "mutation", ["duplicate_workflow", "duplicate_character", "foreign_workflow", "foreign_media"]
)
def test_catalog_ambiguity_and_ownership_refuse(mutation):
    payload = fixture()
    if mutation == "duplicate_workflow":
        payload[1].append(deepcopy(payload[1][0]))
    elif mutation == "duplicate_character":
        payload[5].append(deepcopy(payload[5][0]))
    elif mutation == "foreign_workflow":
        payload[1][0][4] = E
    else:
        payload[2][0][1] = E
    with pytest.raises(ValueError):
        module.project_catalog_snapshot(payload, P)


@pytest.mark.asyncio
async def test_catalog_cap_preserves_unread_project_ids_and_next_cursor(monkeypatch):
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(
        module,
        "list_projects",
        AsyncMock(
            return_value={
                "projects": [{"project_id": P, "name": "One"}, {"project_id": P2, "name": "Two"}],
                "next_cursor": "later",
            }
        ),
    )
    read = AsyncMock(return_value=fixture())
    monkeypatch.setattr(module, "read_project_payload", read)
    result = await module.projects_snapshot(client, include_catalogs=True, max_projects=1)
    assert result["next_cursor"] == "later"
    assert result["pending_project_ids"] == [P2]
    assert result["catalog_projects_read"] == 1 and result["catalogs_capped"] is True
    assert result["catalog_counts"] == {
        "media": 2,
        "workflows": 2,
        "characters": 1,
        "user_voices": 0,
    }
    assert len(result["project_catalogs"]) == 1 and result["complete"] is None
    read.assert_awaited_once_with("page", P, require_request_project=True, allow_empty_catalog=True)
    client._checkout_page.assert_awaited_once()
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"include_catalogs": 1},
        {"max_projects": 1},
        {"include_catalogs": True, "max_projects": True},
        {"include_catalogs": True, "max_projects": 0},
        {"include_catalogs": True, "max_projects": 21},
    ],
)
async def test_invalid_catalog_controls_precede_checkout(kwargs):
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.projects_snapshot(client, **kwargs)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_project_catalog_returns_page_and_no_successful_partial(monkeypatch):
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(
        module,
        "list_projects",
        AsyncMock(
            return_value={"projects": [{"project_id": P, "name": "One"}], "next_cursor": None}
        ),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    with pytest.raises(WireFormatError):
        await module.projects_snapshot(client, include_catalogs=True)
    client._checkin_page.assert_called_once_with("page")


def test_saved_voice_catalog_excludes_native_playback_url():
    payload = fixture()
    audio_id = "77777777-7777-4777-8777-777777777777"
    workflow = "88888888-8888-4888-8888-888888888888"
    metadata = [None] * 10
    metadata[9] = 1
    sample = ["Title", "Soft", None, "SIGNED_PLAYBACK_URL", "charon", None, "Hello"]
    payload[1].append([workflow, None, None, ["Saved voice", None, False, None, audio_id], P, None])
    payload[2].append(
        [audio_id, P, workflow, None, None, metadata, None, None, None, None, [sample]]
    )
    result = module.project_catalog_snapshot(payload, P)
    assert result["counts"]["user_voices"] == 1
    assert result["user_voices"][0]["dialogue"] == "Hello"
    assert "SIGNED_PLAYBACK_URL" not in repr(result)


def test_empty_project_catalogs_keep_unknown_completeness():
    result = module.project_catalog_snapshot([None, [], [], None, None, []], P)
    assert result["counts"] == {"media": 0, "workflows": 0, "characters": 0, "user_voices": 0}
    assert result["complete"] is None


@pytest.mark.asyncio
async def test_catalog_cancellation_releases_page(monkeypatch):
    import asyncio

    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(
        module,
        "list_projects",
        AsyncMock(
            return_value={"projects": [{"project_id": P, "name": "One"}], "next_cursor": None}
        ),
    )
    monkeypatch.setattr(
        module, "read_project_payload", AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await module.projects_snapshot(client, include_catalogs=True)
    client._checkin_page.assert_called_once_with("page")
