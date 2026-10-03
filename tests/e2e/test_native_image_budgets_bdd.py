"""Read-only fresh catalog and owned-reference SDK budget boundary; no generation."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest, ImageRef, Model
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_budgets.feature")


class PreflightCompleteError(Exception):
    pass


@given("an explicit native account for read only image reference budgets", target_fixture="case")
def configured(monkeypatch):
    values = {
        k: os.getenv("GFLOW_CLI_E2E_" + k, "") for k in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_IMAGE_BUDGET") != "1":
        pytest.skip("Explicit read-only image budget opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "generation_requests": 0, "boundaries": 0}


@when("fresh model capacities and owned image references reach the SDK transport boundary")
def preflight(case, monkeypatch):
    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            models = await client.list_native_image_reference_models(project)
            by_key = {row["model_key"]: row for row in models}
            assert by_key["NARWHAL"]["effective_reference_cap"] == 10
            assert by_key["HARBOR_SEAL"]["effective_reference_cap"] == 3
            page = await client._checkout_page()

            async def guard(route):
                if any(
                    rpc in route.request.url or rpc in (route.request.post_data or "")
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "YhhmEf",
                        "eb1hJf",
                        "p0UkFb",
                    )
                ):
                    case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            try:
                snapshot = await read_project_payload(page, project)
                media = parse_media_snapshot(snapshot, project)["media"]
                active = {}
                for row in project_media(snapshot, project):
                    if row["archived"] is False:
                        active.setdefault(row["workflow_id"], []).append(row)
                by_workflow = {}
                for row in media:
                    by_workflow.setdefault(row["workflow_id"], []).append(row)
                good = {
                    w
                    for w, rows in by_workflow.items()
                    if len(active.get(w, [])) == 1
                    and all(
                        row["kind"] == "image"
                        and all(type(row.get(k)) is int and row[k] > 0 for k in ("width", "height"))
                        for row in rows
                    )
                }
                selected = [row["media_id"] for row in media if row["workflow_id"] in good][:10]
                if len(selected) < 10:
                    pytest.skip("Ten active owned images required for the ten-reference preflight")
                case["reference_count"] = len(selected)
                client._checkin_page(page)
                page = None

                async def stop(*args, **kwargs):
                    req = kwargs["request"]
                    assert [ref.name for ref in req.refs] == selected
                    case["boundaries"] += 1
                    raise PreflightCompleteError

                monkeypatch.setattr(client.transport, "generate_images", stop)
                with pytest.raises(PreflightCompleteError):
                    await client._drive_images_generation_unseeded(
                        project_id=project,
                        req=GenerateImageRequest(
                            prompt="Reference-budget preflight",
                            model=Model.NARWHAL,
                            refs=tuple(ImageRef(mid) for mid in selected),
                        ),
                        recaptcha_action="IMAGE_GENERATION",
                    )
            finally:
                if page is None:
                    page = await client._checkout_page()
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(run())


@then("the reference order is preserved without uploads or generation")
def verify(case):
    assert case["generation_requests"] == 0 and case["boundaries"] == 1
    print("owned_reference_budget_count", case["reference_count"], "no_generation", True)
