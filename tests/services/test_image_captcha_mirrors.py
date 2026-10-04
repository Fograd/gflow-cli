"""Generic image public provider adapters; synthetic queue and clients only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from click.testing import CliRunner

from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.errors import ConfigurationError, QueueSchemaError, WafRejectionError
from gflow_cli.mcp import tools
from gflow_cli.worker.codec import decode_payload, encode_payload
from tests.worker.test_daemon import FakeFlowApiClient, FakeGeneratedImage
from tests.worker.test_daemon import temp_db as _temp_db

temp_db = _temp_db

P = "11111111-1111-4111-8111-111111111111"
TOKEN = "synthetic-confidential-image-token-" * 3


@pytest.mark.parametrize("kind", ["t2i", "i2i"])
def test_cli_help_controls(kind):
    from gflow_cli import cli_image

    result = CliRunner().invoke(getattr(cli_image, kind), ["--help"])
    assert "--captcha-order" in result.output and "--captcha-retry" in result.output


@pytest.mark.parametrize("kind", ["t2i", "i2i"])
def test_cli_single_prompt_controls_forward(kind, tmp_path, monkeypatch):
    from gflow_cli import cli_image

    execute = AsyncMock()
    monkeypatch.setattr(cli_image, "_run_" + kind, execute)
    monkeypatch.setattr(cli_image, "_resolve_profile", lambda _: "fixture")
    monkeypatch.setattr(cli_image, "_make_provider_dir", lambda _: tmp_path)
    image = tmp_path / "fixture.png"
    image.write_bytes(b"fixture")
    args = ["Fixture", "--project", P, "--captcha-order", "CapSolver", "--captcha-retry", "2"]
    if kind == "i2i":
        args += ["--ref", str(image)]
    result = CliRunner().invoke(getattr(cli_image, kind), args)
    assert result.exit_code == 0, result.output
    assert execute.await_args.kwargs["captcha_order"] == "CapSolver"
    assert execute.await_args.kwargs["captcha_retry"] == 2


@pytest.mark.parametrize(
    "args",
    [
        ["Fixture", "--captcha-retry", "1"],
        ["Fixture", "Other", "--project", P, "--captcha-retry", "1"],
        ["Fixture", "--project", P, "--captcha-order", "CapSolver,CapSolver"],
    ],
)
def test_cli_invalid_controls_before_profile(args, monkeypatch):
    from gflow_cli import cli_image

    profile = Mock(side_effect=AssertionError("Profile must not resolve"))
    monkeypatch.setattr(cli_image, "_resolve_profile", profile)
    result = CliRunner().invoke(cli_image.t2i, args)
    assert result.exit_code == 2, result.output
    profile.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"captchaRetry": True},
        {"captchaRetry": 0},
        {"captchaRetry": 11},
        {"captchaOrder": "CapSolver,CapSolver"},
        {"captchaOrder": "other"},
        {"project_id": None},
        {"count": 5},
        {"captcha_token": TOKEN},
        {"captchaToken": TOKEN},
        {"captchaSecret": "/private/synthetic-secret"},
        {"captcha_token_file": "/private/token"},
    ],
)
def test_queue_bad_or_confidential_fields_refuse(changes):
    with pytest.raises(QueueSchemaError) as caught:
        decode_payload(
            "t2i", {"prompt": "Fixture", "count": 1, "project_id": P, "captchaRetry": 1, **changes}
        )
    assert TOKEN not in str(caught.value)


def test_registered_mcp_controls_default_none_and_strict():
    fields = tools.server._tool_manager.get_tool("gflow_generate_image").fn_metadata.arg_model
    assert fields.model_fields["captcha_order"].default is None
    assert fields.model_fields["captcha_retry"].default is None
    with pytest.raises(ValueError):
        fields.model_validate({"prompt": "Fixture", "captcha_retry": True})


@pytest.mark.asyncio
async def test_mcp_queue_roundtrip_wait_false(monkeypatch):
    run = AsyncMock(return_value={"status": "queued", "task_id": "fixture-task"})
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_generate_image(
        "Fixture", project=P, count=2, wait=False, captcha_order="CapSolver", captcha_retry=1
    )
    assert result["status"] == "queued"
    assert run.await_args.kwargs["wait"] is False
    payload = run.await_args.kwargs["payload"]
    decoded = decode_payload("t2i", payload)
    encoded = encode_payload("t2i", decoded)
    assert encoded["captchaOrder"] == "CapSolver" and encoded["captchaRetry"] == 1
    assert TOKEN not in repr(encoded) and "captcha_token" not in encoded


@pytest.mark.asyncio
async def test_mcp_confidential_input_refuses_before_queue_or_profile(monkeypatch):
    run = AsyncMock(side_effect=AssertionError("Queue must not receive confidential tokens"))
    profile = Mock(side_effect=AssertionError("Profile must not resolve"))
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", profile)
    result = await tools.gflow_generate_image(
        "Fixture", project=P, captcha_token=TOKEN, captcha_retry=1
    )
    assert result["status"] == "error" and TOKEN not in str(result)
    run.assert_not_called()
    profile.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 4])
async def test_service_existing_image_policy_count_seed_and_fresh_overrides(tmp_path, count):
    from gflow_cli.services.image_captcha import generate_images_with_captcha

    req = GenerateImageRequest(prompt="Fixture", count=count, seed=4)
    seen = []

    async def submit(**kwargs):
        scope = active_overrides.get()
        seen.append(scope)
        assert scope.count == count and scope.seed == 4
        scope.used = True
        scope.mark_submitted()
        if len(seen) == 1:
            scope.outcome("rejected")
            raise WafRejectionError()
        scope.outcome("accepted")
        return [FakeGeneratedImage("fixture-" + str(i), seed=4 + i) for i in range(count)]

    client = SimpleNamespace(
        _page=SimpleNamespace(url="https://flow.google.com/project/" + P),
        transport=SimpleNamespace(name="ui_automation"),
        generate_image=AsyncMock(side_effect=lambda **kwargs: None),
        generate_images_batch=AsyncMock(side_effect=submit),
    )

    async def single(**kwargs):
        return (await submit(**kwargs))[0]

    client.generate_image = AsyncMock(side_effect=single)
    values = await generate_images_with_captcha(
        client, req=req, project_id=P, captcha_retry=2, root=tmp_path
    )
    assert len(values) == count and len(seen) == 2 and seen[0] is not seen[1]
    assert all(scope.closed for scope in seen) and active_overrides.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["accepted", "unknown", None, "cancelled"])
async def test_service_never_retries_unknown_accepted_or_cancelled(tmp_path, phase):
    from gflow_cli.services.image_captcha import generate_images_with_captcha

    calls = []

    async def submit(**kwargs):
        calls.append(1)
        scope = active_overrides.get()
        scope.used = True
        scope.mark_submitted()
        if phase == "cancelled":
            scope.outcome("rejected")
            raise asyncio.CancelledError()
        if phase is not None:
            scope.outcome(phase)
        raise WafRejectionError()

    client = SimpleNamespace(
        _page=SimpleNamespace(url="https://flow.google.com/project/" + P),
        transport=SimpleNamespace(name="ui_automation"),
        generate_image=AsyncMock(side_effect=submit),
    )
    with pytest.raises(asyncio.CancelledError if phase == "cancelled" else WafRejectionError):
        await generate_images_with_captcha(
            client,
            req=GenerateImageRequest(prompt="Fixture"),
            project_id=P,
            captcha_retry=10,
            root=tmp_path,
        )
    assert calls == [1] and active_overrides.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,transport",
    [
        ("https://labs.google/fx", "ui_automation"),
        ("about:blank", "ui_automation"),
        ("https://flow.google.com/project/" + P, "evaluate_fetch"),
    ],
)
async def test_service_unsupported_host_transport_refuses_before_submit(tmp_path, host, transport):
    from gflow_cli.services.image_captcha import generate_images_with_captcha

    submit = AsyncMock()
    client = SimpleNamespace(
        _page=SimpleNamespace(url=host),
        transport=SimpleNamespace(name=transport),
        generate_image=submit,
    )
    with pytest.raises(ConfigurationError):
        await generate_images_with_captcha(
            client,
            req=GenerateImageRequest(prompt="Fixture"),
            project_id=P,
            captcha_retry=1,
            root=tmp_path,
        )
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_service_default_path_installs_no_override():
    from gflow_cli.services.image_captcha import generate_images_with_captcha

    async def submit(**kwargs):
        assert active_overrides.get() is None
        return FakeGeneratedImage("fixture")

    client = SimpleNamespace(generate_image=AsyncMock(side_effect=submit))
    result = await generate_images_with_captcha(
        client, req=GenerateImageRequest(prompt="Fixture"), project_id=P
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_service_refuses_nested_provider_scope(tmp_path):
    from gflow_cli.services.image_captcha import generate_images_with_captcha

    outer = ImageOverrides(P, 1, token=AsyncMock(return_value=TOKEN))
    handle = active_overrides.set(outer)
    submit = AsyncMock()
    try:
        with pytest.raises(ConfigurationError):
            await generate_images_with_captcha(
                SimpleNamespace(generate_image=submit),
                req=GenerateImageRequest(prompt="Fixture"),
                project_id=P,
                captcha_retry=1,
                root=tmp_path,
            )
        submit.assert_not_called()
        assert active_overrides.get() is outer
    finally:
        active_overrides.reset(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [False, True])
async def test_durable_worker_dispatches_controls_keeps_outputs(temp_db, tmp_path, provider):
    from gflow_cli.worker.daemon import FlowWorker
    from gflow_cli.worker.queue import QueueRepository

    repo = QueueRepository(temp_db)
    images = [
        FakeGeneratedImage(
            "fixture-" + str(i),
            workflow_id="workflow-" + str(i),
            media_generation_id="generation-" + str(i),
        )
        for i in range(2)
    ]
    payload = {
        "prompt": "Fixture",
        "project_id": P,
        "count": 2,
        "out_dir": str(tmp_path),
        **({"captchaOrder": "CapSolver", "captchaRetry": 1} if provider else {}),
    }
    task = repo.enqueue_task(
        task_id="generic-image-fixture", profile_name="default", task_type="t2i", payload=payload
    )
    fake = FakeFlowApiClient()
    fake.generate_images_batch = AsyncMock(return_value=images)
    policy = AsyncMock(return_value=images)
    worker = FlowWorker("default", str(temp_db.path))
    try:
        with (
            patch("gflow_cli.worker.daemon.FlowApiClient", return_value=fake),
            patch("gflow_cli.services.image_captcha.generate_images_with_captcha", policy),
        ):
            await worker.process_task(task)
        done = repo.get_task(task.task_id)
        assert done.status == "completed"
        assert done.checkpoint["media_ids"] == [image.media_name for image in images]
        assert done.checkpoint["workflow_ids"] == [image.workflow_id for image in images]
        if provider:
            policy.assert_awaited_once()
            assert (
                policy.await_args.kwargs["captcha_order"] == "CapSolver"
                and policy.await_args.kwargs["captcha_retry"] == 1
            )
            fake.generate_images_batch.assert_not_awaited()
        else:
            policy.assert_not_awaited()
            fake.generate_images_batch.assert_awaited_once()
    finally:
        worker.close()


@pytest.mark.parametrize("source", ["file", "stdin"])
def test_cli_provider_batch_sources_refuse_before_consumption(source, tmp_path, monkeypatch):
    from gflow_cli import cli_image

    reader = Mock(side_effect=AssertionError("Batch source must not be consumed"))
    monkeypatch.setattr(cli_image, "_build_t2i_batch_prompts", reader)
    args = ["--project", P, "--captcha-retry", "1"]
    if source == "file":
        file = tmp_path / "prompts.txt"
        file.write_text("Fixture")
        args += ["--prompts-file", str(file)]
    else:
        args += ["--stdin"]
    result = CliRunner().invoke(cli_image.t2i, args, input="Fixture")
    assert result.exit_code == 2 and "single prompt" in result.output
    reader.assert_not_called()


@pytest.mark.asyncio
async def test_provider_setup_failure_typed_and_sanitized(tmp_path, monkeypatch):
    from gflow_cli.selfhost.captcha import SolverError
    from gflow_cli.services import image_captcha

    run = AsyncMock(side_effect=SolverError("synthetic-private-provider-key-" + TOKEN))
    monkeypatch.setattr(image_captcha, "run_with_image_captcha_policy", run)
    client = SimpleNamespace(
        _page=SimpleNamespace(url="https://flow.google.com/project/" + P),
        transport=SimpleNamespace(name="ui_automation"),
    )
    with pytest.raises(ConfigurationError) as caught:
        await image_captcha.generate_images_with_captcha(
            client,
            req=GenerateImageRequest(prompt="Fixture"),
            project_id=P,
            captcha_retry=1,
            root=tmp_path,
        )
    assert TOKEN not in str(caught.value)
    assert "GFLOW_CAPSOLVER_KEY" in caught.value.remediation_hint


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["complete", "download_failed", "cancelled"])
async def test_registered_tool_through_real_queue_codec_daemon(
    temp_db, tmp_path, monkeypatch, terminal
):
    from gflow_cli.api.dto import GenerationCheckpoint
    from gflow_cli.services import image_captcha
    from gflow_cli.worker.daemon import FlowWorker
    from gflow_cli.worker.queue import QueueRepository

    repo = QueueRepository(temp_db)

    async def enqueue(**kwargs):
        assert kwargs["wait"] is False
        repo.enqueue_task(
            task_id="registered-image-fixture",
            profile_name="default",
            task_type=kwargs["task_type"],
            payload=kwargs["payload"],
        )
        return {"status": "queued", "task_id": "registered-image-fixture"}

    monkeypatch.setattr(tools, "_run_generation_task", enqueue)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "default")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    monkeypatch.setattr(image_captcha, "environment_root", lambda: tmp_path / "private-root")
    registered = tools.server._tool_manager.get_tool("gflow_generate_image")
    data = registered.fn_metadata.arg_model.model_validate(
        {
            "prompt": "Fixture",
            "project": P,
            "count": 2,
            "captcha_order": "CapSolver",
            "captcha_retry": 2,
            "wait": False,
        }
    )
    result = await registered.fn(**data.model_dump())
    assert result["status"] == "queued"
    task = repo.claim_task(result["task_id"], "fixture-claimant")
    assert task.decoded.fields["captchaOrder"] == "CapSolver"
    assert task.decoded.fields["captchaRetry"] == 2
    assert "captcha_token" not in task.payload and TOKEN not in repr(task.payload)
    images = [
        FakeGeneratedImage(
            "registered-" + str(i),
            workflow_id="workflow-" + str(i),
            media_generation_id="generation-" + str(i),
        )
        for i in range(2)
    ]
    fake = FakeFlowApiClient()
    fake._page = SimpleNamespace(url="https://flow.google.com/project/" + P)
    fake.transport = SimpleNamespace(name="ui_automation")
    calls = []

    async def submit(**kwargs):
        calls.append(1)
        override = active_overrides.get()
        assert override.project == P and override.count == 2 and kwargs["req"].count == 2
        override.used = True
        override.mark_submitted()
        kwargs["on_checkpoint"](GenerationCheckpoint(phase="submit_attempted"))
        if terminal == "cancelled":
            override.outcome("rejected")
            raise asyncio.CancelledError()
        override.outcome("accepted")
        kwargs["on_checkpoint"](
            GenerationCheckpoint(
                phase="remote_started",
                media_ids=tuple(image.media_name for image in images),
                workflow_ids=tuple(image.workflow_id for image in images),
            )
        )
        return images

    fake.generate_images_batch = AsyncMock(side_effect=submit)
    if terminal == "download_failed":
        fake.download_image = AsyncMock(side_effect=WafRejectionError())
    worker = FlowWorker("default", str(temp_db.path))
    try:
        with patch("gflow_cli.worker.daemon.FlowApiClient", return_value=fake):
            if terminal == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await worker.process_task(task)
            else:
                await worker.process_task(task)
        done = repo.get_task(task.task_id)
        assert calls == [1] and active_overrides.get() is None
        if terminal == "complete":
            assert done.status == "completed"
            assert done.checkpoint["media_ids"] == [image.media_name for image in images]
        elif terminal == "cancelled":
            assert done.status == "indeterminate" and done.checkpoint["may_have_spent"] is True
        else:
            assert done.status == "failed"
            assert done.checkpoint["media_ids"] == [image.media_name for image in images]
    finally:
        worker.close()


@pytest.mark.asyncio
async def test_i2i_runtime_controls_leave_real_mention_helper_unchanged(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from gflow_cli import cli_image
    from gflow_cli.api.image import Aspect, ImageRef, Model

    client = FakeFlowApiClient()
    monkeypatch.setattr(cli_image, "FlowApiClient", lambda **kwargs: client)
    monkeypatch.setattr(cli_image.OperationRecorder, "open", lambda _: MagicMock())
    monkeypatch.setattr(cli_image, "_enrich_uuid_refs", lambda refs, profile: refs)
    tail = AsyncMock(return_value=([FakeGeneratedImage("fixture")], [tmp_path / "fixture.png"]))
    monkeypatch.setattr(cli_image, "_generate_verify_download", tail)
    monkeypatch.setattr(cli_image, "_record_generated_images_safe", Mock())
    params = cli_image._I2IParams(
        prompt="Fixture",
        classified_refs=[ImageRef(P)],
        aspect=Aspect.from_cli("1:1"),
        model=Model.from_cli("nano2"),
        reference_entities=(),
        reference_entity_names=(),
    )
    await cli_image._run_i2i(
        profile_name="fixture",
        profile_dir=tmp_path,
        headless=False,
        params=params,
        count=1,
        out=tmp_path,
        output_root=tmp_path,
        project_id=P,
        as_json=False,
        captcha_order="CapSolver",
        captcha_retry=2,
    )
    assert tail.await_args.kwargs["captcha_order"] == "CapSolver"
    assert tail.await_args.kwargs["captcha_retry"] == 2
    assert tail.await_args.kwargs["req"].prompt == "Fixture"
