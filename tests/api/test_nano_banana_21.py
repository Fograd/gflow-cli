"""Nano Banana 2.1 identity must survive every existing input boundary."""

import pytest
from fastapi.testclient import TestClient

from gflow_cli.api.image import Model, reference_cap_for
from gflow_cli.api.native_image_models import parse_image_reference_models
from gflow_cli.api.reference_markers import (
    ReferenceContractError,
    ReferenceSlot,
    resolve_reference_markers,
    validate_reference_budget,
)
from gflow_cli.api.transports.migrated_composer import IMAGE_MODEL_MENU_MATCHERS
from gflow_cli.api.transports.ui_automation import UiAutomationTransport
from gflow_cli.cli_models import build_catalog
from gflow_cli.image_batch import ALLOWED_MODELS
from gflow_cli.selfhost.config import MODEL_ALIASES
from gflow_cli.selfhost.server import create_app
from gflow_cli.worker.codec import decode_payload, encode_payload
from tests.api.test_native_image_models import payload
from tests.selfhost.test_server import AUTH, settings


@pytest.mark.parametrize("alias", ["nano2.1", "BELUGA", "nano-banana-2.1"])
def test_explicit_alias_preserves_new_identity(alias):
    assert Model.from_cli(alias).value == "BELUGA"
    assert Model.from_cli("nano2").value == "NARWHAL"


def test_cli_and_rest_catalogues_offer_new_model():
    assert "nano2.1" in ALLOWED_MODELS
    assert MODEL_ALIASES["nano-banana-2.1"] == "nano2.1"
    row = next(row for row in build_catalog()["image"]["models"] if row["name"] == "BELUGA")
    assert row["aliases"] == ["nano2.1"]
    assert row["ref_cap"] == 10


def test_old_model_cannot_accept_new_selected_chip():
    for matcher in (
        IMAGE_MODEL_MENU_MATCHERS[Model.NARWHAL],
        UiAutomationTransport._CHARACTER_MODEL_MATCHERS["nano2"],
    ):
        assert matcher.matches("🍌 Nano Banana 2")
        assert not matcher.matches("🍌 Nano Banana 2.1")
        assert not matcher.matches("🍌 Nano Banana 2 Lite")


def test_new_model_only_matches_its_own_label():
    matcher = IMAGE_MODEL_MENU_MATCHERS[Model.from_cli("nano2.1")]
    assert matcher.matches("🍌 Nano Banana 2.1")
    assert not matcher.matches("🍌 Nano Banana 2")
    assert not matcher.matches("🍌 Nano Banana 2 Lite")


def test_fresh_account_cap_can_restrict_beluga():
    rows = parse_image_reference_models(payload("BELUGA", cap=3), tier=2)
    assert len(rows) == 1
    assert rows[0]["effective_reference_cap"] == 3
    assert reference_cap_for(Model.from_cli("nano2.1")) == 10
    assert rows[0]["rendering_verified"] is False


def test_slot_contract_accepts_beluga_but_respects_fresh_cap():
    plan = resolve_reference_markers(
        "Use @reference_1",
        surface="image",
        slots={"reference_1": ReferenceSlot("image", "image-one")},
    )
    assert validate_reference_budget(plan, surface="image", model="nano-banana-2.1") == 1
    with pytest.raises(ReferenceContractError, match="budget exceeded"):
        validate_reference_budget(
            plan, surface="image", model="nano-banana-2.1", native_image_cap=0
        )


def test_mcp_queue_preserves_model_seed_and_reference():
    decoded = decode_payload(
        "t2i", {"prompt": "test", "model": "nano2.1", "seed": 42, "refs": ["ref-one"]}
    )
    again = decode_payload("t2i", encode_payload("t2i", decoded))
    assert again.request.model.value == "BELUGA"
    assert again.request.seed == 42
    assert again.request.refs == decoded.request.refs


def test_rest_accepts_explicit_beluga_without_generation(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "test", "model": "nano-banana-2.1", "async": True},
        )
    assert response.status_code == 201, response.text
