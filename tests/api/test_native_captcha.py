"""Native supplied tokens are private project/action-bound and single-use."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.native_captcha import native_captcha_token, read_native_token_file
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "private-synthetic-token-for-tests"


def page(project=P, host="flow.google.com"):
    return SimpleNamespace(url="https://" + host + "/project/" + project, evaluate=AsyncMock())


@pytest.mark.asyncio
async def test_exact_scope_returns_once_without_browser_then_refuses():
    p = page()
    with native_captcha_token(TOKEN, project_id=P, action="VIDEO_GENERATION") as scope:
        assert TOKEN not in repr(scope)
        assert await TokenMinter(p).mint("VIDEO_GENERATION") == TOKEN
        with pytest.raises(ConfigurationError):
            await TokenMinter(p).mint("VIDEO_GENERATION")
    p.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["host", "project", "action"])
async def test_mismatch_has_no_browser_fallback_or_secret(wrong):
    p = page(
        OTHER if wrong == "project" else P,
        "accounts.google.com" if wrong == "host" else "flow.google.com",
    )
    with native_captcha_token(TOKEN, project_id=P, action="VIDEO_GENERATION"):
        with pytest.raises(ConfigurationError) as error:
            await TokenMinter(p).mint(
                "AUDIO_GENERATION" if wrong == "action" else "VIDEO_GENERATION"
            )
        assert TOKEN not in str(error.value)
    p.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_children_compete_for_same_single_use_token():
    p = page()

    async def consume():
        try:
            return await TokenMinter(p).mint("VIDEO_GENERATION")
        except ConfigurationError:
            return "refused"

    with native_captcha_token(TOKEN, project_id=P, action="VIDEO_GENERATION"):
        result = await asyncio.gather(consume(), consume())
    assert sorted(result) == sorted([TOKEN, "refused"])
    p.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_independent_tasks_have_separate_scopes():
    async def one(token):
        with native_captcha_token(token, project_id=P, action="VIDEO_GENERATION"):
            await asyncio.sleep(0)
            return await TokenMinter(page()).mint("VIDEO_GENERATION")

    assert await asyncio.gather(one(TOKEN + "a"), one(TOKEN + "b")) == [TOKEN + "a", TOKEN + "b"]


@pytest.mark.asyncio
async def test_exception_and_cancellation_reset_scope(monkeypatch):
    p = page()
    minter = TokenMinter(p)
    monkeypatch.setattr(minter, "site_key", AsyncMock(return_value="site"))
    p.evaluate.return_value = "browser"
    for failure in (ValueError, asyncio.CancelledError):
        with pytest.raises(failure):
            with native_captcha_token(TOKEN, project_id=P, action="VIDEO_GENERATION"):
                raise failure
        assert await minter.mint("VIDEO_GENERATION") == "browser"
    assert p.evaluate.await_count == 2


@pytest.mark.parametrize(
    "token", ["", None, "a" * 19, "a" * 20001, "a" * 20 + "\x00", "a" * 20 + " space"]
)
def test_invalid_input_refuses_safely(token):
    with pytest.raises(ConfigurationError):
        with native_captcha_token(token, project_id=P, action="VIDEO_GENERATION"):
            pass


def test_private_file_is_read_without_deletion(tmp_path):
    path = tmp_path / "token"
    path.write_text(TOKEN + "\n")
    path.chmod(0o600)
    assert read_native_token_file(path) == TOKEN
    assert path.exists()


@pytest.mark.parametrize("case", ["symlink", "permissions", "oversized"])
def test_invalid_file_refuses(tmp_path, case):
    path = tmp_path / "token"
    path.write_text(TOKEN)
    path.chmod(0o600)
    if case == "permissions":
        path.chmod(0o644)
    elif case == "oversized":
        path.write_text("x" * 20002)
    else:
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    with pytest.raises(ConfigurationError):
        read_native_token_file(path)


@pytest.mark.asyncio
async def test_child_cannot_use_scope_after_parent_exit():
    ready = asyncio.Event()

    async def child():
        await ready.wait()
        with pytest.raises(ConfigurationError):
            await TokenMinter(page()).mint("VIDEO_GENERATION")

    with native_captcha_token(TOKEN, project_id=P, action="VIDEO_GENERATION"):
        task = asyncio.create_task(child())
    ready.set()
    await task


@pytest.mark.asyncio
async def test_native_audio_minter_uses_same_scope_without_browser():
    from gflow_cli.api.transports.native_voices import _mint_audio_token

    p = page()
    with native_captcha_token(TOKEN, project_id=P, action="AUDIO_GENERATION"):
        assert await _mint_audio_token(p) == TOKEN
    p.evaluate.assert_not_awaited()


def test_native_cli_option_is_present_on_all_applicable_commands():
    from gflow_cli.cli_native_extension import extend_native_command
    from gflow_cli.cli_native_reference_video import reference_native_command
    from gflow_cli.cli_native_video_edit import edit_native_command
    from gflow_cli.cli_voice import create_command

    for command in (
        edit_native_command,
        reference_native_command,
        extend_native_command,
        create_command,
    ):
        assert any("--captcha-token-file" in param.opts for param in command.params)


@pytest.mark.asyncio
async def test_cli_scope_survives_asyncio_run_and_user_file_remains(tmp_path):
    import click
    from click.testing import CliRunner

    from gflow_cli.cli_native_captcha import native_captcha_option

    path = tmp_path / "token"
    path.write_text(TOKEN)
    path.chmod(0o600)

    @click.command()
    @click.option("--project", required=True)
    @native_captcha_option("VIDEO_GENERATION")
    def command(project):
        assert asyncio.run(TokenMinter(page(project)).mint("VIDEO_GENERATION")) == TOKEN

    # Invoke synchronous CLI outside this test's running loop.
    result = await asyncio.to_thread(
        lambda: CliRunner().invoke(command, ["--project", P, "--captcha-token-file", str(path)])
    )
    assert result.exit_code == 0, str(result.exception)
    assert path.exists()
