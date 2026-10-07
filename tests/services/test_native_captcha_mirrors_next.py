"""Native video/image public provider adapters, no browser or solver tasks."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_provider,
    native_captcha_submission,
    take_native_captcha_token_async,
)
from gflow_cli.api.native_extension import new_extension_started
from gflow_cli.api.native_reference_video import new_reference_started
from gflow_cli.api.native_video_edit import NativeVideoEditStarted
from gflow_cli.errors import UpscaleUnavailableError, WafRejectionError
from gflow_cli.mcp import tools
from gflow_cli.selfhost import native_captcha_policy as policy

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
TOKEN = "synthetic-private-single-use-native-token"


@pytest.fixture
def scopes(monkeypatch):
    seen = {"scopes": [], "tokens": []}

    @contextmanager
    def context(payload, project, action):
        seen["scopes"].append(dict(payload))

        async def mint(page, mint_action):
            token = "synthetic-fresh-native-token-" + str(len(seen["scopes"]))
            seen["tokens"].append(token)
            return token

        with native_captcha_provider(mint, project_id=project, action=action):
            yield

    monkeypatch.setattr(policy, "private_native_captcha", context)
    return seen


@pytest.mark.parametrize(
    "name",
    [
        "gflow_extend_native_video",
        "gflow_edit_native_video",
        "gflow_generate_native_reference_video",
        "gflow_upscale_image",
    ],
)
def test_registered_controls_default_none(name):
    fields = tools.server._tool_manager.get_tool(name).fn_metadata.arg_model.model_fields
    assert fields["captcha_order"].default is None and fields["captcha_retry"].default is None


@pytest.mark.parametrize("kind", ["extend", "reference", "edit", "image"])
def test_cli_controls_visible(kind):
    from gflow_cli.cli_image import upscale
    from gflow_cli.cli_native_extension import extend_native_command
    from gflow_cli.cli_native_reference_video import reference_native_command
    from gflow_cli.cli_native_video_edit import edit_native_command

    command = {
        "extend": extend_native_command,
        "reference": reference_native_command,
        "edit": edit_native_command,
        "image": upscale,
    }[kind]
    result = CliRunner().invoke(command, ["--help"])
    assert "--captcha-order" in result.output and "--captcha-retry" in result.output


@pytest.mark.parametrize("kind", ["extend", "reference"])
def test_cli_existing_workers_receive_nonsecret_controls(kind, tmp_path, monkeypatch):
    from gflow_cli import cli_native_extension as ext
    from gflow_cli import cli_native_reference_video as ref

    module = ext if kind == "extend" else ref
    run = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(module, "run_extension" if kind == "extend" else "run_reference_video", run)
    monkeypatch.setattr(module, "_resolve_profile", lambda _: "fixture")
    args = ([M] if kind == "extend" else []) + [
        "--project",
        P,
        "--prompt",
        "Fixture",
        "--out-dir",
        str(tmp_path),
        "--json",
        "--captcha-order",
        "CapSolver",
        "--captcha-retry",
        "2",
    ]
    result = CliRunner().invoke(
        ext.extend_native_command if kind == "extend" else ref.reference_native_command, args
    )
    assert result.exit_code == 0, result.output
    payload = run.await_args.args[2]
    assert payload["captchaOrder"] == "CapSolver" and payload["captchaRetry"] == 2
    assert TOKEN not in repr(payload) and "captcha_token" not in payload


@pytest.mark.parametrize("kind", ["extend", "reference", "edit"])
def test_native_cli_conflict_before_file_read(kind, tmp_path, monkeypatch):
    from gflow_cli import cli_native_captcha
    from gflow_cli.cli_native_extension import extend_native_command
    from gflow_cli.cli_native_reference_video import reference_native_command
    from gflow_cli.cli_native_video_edit import edit_native_command

    file = tmp_path / "token"
    file.write_text(TOKEN)
    file.chmod(0o600)
    read = AsyncMock(side_effect=AssertionError("Token file must not be consumed"))
    monkeypatch.setattr(cli_native_captcha, "read_native_token_file", read)
    command = {
        "extend": extend_native_command,
        "reference": reference_native_command,
        "edit": edit_native_command,
    }[kind]
    args = ([M] if kind != "reference" else []) + [
        "--project",
        P,
        "--prompt",
        "Fixture",
        "--json",
        "--captcha-token-file",
        str(file),
        "--captcha-retry",
        "1",
    ]
    if kind == "edit":
        args += ["--model-key", "fixture"]
    result = CliRunner().invoke(command, args)
    assert result.exit_code != 0 and TOKEN not in result.output
    read.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["extend", "edit", "reference", "image"])
async def test_mcp_fresh_clients_per_refusal_one_rate_acquisition(
    kind, tmp_path, monkeypatch, scopes
):
    clients = []
    calls = []
    action = "IMAGE_GENERATION" if kind == "image" else "VIDEO_GENERATION"
    started = (
        new_reference_started(P, 1)
        if kind == "reference"
        else NativeVideoEditStarted(**vars(new_extension_started(P, M, 1)), end_frame=24)
        if kind == "edit"
        else new_extension_started(P, M, 1)
    )

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self._page = SimpleNamespace(url="https://flow.google.com/project/" + P)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def _uses_native_characters(self):
            return True

        async def submit(self, **kwargs):
            calls.append(kwargs)
            await take_native_captcha_token_async(
                SimpleNamespace(url="https://flow.google.com/project/" + P), action
            )
            native_captcha_submission()
            if len(calls) == 1:
                native_captcha_outcome("rejected")
                raise WafRejectionError()
            native_captcha_outcome("accepted")
            if "on_started" in kwargs:
                await kwargs["on_started"](started)
            if kind == "image":
                path = kwargs["out_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"image")
                return path
            return started

        extend_native_video = submit
        edit_native_video = submit
        generate_native_reference_video = submit
        upsample_image = submit

        async def wait_native_extension(self, *args):
            return ()

        wait_native_video_edit = wait_native_extension
        wait_native_reference_video = wait_native_extension

    monkeypatch.setattr(tools, "FlowApiClient", Client)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    rate = AsyncMock(return_value=True)
    monkeypatch.setattr(tools._rate_limiter, "acquire", rate)
    if kind == "extend":
        # This fixture isolates CAPTCHA retry/client lifetime; content validation
        # has separate real bounded-download regressions.
        monkeypatch.setattr(
            "gflow_cli.api.native_extension.download_native_extension",
            AsyncMock(return_value=()),
        )
    kwargs = dict(out_dir=str(tmp_path), captcha_order="CapSolver", captcha_retry=2)
    if kind == "extend":
        result = await tools.gflow_extend_native_video(P, M, "Fixture", **kwargs)
    elif kind == "edit":
        result = await tools.gflow_edit_native_video(P, M, "Fixture", "key", 24, **kwargs)
    elif kind == "reference":
        result = await tools.gflow_generate_native_reference_video(
            P, "Fixture", image_ref=[M], **kwargs
        )
    else:
        result = await tools.gflow_upscale_image(M, project=P, **kwargs)
    assert result["status"] == "ok", result
    assert len(clients) == 2 and len(calls) == 2 and len(set(scopes["tokens"])) == 2
    if kind != "image":
        assert rate.await_count == 1
    assert TOKEN not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [True, False])
async def test_image_disabled_or_legacy_refuses_without_mint(tmp_path, monkeypatch, scopes, legacy):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self._page = SimpleNamespace(
                url="https://labs.google/" if legacy else "https://flow.google.com/project/" + P
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def upsample_image(self, **kwargs):
            calls.append(1)
            raise UpscaleUnavailableError()

    monkeypatch.setattr(tools, "FlowApiClient", Client)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    result = await tools.gflow_upscale_image(
        M, project=P, out_dir=str(tmp_path), captcha_order="CapSolver", captcha_retry=10
    )
    assert result["status"] == "error"
    assert calls == ([] if legacy else [1])
    assert scopes["tokens"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["accepted", "unknown"])
async def test_callback_adapter_never_retries_late_or_uncertain_waf(scopes, terminal):
    from gflow_cli.services.native_captcha import run_native_captcha_with_controls

    calls = []

    async def attempt():
        calls.append(1)
        await take_native_captcha_token_async(
            SimpleNamespace(url="https://flow.google.com/project/" + P), "VIDEO_GENERATION"
        )
        native_captcha_submission()
        if terminal == "accepted":
            native_captcha_outcome("accepted")
        raise WafRejectionError()

    with pytest.raises(WafRejectionError):
        await run_native_captcha_with_controls(
            project_id=P, action="VIDEO_GENERATION", attempt=attempt, captcha_retry=10
        )
    assert calls == [1]


@pytest.mark.asyncio
async def test_image_teardown_failure_after_refusal_stops_retry(tmp_path, monkeypatch, scopes):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self._page = SimpleNamespace(url="https://flow.google.com/project/" + P)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise WafRejectionError()

        async def upsample_image(self, **kwargs):
            await take_native_captcha_token_async(self._page, "IMAGE_GENERATION")
            native_captcha_submission()
            native_captcha_outcome("rejected")
            raise WafRejectionError()

    monkeypatch.setattr(tools, "FlowApiClient", Client)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    result = await tools.gflow_upscale_image(M, project=P, out_dir=str(tmp_path), captcha_retry=10)
    assert len(clients) == 1 and len(scopes["tokens"]) == 1
    assert result["status"] == "error" and "teardown" in result["error"]["detail"]


def test_cli_image_controls_conflict_typed_before_file_read(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from gflow_cli import cli_image

    file = tmp_path / "token"
    file.write_text(TOKEN)
    file.chmod(0o600)
    read = Mock(side_effect=AssertionError("Token file must not be consumed"))
    monkeypatch.setattr(cli_image, "read_native_token_file", read)
    monkeypatch.setattr(cli_image, "_resolve_profile", lambda _: "fixture")
    monkeypatch.setattr(cli_image, "_lookup_project_in_catalog", lambda *args: None)
    result = CliRunner().invoke(
        cli_image.upscale,
        [
            M,
            "--project",
            P,
            "--scale",
            "2k",
            "--captcha-token-file",
            str(file),
            "--captcha-retry",
            "1",
        ],
    )
    assert result.exit_code == 2 and "cannot be combined" in result.output
    read.assert_not_called()


@pytest.mark.parametrize("kind", ["image", "edit"])
def test_cli_callbacks_retry_with_fresh_clients(kind, tmp_path, monkeypatch, scopes):
    from gflow_cli import cli_image
    from gflow_cli import cli_native_video_edit as edit

    clients = []
    calls = []
    started = NativeVideoEditStarted(**vars(new_extension_started(P, M, 1)), end_frame=24)

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self._page = SimpleNamespace(url="https://flow.google.com/project/" + P)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def upsample_image(self, **kwargs):
            return await submit(self, **kwargs)

    async def submit(client, **kwargs):
        calls.append(client)
        await take_native_captcha_token_async(
            client._page, "IMAGE_GENERATION" if kind == "image" else "VIDEO_GENERATION"
        )
        native_captcha_submission()
        if len(calls) == 1:
            native_captcha_outcome("rejected")
            raise WafRejectionError()
        native_captcha_outcome("accepted")
        if kind == "image":
            return kwargs["out_path"]
        await kwargs["on_started"](started)
        return started

    module = cli_image if kind == "image" else edit
    monkeypatch.setattr(module, "FlowApiClient", Client)
    monkeypatch.setattr(module, "_resolve_profile", lambda _: "fixture")
    if kind == "image":
        monkeypatch.setattr(cli_image, "_lookup_project_in_catalog", lambda *args: None)
        monkeypatch.setattr(cli_image, "_make_provider_dir", lambda _: tmp_path / "profile")
        command = cli_image.upscale
        args = [M, "--scale", "2k", "--project", P, "--out", str(tmp_path)]
    else:
        monkeypatch.setattr(edit, "edit_native_video", submit)
        monkeypatch.setattr(edit, "wait_native_video_edit", AsyncMock(return_value=()))
        command = edit.edit_native_command
        args = [
            M,
            "--project",
            P,
            "--prompt",
            "Fixture",
            "--model-key",
            "key",
            "--end-frame",
            "24",
            "--out-dir",
            str(tmp_path),
            "--json",
        ]
    result = CliRunner().invoke(
        command, args + ["--captcha-order", "CapSolver", "--captcha-retry", "2"]
    )
    assert result.exit_code == 0, result.output
    assert len(clients) == 2 and len(calls) == 2 and len(set(scopes["tokens"])) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "gflow_extend_native_video",
        "gflow_edit_native_video",
        "gflow_generate_native_reference_video",
        "gflow_upscale_image",
    ],
)
async def test_direct_conflict_refuses_before_profile_or_client(name, monkeypatch):
    from unittest.mock import Mock

    factory = Mock(side_effect=AssertionError("Browser must not open"))
    profile = Mock(side_effect=AssertionError("Profile must not resolve"))
    monkeypatch.setattr(tools, "FlowApiClient", factory)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", profile)
    kwargs = dict(captcha_token=TOKEN, captcha_retry=1)
    if name == "gflow_generate_native_reference_video":
        kwargs.update(project=P, prompt="Fixture", image_ref=[M])
    elif name == "gflow_upscale_image":
        kwargs.update(media_id=M, project=P)
    else:
        kwargs.update(project=P, media_id=M, prompt="Fixture")
        if name == "gflow_edit_native_video":
            kwargs["model_key"] = "key"
    result = await getattr(tools, name)(**kwargs)
    assert result["status"] == "error" and "cannot be combined" in result["error"]["detail"]
    factory.assert_not_called()
    profile.assert_not_called()
