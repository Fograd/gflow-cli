"""Internal seeded/solver image operation; never expose secret values on argv."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError, WafRejectionError, WireFormatError
from gflow_cli.image_recovery import create_journal, download_images
from gflow_cli.selfhost.image_captcha_policy import run_with_image_captcha_policy


def failure_phase(error: BaseException, *, generating: bool) -> str:
    """Only a typed refusal during generation proves a rejected submit."""
    return "rejected" if generating and isinstance(error, WafRejectionError) else "unknown"


async def prepare_image_aspect(
    client: FlowApiClient,
    project: str,
    request: GenerateImageRequest,
    payload: dict[str, Any],
) -> tuple[GenerateImageRequest, dict[str, str]]:
    """Resolve native-first Auto before any upload or generation in this worker."""
    from gflow_cli.selfhost.http_jobs import aspect_metadata
    from gflow_cli.services.image_aspect import aspect_decision_metadata

    if payload.get("aspectRatio") != "auto":
        return request, aspect_metadata(payload)
    plan = request.reference_prompt_plan
    if (
        plan is None
        or not plan.image_ids
        or plan.image_ids[0] not in {ref.name for ref in request.refs}
    ):
        raise ConfigurationError(detail="Native Auto requires the first ordered native image input")
    aspect, decision = await client.resolve_native_image_aspect(project, plan.image_ids[0])
    return replace(request, aspect=aspect), aspect_decision_metadata(decision)


async def generate(profile: str, project: str, job_path: Path) -> None:
    payload: dict[str, Any] = json.loads(job_path.read_text(encoding="utf-8"))
    out = job_path.parent
    from gflow_cli.worker.codec import build_image_request

    request = build_image_request(
        {
            **payload,
            "ref_paths": payload.get("refPaths", []),
            "aspect": "16:9" if payload["aspectRatio"] == "auto" else payload["aspectRatio"],
            "reference_entities": payload.get("reference_prompt_plan", {}).get("character_ids", []),
            "reference_syntax": payload.get("reference_syntax", "names"),
        }
    )
    settings = get_settings()
    async with FlowApiClient(
        profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
    ) as client:
        request, aspect_metadata = await prepare_image_aspect(client, project, request, payload)

        async def attempt(override: ImageOverrides) -> Any:
            return await client.generate_images_batch(
                project_id=project, req=request, count=payload["count"]
            )

        images, chosen = await run_with_image_captcha_policy(
            payload, project, out.parent.parent, attempt
        )
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
        result.update(aspect_metadata)
        if chosen:
            result["captchaProvider"] = chosen
        json_output.emit(result)


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
