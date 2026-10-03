"""Auto rows resolve from actual local bytes before upload or generation."""

import asyncio
from pathlib import Path

from PIL import Image

from gflow_cli.image_batch import BatchPromptItem, parse_batch_item_dict, run_image_batch
from tests.test_batch_ref_wiring import UploadingClient


def test_manifest_accepts_auto() -> None:
    assert (
        parse_batch_item_dict({"text": "photo", "aspect_ratio": "auto"}, 0).aspect_ratio == "auto"
    )


def test_rows_resolve_local_auto_and_refuse_text_only(tmp_path: Path) -> None:
    photo = tmp_path / "photo.png"
    Image.new("RGB", (300, 400)).save(photo)
    client = UploadingClient(fail_generate=set(), fail_download=set())
    outcomes = asyncio.run(
        run_image_batch(
            profile_dir=tmp_path,
            headless=True,
            transport=None,
            prompts=(
                BatchPromptItem("local", aspect_ratio="auto", ref=str(photo)),
                BatchPromptItem("plain", aspect_ratio="auto", index=1),
            ),
            output_dir=tmp_path / "out",
            continue_on_error=True,
            project_title="t",
            client_factory=lambda **_: client,
            jitter_range=(0, 0),
            _command="run",
        )
    )
    assert outcomes[0].status == "ok"
    assert outcomes[0].prompt.aspect_ratio == "3:4"
    assert outcomes[0].prompt.aspect_decision.requested_aspect == "auto"
    assert outcomes[1].exit_code == 11
    assert "plain" not in client.requests
    assert client.uploads == [photo]


def test_parent_auto_uses_downloaded_bytes(tmp_path: Path) -> None:
    class ImageClient(UploadingClient):
        async def download_image(self, img, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (400, 300)).save(target)
            return target

    client = ImageClient(fail_generate=set(), fail_download=set())
    outcomes = asyncio.run(
        run_image_batch(
            profile_dir=tmp_path,
            headless=True,
            transport=None,
            prompts=(
                BatchPromptItem("parent"),
                BatchPromptItem("child", index=1, ref="batch:0", aspect_ratio="auto"),
            ),
            output_dir=tmp_path / "out",
            continue_on_error=True,
            project_title="t",
            client_factory=lambda **_: client,
            jitter_range=(0, 0),
            _command="run",
        )
    )
    assert outcomes[1].status == "ok"
    assert outcomes[1].prompt.aspect_ratio == "4:3"
    assert (
        outcomes[1].prompt.aspect_decision.policy == "derived-first-reference-nearest-supported-v1"
    )
    assert client.uploads == []


def test_parent_without_downloaded_bytes_refuses_auto(tmp_path: Path) -> None:
    client = UploadingClient(fail_generate=set(), fail_download={"parent"})
    outcomes = asyncio.run(
        run_image_batch(
            profile_dir=tmp_path,
            headless=True,
            transport=None,
            prompts=(
                BatchPromptItem("parent"),
                BatchPromptItem("child", index=1, ref="batch:0", aspect_ratio="auto"),
            ),
            output_dir=tmp_path / "out",
            continue_on_error=True,
            project_title="t",
            client_factory=lambda **_: client,
            jitter_range=(0, 0),
            _command="run",
        )
    )
    assert outcomes[0].images
    assert outcomes[1].exit_code == 11
    assert "child" not in client.requests
