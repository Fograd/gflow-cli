"""Native refs are routed explicitly; managed/native inputs retain slot order."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_reference_slots import AUTH, IMAGE, PROJECT, setup

NATIVE = "44444444-4444-4444-8444-444444444444"


def body(**values):
    return {
        "prompt": "Use @reference_1 and @reference_2.",
        "reference_1": NATIVE,
        "reference_2": IMAGE,
        "model": "nano-banana-2",
        "count": 1,
        "async": True,
        "email": "test@example.org",
        "aspectRatio": "1:1",
        **values,
    }


def test_unknown_native_ref_requires_an_explicit_configured_account(tmp_path):
    cfg, store = setup(tmp_path)
    payload = body()
    payload.pop("email")
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post("/v1/google-flow/images", headers=AUTH, json=payload)
    assert response.status_code == 422
    assert not store.job_page(limit=10)["jobs"]


@pytest.mark.parametrize("native_first", [True, False])
async def test_native_and_managed_refs_keep_original_plan_in_private_worker(
    tmp_path, monkeypatch, native_first
):
    cfg, store = setup(tmp_path)
    payload = body()
    if not native_first:
        payload.update(reference_1=IMAGE, reference_2=NATIVE)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post("/v1/google-flow/images", headers=AUTH, json=payload)
        assert response.status_code == 201, response.text
        job = store.claim("one")
    observed = {}

    async def subprocess(args, *a, **kw):
        assert "gflow_cli.selfhost.image_worker" in args
        path = Path(args[-1])
        assert path.stat().st_mode & 0o777 == 0o600
        observed.update(json.loads(path.read_text()))
        return 1, b""

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    await runtime.execute(cfg, store, dict(job))
    assert observed["refs"] == [NATIVE]
    assert observed["local_ref_ids"] == [IMAGE]
    assert observed["refPaths"] == [str(tmp_path / "managed.png")]
    assert observed["reference_prompt_plan"]["image_ids"] == (
        [NATIVE, IMAGE] if native_first else [IMAGE, NATIVE]
    )


@pytest.mark.parametrize("explicit", [True, False])
def test_native_first_auto_is_deferred_to_the_selected_account_worker(tmp_path, explicit):
    cfg, store = setup(tmp_path)
    payload = body(aspectRatio="auto")
    if not explicit:
        payload.pop("aspectRatio")
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post("/v1/google-flow/images", headers=AUTH, json=payload)
        assert response.status_code == 201, response.text
    queued = json.loads(store.claim("one")["payload"])
    assert queued["aspectRatio"] == "auto"
    assert queued["project"] == PROJECT
    assert "resolvedAspectRatio" not in queued


def test_managed_first_auto_keeps_the_actual_first_source(tmp_path):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json=body(reference_1=IMAGE, reference_2=NATIVE, aspectRatio="auto"),
        )
        assert response.status_code == 201, response.text
    queued = json.loads(store.claim("one")["payload"])
    assert queued["requestedAspectRatio"] == "auto"
    assert queued["resolvedAspectRatio"] == "1:1"


@pytest.mark.asyncio
async def test_native_auto_resolves_only_first_native_input_before_generation():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.image import Aspect
    from gflow_cli.api.image_aspect_policy import derive_aspect
    from gflow_cli.api.reference_markers import (
        ReferenceSlot,
        reference_plan_record,
        resolve_reference_markers,
    )
    from gflow_cli.selfhost.image_worker import prepare_image_aspect
    from gflow_cli.worker.codec import build_image_request

    prompt = "Use @reference_1."
    plan = resolve_reference_markers(
        prompt, surface="image", slots={"reference_1": ReferenceSlot("image", NATIVE)}
    )
    payload = {
        "prompt": prompt,
        "aspectRatio": "auto",
        "refs": [NATIVE],
        "reference_syntax": "slots",
        "reference_prompt_plan": reference_plan_record(plan),
    }
    request = build_image_request({**payload, "aspect": "16:9"})
    resolver = AsyncMock(return_value=(Aspect.from_cli("3:4"), derive_aspect(750, 1000)))
    prepared, metadata = await prepare_image_aspect(
        SimpleNamespace(resolve_native_image_aspect=resolver), PROJECT, request, payload
    )
    resolver.assert_awaited_once_with(PROJECT, NATIVE)
    assert prepared.aspect == Aspect.from_cli("3:4")
    assert metadata["requestedAspectRatio"] == "auto"
    assert metadata["resolvedAspectRatio"] == "3:4"


@pytest.mark.parametrize(
    "records",
    [
        [{"id": NATIVE, "kind": "native", "path": "/caller-controlled.png"}],
        [{"id": IMAGE, "kind": "native"}],
        [{"id": NATIVE, "kind": "unknown"}],
    ],
)
def test_worker_rejects_tampered_source_records(tmp_path, records):
    cfg, store = setup(tmp_path)
    with pytest.raises(ValueError):
        runtime.image_reference_inputs(
            cfg,
            store,
            "one",
            {"email": "test@example.org", "_image_reference_sources": records},
            [NATIVE],
        )


@pytest.mark.asyncio
async def test_missing_first_native_dimensions_never_fall_back_to_second():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import prepare_explicit_image_inputs
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost.image_worker import prepare_image_aspect

    request = GenerateImageRequest(
        prompt="Use @reference_1.", refs=(ImageRef(NATIVE), ImageRef(IMAGE))
    )
    request = prepare_explicit_image_inputs(request, request.refs)
    resolver = AsyncMock(side_effect=ConfigurationError(detail="Missing native dimensions"))
    with pytest.raises(ConfigurationError):
        await prepare_image_aspect(
            SimpleNamespace(resolve_native_image_aspect=resolver),
            PROJECT,
            request,
            {"aspectRatio": "auto"},
        )
    resolver.assert_awaited_once_with(PROJECT, NATIVE)


@pytest.mark.asyncio
async def test_deferred_auto_cannot_replace_a_managed_first_reference(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import prepare_explicit_image_inputs
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost.image_worker import prepare_image_aspect

    path = tmp_path / "first.png"
    native = ImageRef(NATIVE)
    request = GenerateImageRequest(prompt="Use @reference_1.", refs=(native,), ref_paths=(path,))
    request = prepare_explicit_image_inputs(request, (path, native))
    resolver = AsyncMock()
    with pytest.raises(ConfigurationError):
        await prepare_image_aspect(
            SimpleNamespace(resolve_native_image_aspect=resolver),
            PROJECT,
            request,
            {"aspectRatio": "auto"},
        )
    resolver.assert_not_awaited()


def test_native_sources_require_the_same_selected_worker_account(tmp_path):
    cfg, store = setup(tmp_path)
    with pytest.raises(ValueError):
        runtime.image_reference_inputs(
            cfg,
            store,
            "one",
            {
                "email": "other@example.org",
                "_image_reference_sources": [{"id": NATIVE, "kind": "native"}],
            },
            [NATIVE],
        )


async def test_native_auto_resolution_failure_prevents_worker_generation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.reference_markers import (
        ReferenceSlot,
        reference_plan_record,
        resolve_reference_markers,
    )
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost import image_worker

    prompt = "Use @reference_1."
    plan = resolve_reference_markers(
        prompt, surface="image", slots={"reference_1": ReferenceSlot("image", NATIVE)}
    )
    payload = {
        "prompt": prompt,
        "model": "nano-banana-2",
        "count": 1,
        "aspectRatio": "auto",
        "refs": [NATIVE],
        "reference_syntax": "slots",
        "reference_prompt_plan": reference_plan_record(plan),
    }
    path = tmp_path / "output" / "job" / "request.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    client = MagicMock()
    client.resolve_native_image_aspect = AsyncMock(
        side_effect=ConfigurationError(detail="first reference has no dimensions")
    )
    client.generate_images_batch = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(image_worker, "FlowApiClient", MagicMock(return_value=context))
    monkeypatch.setattr(image_worker, "_make_provider_dir", lambda profile: tmp_path / profile)
    monkeypatch.setattr(image_worker, "get_settings", lambda: SimpleNamespace(headless=False))
    monkeypatch.setattr(
        image_worker, "ProviderKeys", lambda root: SimpleNamespace(get=lambda name: "")
    )
    with pytest.raises(ConfigurationError, match="no dimensions"):
        await image_worker.generate("pro1", PROJECT, path)
    client.resolve_native_image_aspect.assert_awaited_once_with(PROJECT, NATIVE)
    client.generate_images_batch.assert_not_awaited()
