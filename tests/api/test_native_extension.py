from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from gflow_cli.api.native_extension import (
    NativeExtensionStarted,
    NativeExtensionUnknownError,
    assigned_id,
    extend_native_video,
    extension_args,
)
from gflow_cli.errors import ConfigurationError

P, M, OUT, W = [str(UUID(int=i)) for i in (1, 2, 3, 4)]


def test_deployed_extension_proto_has_standalone_identity():
    started = NativeExtensionStarted(P, M, (assigned_id(OUT),), (assigned_id(W),), (OUT,), (W,))
    args = extension_args(
        started,
        prompt="Continue the motion",
        model_key="native-key",
        aspect="16:9",
        token="private-token",
        trim_start_frame=12,
        trim_end_frame=36,
    )
    request = args[0][0]
    assert request[0] == [None, M, 12, 36]
    assert request[1] == [None, None, [[["Continue the motion"]]]]
    assert request[2:4] == ["native-key", 2]
    assert request[5] == [None, None, None, None, OUT, W]
    assert args[1][5] == P
    assert args[1][10] == ["private-token", 1]
    assert len(args[2]) == 2  # no scene context or concatenate


@pytest.mark.asyncio
async def test_validation_precedes_browser():
    client = AsyncMock()
    with pytest.raises(ConfigurationError):
        await extend_native_video(
            client, project_id=P, media_id=M, prompt="Continue", model_key="native-key", count=True
        )
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_precedes_single_dispatch_and_failure_preserves_handles(monkeypatch):
    import gflow_cli.api.native_extension as module

    sequence = []
    page = AsyncMock()
    client = AsyncMock()
    client._checkin_page = Mock()
    client._checkout_page.return_value = page
    client._mint_recaptcha_token.return_value = "token"
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *_: {"media": [{"media_id": M, "kind": "video", "width": 1280, "height": 720}]},
    )

    async def metadata(_page, rpc, *_):
        if rpc == "nzlxg":
            return [None, None, None, 2]
        usage = [None] * 25
        usage[0] = "native-key"
        usage[4] = [[2, [[None, 10]]]]
        usage[7] = [[[[1, 14]]]]
        usage[12] = [[2]]
        family = ["Veo extension", [usage], None, "veo-family"]
        return [[None, None, None, None, [family]]]

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="token"))

    async def checkpoint(started):
        sequence.append(("checkpoint", started))

    async def fail(*_):
        sequence.append(("dispatch", None))
        raise TimeoutError()

    page.evaluate.side_effect = fail
    with pytest.raises(NativeExtensionUnknownError) as caught:
        await extend_native_video(
            client,
            project_id=P,
            media_id=M,
            prompt="Continue",
            model_key="native-key",
            count=2,
            on_started=checkpoint,
        )
    assert [row[0] for row in sequence] == ["checkpoint", "dispatch"]
    assert len(caught.value.to_problem_details()["media_ids"]) == 2
    assert page.evaluate.await_count == 1
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_wait_reads_exact_output_and_rejects_unrelated_identity(monkeypatch):
    from unittest.mock import Mock

    import gflow_cli.api.native_extension as module

    started = NativeExtensionStarted(P, M, (OUT,), (W,))
    row = [
        OUT,
        P,
        W,
        "CAE",
        None,
        [None] * 8 + [[3]],
        None,
        [[None] * 8 + ["https://flow-content.google/result"]],
    ]
    monkeypatch.setattr(module, "parse_frames", lambda _: [("as29s", row)])
    page = AsyncMock()
    page.evaluate.return_value = {"status": 200, "text": "safe-fixture"}
    client = AsyncMock()
    client._checkin_page = Mock()
    client._checkout_page.return_value = page
    result = await module.wait_native_extension(client, started, timeout_s=1)
    assert result[0].media_id == OUT
    assert page.evaluate.call_args.args[1]["args"] == [OUT]
    row[2] = M
    with pytest.raises(NativeExtensionUnknownError):
        await module.wait_native_extension(client, started, timeout_s=1)
    assert page.evaluate.await_count == 2


def test_native_extension_models_require_extension_and_available_tier():
    from gflow_cli.api.native_extension import parse_extension_models

    usage = [None] * 25
    usage[0] = "deployed-native-key"
    usage[4] = [[2, [[None, 10]]], [3, [None, []]]]
    usage[7] = [[[[1, 14]]]]
    usage[12] = [[2]]
    family = ["Native Veo", [usage], None, "veo-family"]
    payload = [[None, None, None, None, [family]]]
    available = parse_extension_models(payload, tier=2)
    assert available[0]["model_key"] == "deployed-native-key"
    assert available[0]["credits"] == 10
    assert parse_extension_models(payload, tier=3) == []
    usage[7] = [[[[1]]]]
    assert parse_extension_models(payload, tier=2) == []


def test_uuid_assignment_matches_deployed_sha256_algorithm():
    from hashlib import sha256

    from gflow_cli.api.native_extension import assigned_id

    seed = "00000000-0000-4000-8000-000000000123"
    digits = list(sha256(seed.encode()).hexdigest()[:32])
    digits[12] = "4"
    digits[16] = format(int(digits[16], 16) & 3 | 8, "x")
    assert assigned_id(seed) == str(UUID("".join(digits)))


def test_cli_extend_native_registered_and_count_rejected_without_browser():
    from click.testing import CliRunner

    from gflow_cli.cli_video import video

    help_result = CliRunner().invoke(video, ["extend-native", "--help"])
    assert help_result.exit_code == 0
    assert "--model-key" in help_result.output
    invalid = CliRunner().invoke(
        video, ["extend-native", M, "--project", P, "--prompt", "Continue", "--count", "5"]
    )
    assert invalid.exit_code == 2
