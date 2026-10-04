"""Private-file CAPTCHA option for one native operation."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import Any

import click

from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.api.native_captcha import native_captcha_token, read_native_token_file
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.native_captcha import native_captcha_controls


def native_captcha_option(action: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        def run(*args: Any, **kwargs: Any) -> Any:
            path = kwargs.pop("captcha_token_file", None)
            bound = signature(function).bind_partial(*args, **kwargs)
            project = bound.arguments.get("project")
            try:
                native_captcha_controls(
                    captcha_order=kwargs.get("captcha_order"),
                    captcha_retry=kwargs.get("captcha_retry"),
                    supplied_token=path is not None,
                )
                if path is None:
                    return function(*args, **kwargs)
                if not isinstance(project, str):
                    raise ConfigurationError(
                        detail="Supplied native CAPTCHA requires a project UUID"
                    )
                with native_captcha_token(
                    read_native_token_file(Path(path)), project_id=project, action=action
                ):
                    return function(*args, **kwargs)
            except ConfigurationError as error:

                async def refuse(failure: ConfigurationError = error) -> None:
                    raise failure

                return run_with_handlers(
                    refuse, cli_command=function.__name__, as_json=bool(kwargs.get("as_json"))
                )

        return click.option(
            "--captcha-token-file",
            type=click.Path(exists=True, path_type=Path),
            default=None,
            help="Private mode600 single-use supplied token; Google acceptance unverified.",
        )(run)

    return decorate
