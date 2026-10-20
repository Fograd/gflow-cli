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
    # A reference copied from another project still needs its original bytes.
    asset = store.asset_get(IMAGE)
    store.asset(IMAGE, "one", NATIVE, asset["path"], asset["mime"])
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
    captcha_policy = AsyncMock()
    monkeypatch.setattr(image_worker, "run_with_image_captcha_policy", captcha_policy)
    with pytest.raises(ConfigurationError, match="no dimensions"):
        await image_worker.generate("pro1", PROJECT, path)
    client.resolve_native_image_aspect.assert_awaited_once_with(PROJECT, NATIVE)
    client.generate_images_batch.assert_not_awaited()
    captcha_policy.assert_not_awaited()


def test_cached_native_reference_uses_its_owned_project_without_explicit_account(tmp_path):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json=body(
                prompt="Use @reference_1.",
                reference_1=IMAGE,
                reference_2=IMAGE,
            )
            | {"email": None},
        )
        assert response.status_code == 201, response.text
    queued = json.loads(store.claim("one")["payload"])
    assert queued["email"] == "test@example.org"
    assert queued["project"] == PROJECT
    assert queued["_image_reference_sources"] == [{"id": IMAGE, "kind": "native"}]


@pytest.mark.asyncio
async def test_cached_native_reference_worker_does_not_upload_its_bytes_again(
    tmp_path, monkeypatch
):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json=body(reference_1=IMAGE, reference_2=IMAGE),
        )
        assert response.status_code == 201, response.text
        job = store.claim("one")
    observed = {}

    async def subprocess(args, *a, **kw):
        assert "gflow_cli.selfhost.image_worker" in args
        observed.update(json.loads(Path(args[-1]).read_text()))
        return 1, b""

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    await runtime.execute(cfg, store, dict(job))
    assert observed["refs"] == [IMAGE]
    assert observed["refPaths"] == []
    assert observed["local_ref_ids"] == []
    assert observed["reference_prompt_plan"]["image_ids"] == [IMAGE]


def test_worker_reuses_owned_cached_native_in_an_older_managed_source_record(tmp_path):
    cfg, store = setup(tmp_path)
    assert runtime.image_reference_inputs(
        cfg,
        store,
        "one",
        {
            "project": PROJECT,
            "_image_reference_sources": [{"id": IMAGE, "kind": "managed"}],
        },
        [IMAGE],
    ) == ([IMAGE], [], [])


def test_worker_rejects_cached_native_record_from_another_project(tmp_path):
    cfg, store = setup(tmp_path)
    with pytest.raises(ValueError):
        runtime.image_reference_inputs(
            cfg,
            store,
            "one",
            {
                "email": "test@example.org",
                "project": NATIVE,
                "_image_reference_sources": [{"id": IMAGE, "kind": "native"}],
            },
            [IMAGE],
        )


@pytest.mark.parametrize("project", [PROJECT, NATIVE])
def test_cached_reference_in_a_different_target_project_keeps_local_copy(tmp_path, project):
    cfg, store = setup(tmp_path)
    target = NATIVE if project == PROJECT else PROJECT
    asset = store.asset_get(IMAGE)
    store.asset(IMAGE, "one", project, asset["path"], asset["mime"])
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json=body(reference_1=IMAGE, reference_2=IMAGE, projectId=target),
        )
        assert response.status_code == 201, response.text
    queued = json.loads(store.claim("one")["payload"])
    assert queued["project"] == target
    assert queued["_image_reference_sources"] == [{"id": IMAGE, "kind": "managed"}]
    assert runtime.image_reference_inputs(cfg, store, "one", queued, [IMAGE]) == (
        [],
        [IMAGE],
        [str(tmp_path / "managed.png")],
    )


def test_non_uuid_local_cache_is_not_promoted_to_native(tmp_path):
    cfg, store = setup(tmp_path)
    asset = store.asset_get(IMAGE)
    local_id = "local-only"
    store.asset(local_id, "one", PROJECT, asset["path"], asset["mime"])
    assert runtime.image_reference_inputs(
        cfg,
        store,
        "one",
        {
            "project": PROJECT,
            "_image_reference_sources": [{"id": local_id, "kind": "managed"}],
        },
        [local_id],
    ) == ([], [local_id], [str(tmp_path / "managed.png")])


def test_legacy_plain_cli_reference_keeps_its_local_input(tmp_path):
    cfg, store = setup(tmp_path)
    assert runtime.image_reference_inputs(cfg, store, "one", {"project": PROJECT}, [IMAGE]) == (
        [],
        [IMAGE],
        [str(tmp_path / "managed.png")],
    )


def test_idempotent_cached_reference_keeps_its_original_project_after_account_change(tmp_path):
    cfg, store = setup(tmp_path)
    payload = body(reference_1=IMAGE, reference_2=IMAGE)
    headers = {**AUTH, "Idempotency-Key": "cached-native-project"}
    with TestClient(create_app(cfg, start_workers=False)) as client:
        first = client.post("/v1/google-flow/images", headers=headers, json=payload)
        assert first.status_code == 201, first.text
        cfg.accounts["one"]["project"] = NATIVE
        replay = client.post("/v1/google-flow/images", headers=headers, json=payload)
        assert replay.status_code == 201, replay.text
    assert len(store.job_page(limit=10)["jobs"]) == 1
    assert replay.json()["jobid"] == first.json()["jobid"]
    queued = json.loads(store.claim("one")["payload"])
    assert queued["project"] == PROJECT
    assert queued["_image_reference_sources"] == [{"id": IMAGE, "kind": "native"}]


def test_worker_rejects_cached_reference_rebound_to_another_account(tmp_path):
    cfg, store = setup(tmp_path)
    asset = store.asset_get(IMAGE)
    store.asset(IMAGE, "foreign", PROJECT, asset["path"], asset["mime"])
    with pytest.raises(ValueError):
        runtime.image_reference_inputs(
            cfg,
            store,
            "one",
            {
                "email": "test@example.org",
                "project": PROJECT,
                "_image_reference_sources": [{"id": IMAGE, "kind": "native"}],
            },
            [IMAGE],
        )


def test_cache_without_native_project_does_not_get_promoted(tmp_path):
    cfg, store = setup(tmp_path)
    asset = store.asset_get(IMAGE)
    store.asset(IMAGE, "one", "", asset["path"], asset["mime"])
    assert runtime.image_reference_inputs(
        cfg,
        store,
        "one",
        {
            "project": "",
            "_image_reference_sources": [{"id": IMAGE, "kind": "managed"}],
        },
        [IMAGE],
    ) == ([], [IMAGE], [str(tmp_path / "managed.png")])


def _legacy_cached_request(store, job_id, caller):
    """Reproduce the pre-reuse payload/fingerprint in an isolated fixture store."""
    import hashlib

    with store.connection() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        frozen = json.loads(row["payload"])
        if "email" in caller:
            frozen["email"] = caller["email"]
        else:
            frozen.pop("email", None)
        frozen["_image_reference_sources"] = [
            {"id": item["id"], "kind": "managed"} for item in frozen["_image_reference_sources"]
        ]
        semantic = json.dumps(
            {key: value for key, value in frozen.items() if key != "_delivery_async"},
            sort_keys=True,
        )
        fingerprint = hashlib.sha256(f"images:one:{semantic}".encode()).hexdigest()
        connection.execute(
            "UPDATE jobs SET payload=?,fingerprint=? WHERE id=?",
            (json.dumps(frozen, sort_keys=True), fingerprint, job_id),
        )
    return frozen, fingerprint


@pytest.mark.parametrize("email", ["omitted", None, "test@example.org"])
def test_idempotent_legacy_cached_request_replays_the_original_job(tmp_path, email):
    cfg, store = setup(tmp_path)
    caller = body(reference_1=IMAGE, reference_2=IMAGE)
    if email == "omitted":
        caller.pop("email")
    else:
        caller["email"] = email
    headers = {**AUTH, "Idempotency-Key": "legacy-cached-source"}
    with TestClient(create_app(cfg, start_workers=False)) as client:
        original = client.post("/v1/google-flow/images", headers=headers, json=caller)
        assert original.status_code == 201, original.text
        frozen, fingerprint = _legacy_cached_request(store, original.json()["jobId"], caller)
        replay = client.post("/v1/google-flow/images", headers=headers, json=caller)
        assert replay.status_code == 201, replay.text
    assert replay.json()["jobId"] == original.json()["jobId"]
    row = store.by_idempotency("legacy-cached-source")
    assert row["fingerprint"] == fingerprint
    assert json.loads(row["payload"]) == frozen
    assert len(store.jobs()) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"prompt": "Different"},
        {"model": "nano-banana-pro"},
        {"projectId": NATIVE},
        {"reference_1": NATIVE},
    ],
)
def test_legacy_cached_request_replay_still_rejects_changed_caller_input(tmp_path, change):
    cfg, store = setup(tmp_path)
    caller = body(reference_1=IMAGE, reference_2=IMAGE)
    headers = {**AUTH, "Idempotency-Key": "legacy-changed-source"}
    with TestClient(create_app(cfg, start_workers=False)) as client:
        original = client.post("/v1/google-flow/images", headers=headers, json=caller)
        assert original.status_code == 201, original.text
        frozen, fingerprint = _legacy_cached_request(store, original.json()["jobId"], caller)
        replay = client.post("/v1/google-flow/images", headers=headers, json={**caller, **change})
        assert replay.status_code == 409, replay.text
    row = store.by_idempotency("legacy-changed-source")
    assert row["fingerprint"] == fingerprint
    assert json.loads(row["payload"]) == frozen
    assert len(store.jobs()) == 1
