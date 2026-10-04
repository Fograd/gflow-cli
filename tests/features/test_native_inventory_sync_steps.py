"""Offline BDD for native sync orchestration; live reads are root-owned."""

import asyncio

from pytest_bdd import given, scenarios, then, when

from tests.services.test_inventory_sync import P, catalog, client, page, run

scenarios("native_inventory_sync.feature")


@given("an account page with one observed project and a later page cursor", target_fixture="native")
def discovered():
    return client([page([P], "later")])


@when("one synchronization read is allowed", target_fixture="progress")
def one_read(native, tmp_path):
    return asyncio.run(run(native, tmp_path, max_steps=1))


@then("the project catalog remains pending with unknown completeness")
def pending(progress):
    assert progress["pending_project_count"] == 1
    assert progress["complete"] is None
    assert progress["project_pagination_exhausted"] is False


@given("previously synchronized native project media")
def recorded(tmp_path):
    asyncio.run(run(client([page([P]), {"project_catalogs": [catalog()]}]), tmp_path))


@when("a fresh traversal returns no projects or history", target_fixture="progress")
def empty(tmp_path):
    return asyncio.run(run(client([page([])]), tmp_path, restart=True))


@then("the observed media remains with unknown completeness")
def retained(progress):
    assert progress["observations"]["project_catalog"]["media"] == 1
    assert progress["complete"] is None
    assert progress["traversal_finished"] is True
