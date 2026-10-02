"""Internal seeded/solver image operation; never expose secret values on argv."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest, Model
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.config import get_settings
from gflow_cli.errors import WafRejectionError, WireFormatError
from gflow_cli.image_recovery import create_journal, download_images
from gflow_cli.selfhost.captcha import CaptchaStats, ProviderKeys, Solver, SolverError


def failure_phase(error: BaseException, *, generating: bool) -> str:
    """Only a typed refusal during generation proves a rejected submit."""
    return "rejected" if generating and isinstance(error, WafRejectionError) else "unknown"


async def generate(profile: str, project: str, job_path: Path) -> None:
    payload: dict[str, Any] = json.loads(job_path.read_text(encoding="utf-8"))
    out = job_path.parent
    stats = CaptchaStats(out.parent.parent)
    secret_path = Path(payload["captchaSecret"]) if payload.get("captchaSecret") else None
    supplied = secret_path.read_text(encoding="utf-8") if secret_path else None
    if secret_path:
        secret_path.unlink(missing_ok=True)
    keys = ProviderKeys(Path.home() / ".config/homelab")
    order = payload.get("captchaOrder", "")
    names = (
        order.split(",")
        if order
        else [name for name in ("CapSolver", "2Captcha") if keys.get(name)]
    )
    selected_solver = bool(payload.get("captchaOrder") or payload.get("captchaRetry"))
    chosen: str | None = None

    async def token(page: Any) -> str:
        nonlocal chosen
        if supplied:
            chosen = "supplied"
            return supplied
        metadata: Any = override.metadata
        if not isinstance(metadata, dict):
            raise SolverError("Browser did not expose CAPTCHA metadata")
        data = cast(dict[str, Any], metadata)
        sitekey, action = data.get("sitekey"), data.get("action")
        if not isinstance(sitekey, str) or not isinstance(action, str) or not action:
            raise SolverError("Browser CAPTCHA metadata is incomplete")
        for name in names:
            stats.record(name, "solveStarted")
            try:
                solution = await Solver().solve(name, keys.get(name), page.url, sitekey, action)
            except SolverError:
                stats.record(name, "solveFailed")
                continue
            chosen = name
            stats.record(name, "solved")
            return solution.token
        raise SolverError("All configured providers failed before Google submission")

    refs = tuple(Path(path) for path in payload.get("refPaths", []))
    request = GenerateImageRequest(
        prompt=payload["prompt"],
        aspect=Aspect.from_cli(payload["aspectRatio"]),
        model=Model.from_cli(payload["model"]),
        ref_paths=refs,
        count=payload["count"],
    )
    override = ImageOverrides(
        project=project,
        count=payload["count"],
        seed=payload.get("seed"),
        token=token if (supplied or selected_solver) else None,
        metadata_required=selected_solver and not bool(supplied),
    )
    state = active_overrides.set(override)
    generating = True
    try:
        settings = get_settings()
        async with FlowApiClient(
            profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
        ) as client:
            images = await client.generate_images_batch(
                project_id=project, req=request, count=payload["count"]
            )
            generating = False
            create_journal(out, images)
            if payload.get("seed") is not None:
                actual = sorted(image.seed for image in images)
                expected = list(range(payload["seed"], payload["seed"] + payload["count"]))
                if actual != expected:
                    raise WireFormatError(detail="Google returned different seeds than requested")
            paths = await download_images(
                client, images, [out / (image.media_name + ".png") for image in images]
            )
            result = json_output.image_result(
                command="selfhost images",
                project_id=project,
                model=payload["model"],
                images=images,
                saved_paths=paths,
            )
            if chosen:
                stats.record(chosen, "accepted")
                result["captchaProvider"] = chosen
            json_output.emit(result)
    except BaseException as error:
        if chosen and override.used:
            stats.record(chosen, failure_phase(error, generating=generating))
        raise
    finally:
        if chosen and override.used:
            stats.record(chosen, "submitted")
        active_overrides.reset(state)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(2)
    profile, project, job_path = sys.argv[1:]
    run_with_handlers(
        lambda: generate(profile, project, Path(job_path)),
        cli_command="selfhost images",
        as_json=True,
    )


if __name__ == "__main__":
    main()
