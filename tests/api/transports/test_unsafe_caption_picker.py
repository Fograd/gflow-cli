"""Unsafe captions are locator input, never image identity."""

import unicodedata
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.image import ImageRef
from gflow_cli.api.transports.migrated_composer import MigratedComposer, _picker_query
from gflow_cli.errors import ReferenceNotFoundError


@pytest.mark.parametrize(
    "caption,query",
    [
        ("  Safe caption  ", "Safe caption"),
        ("@portrait", "portrait"),
        ("short\nlonger caption", "longer caption"),
        ("one\x00longer", "longer"),
        ("\u202e", ""),
        ("", ""),
        ("x" * 121, "x" * 120),
        ("a\ud800bc", "bc"),
    ],
)
def test_bounded_safe_contiguous_locator(caption, query):
    result = _picker_query(ImageRef("owned-image", display_name=caption))
    assert result == query
    assert len(result) <= 120 and "@" not in result
    assert not any(unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for ch in result)


@pytest.mark.asyncio
async def test_duplicate_target_option_never_presses_enter():
    keyboard = SimpleNamespace(type=AsyncMock(), press=AsyncMock())
    page = SimpleNamespace(
        keyboard=keyboard,
        locator=lambda _: SimpleNamespace(first=SimpleNamespace(click=AsyncMock())),
        wait_for_timeout=AsyncMock(),
        evaluate=AsyncMock(return_value=["owned-token", "owned-token"]),
    )
    composer = MigratedComposer()
    with pytest.raises(ReferenceNotFoundError):
        await composer._mention_by_token(page, "safe", "owned-token", "owned-image", expect_chips=1)
    assert "Enter" not in [call.args[0] for call in keyboard.press.await_args_list]
    keyboard.press.assert_awaited_with("Escape")


def test_owned_image_without_caption_retains_id_for_bare_picker():
    from gflow_cli.api.native_image_references import _hydrate_owned_images

    identifier = "11111111-1111-4111-8111-111111111111"
    workflow = "22222222-2222-4222-8222-222222222222"
    refs = _hydrate_owned_images(
        (ImageRef(identifier),),
        [{"media_id": identifier}],
        [{"workflow_id": workflow, "caption": ""}],
        {identifier: workflow},
    )
    assert refs[0].name == identifier and refs[0].display_name == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("caption,query", [("unsafe@reference\ncaption", "reference"), ("", "")])
async def test_canonical_unsafe_upload_uses_owned_token_and_safe_excerpt(caption, query):
    from unittest.mock import MagicMock

    from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
    from gflow_cli.api.transports.native_image_prompt import (
        NativeImageBinding,
        materialize_reference_prompt,
    )

    identifier = "11111111-1111-4111-8111-111111111111"
    plan = resolve_reference_markers(
        "Use @reference_1.",
        surface="image",
        slots={"reference_1": ReferenceSlot("image", identifier)},
    )
    composer = MagicMock()
    composer.await_existing_references = AsyncMock(return_value={identifier: "owned-token"})
    composer.clear_composer = AsyncMock()
    composer._mention_by_token = AsyncMock()
    composer._mention_by_name = AsyncMock()
    composer.read_chips = AsyncMock(return_value=[{"reference_type": "media"}])
    page = MagicMock()
    page.keyboard.insert_text = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.locator.return_value.first.evaluate = AsyncMock(return_value=True)
    await materialize_reference_prompt(
        page,
        composer,
        plan,
        {identifier: NativeImageBinding(identifier, caption)},
        {},
    )
    composer._mention_by_token.assert_awaited_once_with(
        page,
        query,
        "owned-token",
        identifier,
        expect_chips=1,
        at_end=True,
        trailing_space=False,
    )
    composer._mention_by_name.assert_not_awaited()
