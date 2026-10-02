import pytest

from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.worker.codec import build_image_request


def test_api_and_worker_carry_image_seed():
    assert GenerateImageRequest(prompt="fixture", seed=0).seed == 0
    assert build_image_request({"prompt": "fixture", "seed": 42, "count": 2}).seed == 42


@pytest.mark.parametrize(
    "seed,count", [(True, 1), (-1, 1), (2147483648, 1), (2147483647, 2), (1.5, 1), ("42", 1)]
)
def test_invalid_seed_is_rejected_before_browser(seed, count):
    with pytest.raises(ValueError):
        GenerateImageRequest(prompt="fixture", seed=seed, count=count)


async def test_sdk_seed_scope_preserves_provider_and_rejects_wrong_google_seed(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
    from gflow_cli.errors import WireFormatError

    client = FlowApiClient(profile_dir=tmp_path)
    client.transport = SimpleNamespace(name="ui_automation")

    async def token(page):
        return "t" * 30

    provider = ImageOverrides("project", 2, token=token)
    state = active_overrides.set(provider)

    async def drive(**kwargs):
        assert active_overrides.get() is provider and provider.token is token
        assert provider.seed == 42
        provider.used = True
        return [SimpleNamespace(seed=42), SimpleNamespace(seed=43)]

    monkeypatch.setattr(client, "_drive_images_generation_unseeded", drive)
    try:
        result = await client._drive_images_generation(
            project_id="project",
            req=GenerateImageRequest(prompt="fixture", seed=42, count=2),
            recaptcha_action="unused",
        )
        assert [item.seed for item in result] == [42, 43]
        assert provider.seed is None and provider.used
        with pytest.raises(WireFormatError, match="cannot replay"):
            await provider.apply(None, "")
    finally:
        active_overrides.reset(state)
    assert active_overrides.get() is None
    monkeypatch.setattr(
        client,
        "_drive_images_generation_unseeded",
        AsyncMock(return_value=[SimpleNamespace(seed=99)]),
    )
    with pytest.raises(WireFormatError, match="different image seeds"):
        await client._drive_images_generation(
            project_id="project",
            req=GenerateImageRequest(prompt="fixture", seed=42),
            recaptcha_action="unused",
        )
    assert active_overrides.get() is None


async def test_sdk_seed_rejects_other_transport_without_submit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.errors import ConfigurationError

    client = FlowApiClient(profile_dir=tmp_path)
    client.transport = SimpleNamespace(name="bearer")
    drive = AsyncMock()
    monkeypatch.setattr(client, "_drive_images_generation_unseeded", drive)
    with pytest.raises(ConfigurationError, match="native UI"):
        await client._drive_images_generation(
            project_id="project",
            req=GenerateImageRequest(prompt="fixture", seed=42),
            recaptcha_action="unused",
        )
    drive.assert_not_called()


async def test_batch_seed_overflow_rejected_before_project_creation(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api.client import FlowApiClient

    client = FlowApiClient(profile_dir=tmp_path)
    create = AsyncMock()
    monkeypatch.setattr(client, "create_project", create)
    with pytest.raises(ValueError, match="seed"):
        await client.generate_images_batch(
            req=GenerateImageRequest(prompt="fixture", seed=2147483647), count=2
        )
    create.assert_not_called()


async def test_labs_ui_route_rejects_seed_before_submit(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.ui_automation import UiAutomationTransport
    from gflow_cli.errors import ConfigurationError

    transport = UiAutomationTransport()
    transport._page = SimpleNamespace(url="https://labs.google/fx/tools/flow")
    monkeypatch.setattr(transport, "park_deferred_page", AsyncMock())
    monkeypatch.setattr(transport, "_enter_editor", AsyncMock())
    monkeypatch.setattr(transport, "_dismiss_blocking_overlays", AsyncMock())
    monkeypatch.setattr(
        "gflow_cli.api.transports.ui_automation.migrated_route", lambda *args, **kwargs: "labs"
    )
    monkeypatch.setattr(
        "gflow_cli.api.transports.ui_automation.migrated_images_prefer",
        lambda *args, **kwargs: False,
    )
    with pytest.raises(ConfigurationError, match="flow.google.com"):
        await transport._generate_images_locked(
            GenerateImageRequest(prompt="fixture", seed=42), project_id="project"
        )
