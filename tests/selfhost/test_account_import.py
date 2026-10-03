"""Preserved project verification never trusts markers without fresh identity/access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import AuthMissingError, ConfigurationError
from gflow_cli.selfhost.account_import import reverify_imported_project
from gflow_cli.selfhost.profile_import import ImportedProfile

P = "11111111-1111-4111-8111-111111111111"
EMAIL = "fixture@example.test"


@pytest.fixture
def verification(tmp_path, monkeypatch):
    target = tmp_path / "profile_candidate"
    target.mkdir()
    (target / ".gflow_account").write_text(EMAIL)
    imported = ImportedProfile(
        "candidate", EMAIL, P, 1, _identity=(target.stat().st_dev, target.stat().st_ino)
    ).recaptured_private_state(target)
    monkeypatch.setattr("gflow_cli.selfhost.account_import.profile_dir", lambda _: target)
    from gflow_cli.auth.verification import FlowSessionOutcome

    verify = AsyncMock(
        return_value=SimpleNamespace(outcome=FlowSessionOutcome.AUTHENTICATED, user_email=EMAIL)
    )
    monkeypatch.setattr("gflow_cli.auth.verification.verify_flow_profile", verify)
    access = AsyncMock()
    browser = AsyncMock()
    browser.__aenter__.return_value.list_native_media = access

    def factory(**kwargs):
        return browser

    monkeypatch.setattr("gflow_cli.api.client.FlowApiClient", factory)
    return target, imported, verify, browser, access


@pytest.mark.asyncio
async def test_fresh_identity_and_project_once_before_recapture(verification):
    _, imported, verify, browser, access = verification
    updated = await reverify_imported_project(imported, P)
    verify.assert_awaited_once()
    access.assert_awaited_once_with(P)
    browser.__aexit__.assert_awaited_once()
    assert updated.email == EMAIL and updated.project_id == P


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["marker", "directory"])
async def test_changed_owned_state_never_opens_browser(verification, mutation):
    target, imported, verify, browser, _ = verification
    if mutation == "marker":
        (target / ".gflow_account").write_text("other@example.test")
    else:
        target.rename(target.with_name("old_candidate"))
        target.mkdir()
        (target / ".gflow_account").write_text(EMAIL)
    with pytest.raises(ConfigurationError):
        await reverify_imported_project(imported, P)
    verify.assert_not_awaited()
    browser.__aenter__.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_mismatch_never_probes_project(verification):
    _, imported, verify, browser, access = verification
    verify.return_value.user_email = "other@example.test"
    with pytest.raises(AuthMissingError):
        await reverify_imported_project(imported, P)
    browser.__aenter__.assert_not_awaited()
    access.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_error_redacted_and_client_closed(verification):
    _, imported, _, browser, access = verification
    access.side_effect = RuntimeError("private-cookie-body")
    with pytest.raises(AuthMissingError) as caught:
        await reverify_imported_project(imported, P)
    assert "private-cookie-body" not in str(caught.value)
    browser.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_project_refused_before_browser(verification):
    _, imported, verify, browser, _ = verification
    with pytest.raises(ConfigurationError):
        await reverify_imported_project(imported, "not-a-project")
    verify.assert_not_awaited()
    browser.__aenter__.assert_not_awaited()
