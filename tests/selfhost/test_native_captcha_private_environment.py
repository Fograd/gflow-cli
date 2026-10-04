"""Private token workers resolve their root without daemon-only authentication."""

import pytest

from gflow_cli.api.native_captcha import take_native_captcha_token
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.native_captcha import private_native_captcha

P = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "synthetic-single-use-private-worker-token"


@pytest.mark.parametrize("explicit_root", [True, False])
@pytest.mark.parametrize("action", ["VIDEO_GENERATION", "AUDIO_GENERATION"])
def test_private_worker_token_without_daemon_secrets(monkeypatch, tmp_path, explicit_root, action):
    monkeypatch.delenv("GFLOW_DAEMON_TOKEN", raising=False)
    monkeypatch.delenv("GFLOW_SELFHOST_ACCOUNTS", raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("GFLOW_CLI_HOME", str(home))
    root = tmp_path / "explicit" if explicit_root else home / "selfhost"
    if explicit_root:
        monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(root))
    else:
        monkeypatch.delenv("GFLOW_SELFHOST_ROOT", raising=False)
    directory = root / "captcha-input"
    directory.mkdir(parents=True, mode=0o700)
    path = directory / ("a" * 64 + ".token")
    path.write_text(TOKEN)
    path.chmod(0o600)
    with private_native_captcha({"captchaSecret": str(path)}, P, action):
        assert not path.exists()
        with pytest.raises(ConfigurationError, match="scope mismatch"):
            take_native_captcha_token("https://flow.google.com/project/" + OTHER, action)
        wrong_action = "AUDIO_GENERATION" if action == "VIDEO_GENERATION" else "VIDEO_GENERATION"
        with pytest.raises(ConfigurationError, match="scope mismatch"):
            take_native_captcha_token("https://flow.google.com/project/" + P, wrong_action)
        assert take_native_captcha_token("https://flow.google.com/project/" + P, action) == TOKEN
        with pytest.raises(ConfigurationError, match="already consumed"):
            take_native_captcha_token("https://flow.google.com/project/" + P, action)
    assert not path.exists()
    assert take_native_captcha_token("https://flow.google.com/project/" + P, action) is None
