"""Operator configuration and callback destination validation."""

from __future__ import annotations

import ipaddress
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

MAX_ASSET = 20 * 1024 * 1024
MODEL_ALIASES = {
    "nano-banana-2": "nano2",
    "nano-banana-2-lite": "nano2-lite",
    "nano-banana-pro": "nano-pro",
}
VIDEO_ALIASES = {
    "veo-3.1-fast": "veo-fast",
    "veo-3.1-quality": "veo-quality",
    "veo-3.1-lite": "veo-lite",
    "veo-3.1-lite-low-priority": "veo-lite-lp",
    "omni-flash": "omni-flash",
}


@dataclass
class Settings:
    token: str
    root: Path
    accounts: dict[str, dict[str, str]]
    callbacks: tuple[str, ...] = ()
    timeout: int = 900
    allow_video: bool = False

    @classmethod
    def environment(cls) -> Settings:
        token = os.environ.get("GFLOW_DAEMON_TOKEN", "")
        if not token:
            raise ValueError("GFLOW_DAEMON_TOKEN is required")
        raw_accounts: Any = json.loads(os.environ.get("GFLOW_SELFHOST_ACCOUNTS", "{}"))
        if not isinstance(raw_accounts, dict):
            raise ValueError("GFLOW_SELFHOST_ACCOUNTS must be an object")
        accounts: dict[str, dict[str, str]] = {}
        for profile, account in cast(dict[Any, Any], raw_accounts).items():
            if (
                not isinstance(profile, str)
                or not profile.replace("-", "").replace("_", "").isalnum()
            ):
                raise ValueError("Invalid configured profile")
            if not isinstance(account, dict) or not isinstance(
                cast(dict[str, Any], account).get("email"), str
            ):
                raise ValueError("Each configured account requires email")
            uuid.UUID(cast(dict[str, Any], account)["project"])
            accounts[profile] = cast(dict[str, str], account)
        home = Path(os.environ.get("GFLOW_CLI_HOME", str(Path.home() / ".local/share/gflow-cli")))
        root = Path(os.environ.get("GFLOW_SELFHOST_ROOT", str(home / "selfhost"))).resolve()
        return cls(
            token=token,
            root=root,
            accounts=accounts,
            callbacks=tuple(
                filter(None, os.environ.get("GFLOW_SELFHOST_CALLBACK_HOSTS", "").split(","))
            ),
            allow_video=os.environ.get("GFLOW_SELFHOST_ALLOW_VIDEO") == "1",
        )


def validate_callback(url: Any, hosts: tuple[str, ...]) -> str:
    if not isinstance(url, str):
        raise ValueError("Callback URL must be a string")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.fragment
    ):
        raise ValueError("replyUrl requires HTTPS and an explicitly allowlisted host")
    try:
        ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return url
    raise ValueError("IP literal callbacks are forbidden")
