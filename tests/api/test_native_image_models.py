"""Fresh native image budgets never turn metadata into rendering proof."""

import pytest

from gflow_cli.api.image import Model
from gflow_cli.api.native_image_models import image_reference_cap, parse_image_reference_models
from gflow_cli.errors import ConfigurationError


def payload(key="NARWHAL", cap=10, tier=2):
    usage = [None] * 25
    usage[0] = key
    usage[4] = [[tier, [[None, 0]]]]
    usage[21] = [None, 10, cap]
    return [[None, None, None, None, None, [[key, [usage], None, "family"]]]]


@pytest.mark.parametrize(
    ("key", "transport"), [("NARWHAL", 10), ("GEM_PIX_2", 10), ("HARBOR_SEAL", 10)]
)
def test_advertised_and_effective_cap_remain_distinct(key, transport):
    row = parse_image_reference_models(payload(key), tier=2)[0]
    assert row["advertised_reference_cap"] == 10
    assert row["transport_reference_cap"] == transport
    assert row["effective_reference_cap"] == transport
    assert row["retained_reference_verified"] is False


def test_advertised_decrease_restricts_existing_model():
    rows = parse_image_reference_models(payload(cap=2), tier=2)
    assert image_reference_cap(rows, Model.NARWHAL) == 2


@pytest.mark.parametrize("cap", [None, 0, -1, True, "10", [], 101])
def test_malformed_cap_cannot_grant_budget(cap):
    with pytest.raises(ConfigurationError):
        parse_image_reference_models(payload(cap=cap), tier=2)


def test_missing_or_offtier_model_refused():
    with pytest.raises(ConfigurationError):
        image_reference_cap(parse_image_reference_models(payload(tier=1), tier=2), Model.NARWHAL)


def test_duplicate_available_key_refused():
    data = payload()
    data[0][5].append(data[0][5][0])
    with pytest.raises(ConfigurationError):
        parse_image_reference_models(data, tier=2)


@pytest.mark.parametrize("character_cap,effective", [(0, 0), (1, 1), (7, 7), (10, 7)])
def test_character_pool_is_independent_of_image_pool(character_cap, effective):
    data = payload(cap=10)
    data[0][5][0][1][0][21][1] = character_cap
    row = parse_image_reference_models(data, tier=2)[0]
    assert row["advertised_character_cap"] == character_cap
    assert row["effective_character_cap"] == effective
    assert row["effective_reference_cap"] == 10


@pytest.mark.parametrize("character_cap", [None, -1, True, "7", [], 101])
def test_malformed_character_pool_cannot_grant_character_inputs(character_cap):
    data = payload()
    data[0][5][0][1][0][21][1] = character_cap
    with pytest.raises(ConfigurationError, match="character"):
        parse_image_reference_models(data, tier=2)


def test_current_lite_available_image_usage_has_ten_both_pools():
    # Safe projection of the root-owned 2026-10-04 HTrJv/nzlxg capture;
    # private full response is not copied into the repository.
    data = payload("HARBOR_SEAL", cap=10)
    data[0][5][0][1][0][21] = [None, 10, 10]
    row = parse_image_reference_models(data, tier=2)[0]
    assert row["effective_reference_cap"] == 10
    assert row["advertised_character_cap"] == 10
    assert row["effective_character_cap"] == 7
    assert row["retained_reference_verified"] is False
    assert row["rendering_verified"] is False


def test_current_lite_positive_capacity_can_shrink_below_ceiling():
    row = parse_image_reference_models(payload("HARBOR_SEAL", cap=3), tier=2)[0]
    assert row["transport_reference_cap"] == 10
    assert row["effective_reference_cap"] == 3
