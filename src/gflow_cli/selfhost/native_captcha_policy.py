"""Explicit bounded retries only for negatively acknowledged native CAPTCHA refusal."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from gflow_cli.api.native_captcha import native_captcha_refused
from gflow_cli.errors import WafRejectionError
from gflow_cli.selfhost.native_captcha import private_native_captcha

_Result = TypeVar("_Result")


async def run_with_native_captcha_policy(
    payload: dict[str, Any],
    project: str,
    action: str,
    attempt: Callable[[], Awaitable[_Result]],
) -> _Result:
    """Fresh request/token each attempt; never replay accepted or uncertain work."""
    budget = payload.get("captchaRetry", 1)
    if type(budget) is not int or not 1 <= budget <= 10:
        raise ValueError("Native CAPTCHA retry count must be an integer from1through10")
    if payload.get("captchaSecret") is not None:
        budget = 1
    current = dict(payload)
    if "captchaRetry" in current:
        current["captchaRetry"] = 1
    for index in range(budget):
        with private_native_captcha(current, project, action):
            try:
                return await attempt()
            except WafRejectionError:
                # Catch while the scope is active: finally resets its evidence.
                if (
                    payload.get("captchaSecret") is not None
                    or index + 1 >= budget
                    or not native_captcha_refused()
                ):
                    raise
    raise AssertionError("Native CAPTCHA attempt policy exhausted without result")
