"""Current native image model capacities; metadata is distinct from retained/rendered proof."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.image import Model, reference_cap_for
from gflow_cli.api.native_extension import _read_native, _uuid
from gflow_cli.api.transports.batchexecute import _at
from gflow_cli.errors import ConfigurationError

# Shared private helpers stay inside the native RPC adapter boundary.
# pyright: reportPrivateUsage=false
if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


def parse_image_reference_models(payload: Any, *, tier: int) -> list[dict[str, Any]]:
    if type(tier) is not int or tier not in {1, 2, 3}:
        raise ConfigurationError(
            detail="Native image model discovery requires an observed account tier"
        )
    families: Any = _at(payload, 0, 5)
    if not isinstance(families, list):
        raise ConfigurationError(detail="Native image model inventory is unavailable")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for family in cast(list[Any], families):
        if _at(family, 5) is True:
            continue
        usages: Any = _at(family, 1)
        if not isinstance(usages, list):
            continue
        for usage in cast(list[Any], usages):
            key: Any = _at(usage, 0)
            try:
                model = Model(key)
            except (ValueError, TypeError):
                continue
            if _at(usage, 24) is True:
                continue
            costs: Any = _at(usage, 4)
            available: Any = None
            if isinstance(costs, list):
                matching = [x for x in cast(list[Any], costs) if _at(x, 0) == tier]
                if len(matching) > 1:
                    raise ConfigurationError(
                        detail="Native image model tier availability is ambiguous"
                    )
                if matching:
                    available = _at(matching[0], 1)
            cost: Any = _at(available, 0, 1)
            if _at(available, 1) is not None or type(cost) is not int or cost < 0:
                continue
            advertised: Any = _at(usage, 21, 2)
            if type(advertised) is not int or not 1 <= advertised <= 100:
                raise ConfigurationError(
                    detail="Native image reference capacity is unavailable or malformed"
                )
            # The image-family decoder uses the same field22 pools as video:
            # audio1, character2, image3. Character count and flattened image
            # weight are independent composer limits (Q6a/$6a/OZa/c_a).
            character_cap: Any = _at(usage, 21, 1)
            if type(character_cap) is not int or not 0 <= character_cap <= 100:
                raise ConfigurationError(
                    detail="Native image character capacity is unavailable or malformed"
                )
            if key in seen:
                raise ConfigurationError(detail="Native image model inventory has ambiguous keys")
            seen.add(key)
            transport = reference_cap_for(model)
            result.append(
                {
                    "model_key": key,
                    "display_name": _at(family, 0),
                    "family": _at(family, 3),
                    "advertised_reference_cap": advertised,
                    "advertised_character_cap": character_cap,
                    "effective_character_cap": min(7, character_cap),
                    "transport_reference_cap": transport,
                    "effective_reference_cap": min(transport, advertised),
                    "retained_reference_verified": False,
                    "rendering_verified": False,
                }
            )
    return result


def image_reference_cap(rows: list[dict[str, Any]], model: Model) -> int:
    matches = [row for row in rows if row["model_key"] == model.value]
    if len(matches) != 1 or type(matches[0]["effective_reference_cap"]) is not int:
        raise ConfigurationError(
            detail="Requested native image model reference capacity was not uniquely observed"
        )
    return matches[0]["effective_reference_cap"]


def image_character_cap(rows: list[dict[str, Any]], model: Model) -> int:
    """Current independent character pool, bounded by the seven public slots."""
    matches = [row for row in rows if row["model_key"] == model.value]
    cap: Any = matches[0].get("effective_character_cap") if len(matches) == 1 else None
    if type(cap) is not int or not 0 <= cap <= 7:
        raise ConfigurationError(
            detail="Requested native image model character capacity was not uniquely observed"
        )
    return cap


async def read_image_reference_models(page: Any, project: str) -> list[dict[str, Any]]:
    models = await _read_native(page, "HTrJv", [], project)
    tier = await _read_native(page, "nzlxg", [], project)
    if not isinstance(tier, list) or len(cast(list[Any], tier)) < 4:
        raise ConfigurationError(detail="Native image account tier was not observed")
    return parse_image_reference_models(models, tier=cast(list[Any], tier)[3])


async def list_native_image_reference_models(
    client: FlowApiClient, project_id: str
) -> list[dict[str, Any]]:
    project = _uuid(project_id)
    page = await client._checkout_page()
    try:
        await page.goto(f"https://flow.google.com/project/{project}", wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
        return await read_image_reference_models(page, project)
    finally:
        client._checkin_page(page)
