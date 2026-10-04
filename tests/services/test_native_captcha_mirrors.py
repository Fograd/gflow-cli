"""Public native provider mirrors reuse the existing exact-negative-ack policy."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_provider,
    native_captcha_submission,
    take_native_captcha_token_async,
)
from gflow_cli.errors import ConfigurationError, VoiceMutationUnknownError, WafRejectionError
from gflow_cli.mcp import tools
from gflow_cli.selfhost import native_captcha_policy as policy
from gflow_cli.services import native_voices as voice

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
TOKEN = "synthetic-private-native-token-123456789"
ARGS = dict(
    profile="fixture",
    operation="create",
    project_id=P,
    display_name="Fixture",
    preset_voice="Charon",
    dialog="Hello",
    performance="Calm",
)


@pytest.mark.parametrize(
    "order,retry",
    [
        ("bad", None),
        ("CapSolver,CapSolver", None),
        ("", None),
        (True, None),
        (None, True),
        (None, 0),
        (None, 11),
        (None, "2"),
    ],
)
def test_invalid_controls(order, retry):
    from gflow_cli.services.native_captcha import native_captcha_controls

    with pytest.raises(ConfigurationError):
        native_captcha_controls(captcha_order=order, captcha_retry=retry)


def test_controls_default_and_secret_free_shape():
    from gflow_cli.services.native_captcha import native_captcha_controls

    assert native_captcha_controls() == {}
    assert native_captcha_controls(captcha_order="CapSolver,2Captcha", captcha_retry=3) == {
        "captchaOrder": "CapSolver,2Captcha",
        "captchaRetry": 3,
    }
    for kwargs in (dict(captcha_order="CapSolver"), dict(captcha_retry=1)):
        with pytest.raises(ConfigurationError):
            native_captcha_controls(supplied_token=True, **kwargs)


@pytest.fixture
def clients(tmp_path, monkeypatch):
    seen = []

    class Client:
        def __init__(self, **kwargs):
            seen.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(voice, "FlowApiClient", Client)
    monkeypatch.setattr(
        voice,
        "get_settings",
        lambda: SimpleNamespace(headless=False, profile_subdir=lambda _: tmp_path),
    )
    return seen


@pytest.fixture
def scopes(monkeypatch):
    contexts = []

    @contextmanager
    def context(payload, project, action):
        contexts.append(dict(payload))

        async def mint(page, mint_action):
            return "synthetic-fresh-token-" + str(len(contexts))

        with native_captcha_provider(mint, project_id=project, action=action):
            yield

    monkeypatch.setattr(policy, "private_native_captcha", context)
    return contexts


async def dispatch(action="AUDIO_GENERATION"):
    await take_native_captcha_token_async(
        SimpleNamespace(url="https://flow.google.com/project/" + P), action
    )
    native_captcha_submission()


@pytest.mark.asyncio
async def test_saved_voice_fresh_client_each_exact_waf_retry(clients, scopes, monkeypatch):
    calls = []

    async def operate(client, *args, **kwargs):
        calls.append(client)
        await dispatch()
        if len(calls) < 3:
            native_captcha_outcome("rejected")
            raise WafRejectionError()
        native_captcha_outcome("accepted")
        return {"ref": M}

    monkeypatch.setattr(voice, "operate", operate)
    assert await voice.saved_voice_operation(
        **ARGS, captcha_order="CapSolver", captcha_retry=3
    ) == {"ref": M}
    assert len(clients) == 3 and len(set(map(id, calls))) == 3
    assert scopes == [{"captchaOrder": "CapSolver", "captchaRetry": 1}] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize("late", ["accepted", "unknown", "save_unknown"])
async def test_saved_voice_no_retry_without_exact_negative_ack(clients, scopes, monkeypatch, late):
    async def operate(*args, **kwargs):
        await dispatch()
        if late == "accepted":
            native_captcha_outcome("accepted")
        if late == "save_unknown":
            raise VoiceMutationUnknownError(project_id=P, phase="save", media_id=M)
        raise WafRejectionError()

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(VoiceMutationUnknownError if late == "save_unknown" else WafRejectionError):
        await voice.saved_voice_operation(**ARGS, captcha_retry=10)
    assert len(clients) == 1 and len(scopes) == 1


@pytest.mark.asyncio
async def test_saved_voice_default_browser_once_and_supplied_one_use(clients, monkeypatch):
    async def operate(*args, **kwargs):
        assert (
            await take_native_captcha_token_async(
                SimpleNamespace(url="https://flow.google.com/project/" + P), "AUDIO_GENERATION"
            )
            is None
        )
        return {"ref": M}

    monkeypatch.setattr(voice, "operate", operate)
    assert await voice.saved_voice_operation(**ARGS) == {"ref": M}

    async def supplied(*args, **kwargs):
        page = SimpleNamespace(url="https://flow.google.com/project/" + P)
        assert await take_native_captcha_token_async(page, "AUDIO_GENERATION") == TOKEN
        with pytest.raises(ConfigurationError):
            await take_native_captcha_token_async(page, "AUDIO_GENERATION")
        return {"ref": M}

    monkeypatch.setattr(voice, "operate", supplied)
    assert await voice.saved_voice_operation(**ARGS, captcha_token=TOKEN) == {"ref": M}
    assert len(clients) == 2


@pytest.mark.asyncio
async def test_exclusive_controls_and_noncreate_fail_before_client(clients):
    for control in ({"captcha_order": "CapSolver"}, {"captcha_retry": 1}):
        with pytest.raises(ConfigurationError):
            await voice.saved_voice_operation(**ARGS, captcha_token=TOKEN, **control)
    with pytest.raises(ConfigurationError):
        await voice.saved_voice_operation(
            profile="fixture", operation="list", project_id=P, captcha_retry=2
        )
    assert clients == []


def test_cli_voice_controls_forward_and_conflict_before_file_read(tmp_path, monkeypatch):
    from gflow_cli import cli_voice

    calls = []

    async def saved(**kwargs):
        calls.append(kwargs)
        return {"ref": M}

    monkeypatch.setattr(cli_voice, "saved_voice_operation", saved)
    monkeypatch.setattr(cli_voice, "_resolve_profile", lambda _: "fixture")
    args = [
        "create",
        "--project",
        P,
        "--name",
        "Fixture",
        "--preset",
        "Charon",
        "--dialog",
        "Hello",
        "--performance",
        "Calm",
        "--json",
    ]
    result = CliRunner().invoke(
        cli_voice.voice_group, args + ["--captcha-order", "CapSolver", "--captcha-retry", "3"]
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["captcha_order"] == "CapSolver" and calls[0]["captcha_retry"] == 3
    assert "captcha_token" not in str(calls[0]) or calls[0].get("captcha_token") is None
    calls.clear()
    token = tmp_path / "token"
    token.write_text(TOKEN)
    token.chmod(0o600)
    read = AsyncMock(side_effect=AssertionError("Token file must not be read on conflict"))
    monkeypatch.setattr(cli_voice, "read_native_token_file", read)
    result = CliRunner().invoke(
        cli_voice.voice_group, args + ["--captcha-token-file", str(token), "--captcha-retry", "1"]
    )
    assert result.exit_code != 0 and calls == []
    read.assert_not_called()


def test_cli_promotion_payload_has_only_nonsecret_controls(tmp_path, monkeypatch):
    from gflow_cli import cli_native_video_upscale as cli

    calls = []

    async def run(*args):
        calls.append(args)
        return {"results": []}

    monkeypatch.setattr(cli, "run_promotion", run)
    monkeypatch.setattr(cli, "_resolve_profile", lambda _: "fixture")
    result = CliRunner().invoke(
        cli.upscale_native_command,
        [
            M,
            "--project",
            P,
            "--json",
            "--out-dir",
            str(tmp_path),
            "--captcha-order",
            "CapSolver",
            "--captcha-retry",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = calls[0][2]
    assert payload["captchaOrder"] == "CapSolver" and payload["captchaRetry"] == 2
    assert (
        TOKEN not in repr(payload)
        and "captcha_token" not in payload
        and "captchaSecret" not in payload
    )


@pytest.mark.asyncio
async def test_direct_mcp_voice_provider_propagation(monkeypatch):
    saved = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(tools, "_saved_voice_tool", saved)
    result = await tools.gflow_create_saved_voice(
        P, "Fixture", "Charon", "Hello", "Calm", captcha_order="CapSolver", captcha_retry=2
    )
    assert result["status"] == "ok"
    assert (
        saved.await_args.kwargs["captcha_order"] == "CapSolver"
        and saved.await_args.kwargs["captcha_retry"] == 2
    )
    saved.reset_mock()
    result = await tools.gflow_create_saved_voice(
        P, "Fixture", "Charon", "Hello", "Calm", captcha_token=TOKEN, captcha_retry=1
    )
    assert result["status"] == "error"
    saved.assert_not_awaited()
    assert TOKEN not in repr(result)


@pytest.mark.asyncio
async def test_direct_mcp_promotion_payload_and_conflict(tmp_path, monkeypatch):
    from gflow_cli.selfhost import video_promotion_worker

    run = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(video_promotion_worker, "run_promotion", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    result = await tools.gflow_upscale_native_video(
        P, M, out_dir=str(tmp_path), captcha_order="CapSolver", captcha_retry=2
    )
    assert result["status"] == "ok"
    assert run.await_args.args[2]["captchaOrder"] == "CapSolver"
    assert run.await_args.args[2]["captchaRetry"] == 2
    run.reset_mock()
    result = await tools.gflow_upscale_native_video(
        P, M, out_dir=str(tmp_path), captcha_token=TOKEN, captcha_order="CapSolver"
    )
    assert result["status"] == "error"
    run.assert_not_awaited()


@pytest.mark.parametrize("name", ["gflow_create_saved_voice", "gflow_upscale_native_video"])
def test_registered_mcp_controls_optional_and_strict(name):
    tool = tools.server._tool_manager.get_tool(name)
    fields = tool.fn_metadata.arg_model.model_fields
    assert fields["captcha_order"].default is None and fields["captcha_retry"].default is None
    with pytest.raises(ValidationError):
        tool.fn_metadata.arg_model.model_validate(
            {
                "project": P,
                "media_id": M,
                "display_name": "Fixture",
                "preset_voice": "Charon",
                "dialog": "Hello",
                "performance": "Calm",
                "captcha_retry": True,
            }
        )


@pytest.mark.asyncio
async def test_cancelled_saved_voice_never_retries(clients, scopes, monkeypatch):
    async def operate(*args, **kwargs):
        await dispatch()
        raise asyncio.CancelledError()

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(asyncio.CancelledError):
        await voice.saved_voice_operation(**ARGS, captcha_retry=10)
    assert len(clients) == 1 and len(scopes) == 1


@pytest.mark.asyncio
async def test_unconfigured_providers_do_not_solve_or_retry(clients, monkeypatch, tmp_path):
    from gflow_cli.selfhost import native_provider

    monkeypatch.setattr(native_provider.ProviderKeys, "get", lambda *args: None)
    monkeypatch.setattr(
        native_provider, "CaptchaStats", lambda *_: SimpleNamespace(record=lambda *args: None)
    )
    solve = AsyncMock(side_effect=AssertionError("No configured provider"))
    monkeypatch.setattr(native_provider.Solver, "solve", solve)

    async def operate(*args, **kwargs):
        await dispatch()

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(ConfigurationError, match="providers"):
        await voice.saved_voice_operation(**ARGS, captcha_order="CapSolver", captcha_retry=10)
    solve.assert_not_awaited()
    assert len(clients) == 1


@pytest.mark.asyncio
async def test_cleanup_failure_after_accepted_voice_preserves_unknown_without_retry(
    tmp_path, monkeypatch, scopes
):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise RuntimeError("owned teardown failed")

    monkeypatch.setattr(voice, "FlowApiClient", Client)
    monkeypatch.setattr(
        voice,
        "get_settings",
        lambda: SimpleNamespace(headless=False, profile_subdir=lambda _: tmp_path),
    )

    async def operate(*args, **kwargs):
        await dispatch()
        native_captcha_outcome("accepted")
        return {"ref": M, "workflow_id": P}

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(VoiceMutationUnknownError) as caught:
        await voice.saved_voice_operation(**ARGS, captcha_retry=10)
    assert caught.value.to_problem_details().get("known_media_ids") == [M]
    assert len(clients) == 1 and len(scopes) == 1


def test_cli_promotion_conflict_never_reads_file_or_runs(tmp_path, monkeypatch):
    from gflow_cli import cli_native_video_upscale as cli

    token = tmp_path / "token"
    token.write_text(TOKEN)
    token.chmod(0o600)
    read = AsyncMock(side_effect=AssertionError("Token file must not be read"))
    run = AsyncMock(side_effect=AssertionError("Operation must not run"))
    monkeypatch.setattr(cli, "read_native_token_file", read)
    monkeypatch.setattr(cli, "run_promotion", run)
    result = CliRunner().invoke(
        cli.upscale_native_command,
        [
            M,
            "--project",
            P,
            "--json",
            "--captcha-token-file",
            str(token),
            "--captcha-order",
            "CapSolver",
        ],
    )
    assert result.exit_code != 0 and TOKEN not in result.output
    read.assert_not_called()
    run.assert_not_called()


@pytest.mark.parametrize("kind", ["voice", "promotion"])
def test_cli_omitted_controls_remain_none_or_absent(tmp_path, monkeypatch, kind):
    calls = []
    if kind == "voice":
        from gflow_cli import cli_voice as cli

        async def run(**kwargs):
            calls.append(kwargs)
            return {"ref": M}

        monkeypatch.setattr(cli, "saved_voice_operation", run)
        monkeypatch.setattr(cli, "_resolve_profile", lambda _: "fixture")
        command = cli.voice_group
        args = [
            "create",
            "--project",
            P,
            "--name",
            "Fixture",
            "--preset",
            "Charon",
            "--dialog",
            "Hello",
            "--performance",
            "Calm",
            "--json",
        ]
    else:
        from gflow_cli import cli_native_video_upscale as cli

        async def run(*args):
            calls.append(args[2])
            return {"results": []}

        monkeypatch.setattr(cli, "run_promotion", run)
        monkeypatch.setattr(cli, "_resolve_profile", lambda _: "fixture")
        command = cli.upscale_native_command
        args = [M, "--project", P, "--json"]
    result = CliRunner().invoke(command, args)
    assert result.exit_code == 0, result.output
    if kind == "voice":
        assert calls[0].get("captcha_order") is None and calls[0].get("captcha_retry") is None
    else:
        assert "captchaOrder" not in calls[0] and "captchaRetry" not in calls[0]


@pytest.mark.asyncio
async def test_rejected_voice_with_failed_teardown_does_not_open_next_client(
    tmp_path, monkeypatch, scopes
):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise RuntimeError("private teardown failure")

    monkeypatch.setattr(voice, "FlowApiClient", Client)
    monkeypatch.setattr(
        voice,
        "get_settings",
        lambda: SimpleNamespace(headless=False, profile_subdir=lambda _: tmp_path),
    )

    async def operate(*args, **kwargs):
        await dispatch()
        native_captcha_outcome("rejected")
        raise WafRejectionError()

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(ConfigurationError, match="teardown"):
        await voice.saved_voice_operation(**ARGS, captcha_retry=10)
    assert len(clients) == 1 and len(scopes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", ["unknown", "cancel", "rejected_cleanup_cancel"])
async def test_teardown_does_not_mask_unknown_or_cancelled_voice(
    tmp_path, monkeypatch, scopes, primary
):
    clients = []
    unknown = VoiceMutationUnknownError(project_id=P, phase="save", media_id=M)

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            if primary == "rejected_cleanup_cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("private teardown error")

    monkeypatch.setattr(voice, "FlowApiClient", Client)
    monkeypatch.setattr(
        voice,
        "get_settings",
        lambda: SimpleNamespace(headless=False, profile_subdir=lambda _: tmp_path),
    )

    async def operate(*args, **kwargs):
        await dispatch()
        if primary == "unknown":
            raise unknown
        if primary == "cancel":
            raise asyncio.CancelledError()
        native_captcha_outcome("rejected")
        raise WafRejectionError()

    monkeypatch.setattr(voice, "operate", operate)
    with pytest.raises(
        VoiceMutationUnknownError if primary == "unknown" else asyncio.CancelledError
    ) as caught:
        await voice.saved_voice_operation(**ARGS, captcha_retry=10)
    if primary == "unknown":
        assert caught.value is unknown
    assert len(clients) == 1 and len(scopes) == 1


@pytest.mark.asyncio
async def test_ambient_supplied_sdk_scope_rejects_provider_controls_before_client(clients):
    from gflow_cli.api.native_captcha import native_captcha_token

    with native_captcha_token(TOKEN, project_id=P, action="AUDIO_GENERATION"):
        with pytest.raises(ConfigurationError):
            await voice.saved_voice_operation(**ARGS, captcha_retry=2)
        assert clients == []
        assert (
            await take_native_captcha_token_async(
                SimpleNamespace(url="https://flow.google.com/project/" + P), "AUDIO_GENERATION"
            )
            == TOKEN
        )


@pytest.mark.asyncio
async def test_promotion_provider_setup_error_is_typed_and_private(tmp_path, monkeypatch):
    from gflow_cli.selfhost import video_promotion_worker
    from gflow_cli.selfhost.captcha import SolverError

    run = AsyncMock(side_effect=SolverError("private-provider-url-" + TOKEN))
    monkeypatch.setattr(video_promotion_worker, "run_promotion", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    result = await tools.gflow_upscale_native_video(
        P, M, out_dir=str(tmp_path), captcha_order="CapSolver"
    )
    assert result["status"] == "error"
    assert "configuration" in result["error"].get("type", "")
    assert "GFLOW_CAPSOLVER_KEY" in str(result)
    assert TOKEN not in str(result)
    assert run.await_count == 1
