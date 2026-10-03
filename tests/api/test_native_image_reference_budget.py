from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_image_references as subject
from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
W1 = "33333333-3333-4333-8333-333333333333"
W2 = "44444444-4444-4444-8444-444444444444"
M1 = "55555555-5555-4555-8555-555555555555"
M2 = "66666666-6666-4666-8666-666666666666"


def _fixtures(monkeypatch, *, second_kind="image", archived=False, workflows=None):
    chars = [
        {
            "entity_id": E,
            "project_id": P,
            "display_name": "Owned",
            "workflow_ids": workflows if workflows is not None else [W1, W2],
        }
    ]
    media = [
        {
            "media_id": M1,
            "project_id": P,
            "workflow_id": W1,
            "kind": "image",
            "width": 1024,
            "height": 1024,
        },
        {
            "media_id": M2,
            "project_id": P,
            "workflow_id": W2,
            "kind": second_kind,
            "width": 1024,
            "height": 1024,
        },
    ]
    monkeypatch.setattr(subject, "parse_native_characters", lambda *args: chars)
    monkeypatch.setattr(subject, "parse_media_snapshot", lambda *args: {"media": media})
    monkeypatch.setattr(
        subject,
        "project_media",
        lambda *args: [
            {"workflow_id": W1, "project_id": P, "archived": False, "caption": "First owned"},
            {"workflow_id": W2, "project_id": P, "archived": archived, "caption": "Second owned"},
        ],
    )
    monkeypatch.setattr(subject, "read_project_payload", AsyncMock(return_value=[None, None, []]))
    return SimpleNamespace(_checkout_page=AsyncMock(return_value="page"), _checkin_page=Mock())


@pytest.mark.asyncio
async def test_entity_two_images_count_and_authoritative_name(monkeypatch):
    client = _fixtures(monkeypatch)
    req = GenerateImageRequest(
        prompt="portrait", reference_entities=(E,), reference_entity_names=("Stale",)
    )
    result = await subject.validate_native_image_references(client, P, req)
    assert result.reference_entity_names == ("Owned",)
    subject.read_project_payload.assert_awaited_once_with("page", P)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,archived", [("video", False), ("unknown", False), ("image", True)])
async def test_nonactive_or_nonimage_fails_before_submit(monkeypatch, kind, archived):
    client = _fixtures(monkeypatch, second_kind=kind, archived=archived)
    with pytest.raises(ConfigurationError):
        await subject.validate_native_image_references(
            client, P, GenerateImageRequest(prompt="portrait", reference_entities=(E,))
        )
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_duplicate_character_workflow_fails_unknown_count(monkeypatch):
    client = _fixtures(monkeypatch, workflows=[W1, W1])
    with pytest.raises(ConfigurationError):
        await subject.validate_native_image_references(
            client, P, GenerateImageRequest(prompt="portrait", reference_entities=(E,))
        )


@pytest.mark.asyncio
async def test_invalid_identity_rejected_before_browser(monkeypatch):
    client = _fixtures(monkeypatch)
    with pytest.raises(ConfigurationError):
        await subject.validate_native_image_references(
            client, P, GenerateImageRequest(prompt="portrait", reference_entities=("not-an-id",))
        )
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_image_entity_exceeds_lite_budget_with_two_image_refs(monkeypatch):
    from gflow_cli.api.image import ImageRef, Model

    client = _fixtures(monkeypatch)
    request = GenerateImageRequest(
        prompt="portrait",
        model=Model.HARBOR_SEAL,
        refs=(ImageRef(M1), ImageRef(M2)),
        reference_entities=(E,),
    )
    with pytest.raises(ConfigurationError, match="budget exceeded"):
        await subject.validate_native_image_references(client, P, request)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_one_image_entity_fits_same_lite_budget(monkeypatch):
    from gflow_cli.api.image import ImageRef, Model

    client = _fixtures(monkeypatch, workflows=[W1])
    request = GenerateImageRequest(
        prompt="portrait",
        model=Model.HARBOR_SEAL,
        refs=(ImageRef(M1), ImageRef(M2)),
        reference_entities=(E,),
    )
    assert (
        await subject.validate_native_image_references(client, P, request)
    ).reference_entities == (E,)


@pytest.mark.asyncio
async def test_sdk_ownership_failure_happens_before_mint_submit_or_checkpoint(monkeypatch):
    from gflow_cli.api.client import FlowApiClient

    client = object.__new__(FlowApiClient)
    client.transport = SimpleNamespace(generate_images=AsyncMock())
    client._uses_native_characters = Mock(return_value=True)
    client._mint_recaptcha_token = AsyncMock()
    monkeypatch.setattr(
        subject,
        "validate_native_image_references",
        AsyncMock(side_effect=ConfigurationError(detail="unverified")),
    )
    checkpoint = Mock()
    with pytest.raises(ConfigurationError):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(prompt="portrait", reference_entities=(E,)),
            recaptcha_action="imageGeneration",
            on_checkpoint=checkpoint,
        )
    client._mint_recaptcha_token.assert_not_awaited()
    client.transport.generate_images.assert_not_awaited()
    checkpoint.assert_not_called()


@pytest.mark.asyncio
async def test_slot_plan_uses_fresh_counts_not_supplied_count_hint(monkeypatch):
    from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request

    client = _fixtures(monkeypatch)
    request = prepare_image_slot_request(
        GenerateImageRequest(prompt="@character_1"),
        {"character_1": ReferenceSlot("character", E, 0)},
    )
    result = await subject.validate_native_image_references(client, P, request)
    assert result.reference_prompt_plan.slots[0].image_count == 2
    assert result.reference_entity_names == ("Owned",)


@pytest.mark.asyncio
async def test_invalid_local_reference_fails_before_browser(monkeypatch, tmp_path):
    client = _fixtures(monkeypatch)
    request = GenerateImageRequest(
        prompt="portrait", reference_entities=(E,), ref_paths=(tmp_path / "private-no-file.png",)
    )
    with pytest.raises(ConfigurationError) as error:
        await subject.validate_native_image_references(client, P, request)
    assert "private-no-file" not in str(error.value)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "about:blank", "https://example.test/"])
async def test_auto_unknown_host_entities_refused_before_token_or_submit(url):
    from gflow_cli.api.client import FlowApiClient

    client = object.__new__(FlowApiClient)
    client.settings = SimpleNamespace(flow_host="auto")
    client._page = SimpleNamespace(url=url)
    client.transport = SimpleNamespace(generate_images=AsyncMock())
    client._mint_recaptcha_token = AsyncMock()
    checkpoint = Mock()
    with pytest.raises(ConfigurationError, match="host"):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(prompt="portrait", reference_entities=(E,)),
            recaptcha_action="imageGeneration",
            on_checkpoint=checkpoint,
        )
    client._mint_recaptcha_token.assert_not_awaited()
    client.transport.generate_images.assert_not_awaited()
    checkpoint.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("dimensions", [None, [], [1024, 1024]])
async def test_measured_native_payload_requires_positive_image_dimensions(monkeypatch, dimensions):
    payload = [
        None,
        [[W1, None, None, ["", None, False, None, M1], P]],
        [
            [
                M1,
                P,
                W1,
                None,
                None,
                None,
                [] if dimensions is None else [None, None, dimensions],
                None,
            ]
        ],
        None,
        None,
        [[P, E, None, [1, "Owned", [[[W1, 0]], None, None]]]],
    ]
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value="page"), _checkin_page=Mock())
    monkeypatch.setattr(subject, "read_project_payload", AsyncMock(return_value=payload))
    request = GenerateImageRequest(prompt="portrait", reference_entities=(E,))
    if dimensions == [1024, 1024]:
        assert (
            await subject.validate_native_image_references(client, P, request)
        ).reference_entity_names == ("Owned",)
    else:
        with pytest.raises(ConfigurationError):
            await subject.validate_native_image_references(client, P, request)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arm,video,accepted",
    [
        ([[None] * 17], None, True),
        ([[None] * 15, None], None, True),
        ([None, [None] * 7], None, True),
        ([], None, False),
        ([[None] * 17], [], False),
        (["not-an-image-payload"], None, False),
        ([[None]], None, False),
        ([None, "not-an-array"], None, False),
        ([None, []], None, False),
    ],
)
async def test_measured_dimensionless_forms_and_ambiguous_arms(monkeypatch, arm, video, accepted):
    payload = [
        None,
        [[W1, None, None, ["", None, False, None, M1], P]],
        [[M1, P, W1, None, None, None, arm, video]],
        None,
        None,
        [[P, E, None, [1, "Owned", [[[W1, 0]], None, None]]]],
    ]
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value="page"), _checkin_page=Mock())
    monkeypatch.setattr(subject, "read_project_payload", AsyncMock(return_value=payload))
    request = GenerateImageRequest(prompt="portrait", reference_entities=(E,))
    if accepted:
        assert (
            await subject.validate_native_image_references(client, P, request)
        ).reference_entity_names == ("Owned",)
    else:
        with pytest.raises(ConfigurationError):
            await subject.validate_native_image_references(client, P, request)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_bare_uuid_hydrated_from_same_snapshot_becomes_composer_eligible(monkeypatch):
    from gflow_cli.api.image import ImageRef
    from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request
    from gflow_cli.api.transports.migrated_composer import _unported_image_form

    client = _fixtures(monkeypatch, workflows=[W1])
    request = prepare_image_slot_request(
        GenerateImageRequest(
            prompt="Use @reference_1 beside @character_1 and @reference_1.",
            refs=(ImageRef(M2, display_name="Untrusted", in_project=True), ImageRef(M1)),
            reference_entities=(E,),
        ),
        {
            "reference_1": ReferenceSlot("image", M2),
            "reference_2": ReferenceSlot("image", M1),
            "character_1": ReferenceSlot("character", E, 1),
        },
    )
    result = await subject.validate_native_image_references(client, P, request)
    assert [ref.name for ref in result.refs] == [M2, M1]
    assert [ref.display_name for ref in result.refs] == ["Second owned", "First owned"]
    assert all(ref.in_project for ref in result.refs)
    assert _unported_image_form(result) is None
    assert result.prompt == request.prompt
    assert result.reference_prompt_plan.spans == request.reference_prompt_plan.spans
    assert request.refs[0].display_name == "Untrusted" and not request.refs[1].in_project
    subject.read_project_payload.assert_awaited_once_with("page", P)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caption",
    [42],
    ids=["nontext"],
)
async def test_requested_image_missing_or_invalid_caption_fails_closed(monkeypatch, caption):
    from gflow_cli.api.image import ImageRef

    client = _fixtures(monkeypatch)
    monkeypatch.setattr(
        subject,
        "project_media",
        lambda *args: [{"workflow_id": W1, "project_id": P, "archived": False, "caption": caption}],
    )
    with pytest.raises(ConfigurationError):
        await subject.validate_native_image_references(
            client,
            P,
            GenerateImageRequest(
                prompt="x", refs=(ImageRef(M1, display_name="Forged", in_project=True),)
            ),
        )
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["video", "archived", "foreign", "duplicate_workflow", "duplicate_media"]
)
async def test_claimed_in_project_flag_cannot_bypass_fresh_image_proof(monkeypatch, defect):
    from gflow_cli.api.image import ImageRef

    client = _fixtures(monkeypatch)
    timeline = [
        {
            "workflow_id": W1,
            "project_id": P,
            "archived": defect == "archived",
            "caption": "First owned",
        }
    ]
    media = [
        {
            "media_id": M1,
            "project_id": P if defect != "foreign" else E,
            "workflow_id": W1,
            "kind": "video" if defect == "video" else "image",
            "width": 1024,
            "height": 1024,
        }
    ]
    if defect == "duplicate_workflow":
        timeline.append(dict(timeline[0], caption="Ambiguous"))
    if defect == "duplicate_media":
        media.append(dict(media[0]))
    monkeypatch.setattr(subject, "project_media", lambda *args: timeline)
    monkeypatch.setattr(subject, "parse_media_snapshot", lambda *args: {"media": media})
    with pytest.raises(ConfigurationError):
        await subject.validate_native_image_references(
            client,
            P,
            GenerateImageRequest(
                prompt="x", refs=(ImageRef(M1, display_name="Forged", in_project=True),)
            ),
        )
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_caption_collision_preserves_distinct_owned_image_ids(monkeypatch):
    from gflow_cli.api.image import ImageRef

    client = _fixtures(monkeypatch)
    monkeypatch.setattr(
        subject,
        "project_media",
        lambda *args: [
            {"workflow_id": W1, "project_id": P, "archived": False, "caption": "Same"},
            {"workflow_id": W2, "project_id": P, "archived": False, "caption": "Same"},
        ],
    )
    result = await subject.validate_native_image_references(
        client, P, GenerateImageRequest(prompt="x", refs=(ImageRef(M2), ImageRef(M1)))
    )
    assert [ref.name for ref in result.refs] == [M2, M1]
    assert [ref.display_name for ref in result.refs] == ["Same", "Same"]
    assert all(ref.in_project for ref in result.refs)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_inactive_image_through_sdk_precedes_mint_checkpoint_and_submit(monkeypatch):
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.image import ImageRef

    fake = _fixtures(monkeypatch, workflows=[W1])
    monkeypatch.setattr(
        subject,
        "project_media",
        lambda *args: [{"workflow_id": W1, "project_id": P, "archived": True, "caption": ""}],
    )
    client = object.__new__(FlowApiClient)
    client._checkout_page = fake._checkout_page
    client._checkin_page = fake._checkin_page
    client._uses_native_characters = Mock(return_value=True)
    client._mint_recaptcha_token = AsyncMock()
    submit = AsyncMock()
    client.transport = SimpleNamespace(generate_images=submit)
    checkpoint = Mock()
    with pytest.raises(ConfigurationError):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(
                prompt="portrait", refs=(ImageRef(M1),), reference_entities=(E,)
            ),
            recaptcha_action="imageGeneration",
            on_checkpoint=checkpoint,
        )
    client._mint_recaptcha_token.assert_not_awaited()
    submit.assert_not_awaited()
    checkpoint.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("caption", [None, "", "  ", "x" * 4097])
async def test_owned_identity_survives_missing_or_long_caption(monkeypatch, caption):
    from gflow_cli.api.image import ImageRef

    client = _fixtures(monkeypatch)
    monkeypatch.setattr(
        subject,
        "project_media",
        lambda *args: [{"workflow_id": W1, "project_id": P, "archived": False, "caption": caption}],
    )
    result = await subject.validate_native_image_references(
        client, P, GenerateImageRequest(prompt="x", refs=(ImageRef(M1),))
    )
    assert result.refs[0].name == M1
    assert result.refs[0].display_name == (caption or "")
    client._checkin_page.assert_called_once_with("page")


@pytest.fixture(autouse=True)
def image_model_metadata(monkeypatch):
    """Ownership fixtures also provide fresh available model metadata."""
    import gflow_cli.api.native_image_models as models
    from tests.api.test_native_image_models import payload

    data = payload("NARWHAL")
    data[0][5].extend(payload(key)[0][5][0] for key in ("GEM_PIX_2", "HARBOR_SEAL"))

    async def read(page, rpc, *args):
        return [None, None, None, 2] if rpc == "nzlxg" else data

    monkeypatch.setattr(models, "_read_native", read)


@pytest.mark.asyncio
async def test_plain_native_refs_without_plan_use_fresh_budget_before_submit(monkeypatch):
    import gflow_cli.api.native_image_models as models
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.image import ImageRef
    from tests.api.test_native_image_models import payload

    fake = _fixtures(monkeypatch)

    async def read(page, rpc, *args):
        return [None, None, None, 2] if rpc == "nzlxg" else payload(cap=1)

    monkeypatch.setattr(models, "_read_native", read)
    client = object.__new__(FlowApiClient)
    client._checkout_page = fake._checkout_page
    client._checkin_page = fake._checkin_page
    client._uses_native_characters = Mock(return_value=True)
    client._mint_recaptcha_token = AsyncMock()
    submit = AsyncMock()
    client.transport = SimpleNamespace(generate_images=submit)
    checkpoint = Mock()
    with pytest.raises(ConfigurationError, match="budget exceeded"):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(prompt="Fixture", refs=(ImageRef(M1), ImageRef(M2))),
            recaptcha_action="IMAGE_GENERATION",
            on_checkpoint=checkpoint,
        )
    client._mint_recaptcha_token.assert_not_awaited()
    submit.assert_not_awaited()
    checkpoint.assert_not_called()
