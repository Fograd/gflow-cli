"""Reference an image already in the project, with no upload (#913, PLAN Task 5).

Modelled on the measured surface (docs/superpowers/spikes/2026-10-01-batch-ref-dropped.md
§ Gate): `@` opens a picker dialog whose options carry a thumbnail `/asb/<token>`; the
project grid tile `img[data-media-id=<uuid>]` carries the same token. Captions collide
(the picker listed the older of two "a single red apple" first), so the option is chosen
by token, never by caption or position.
"""

from __future__ import annotations

from typing import Any

import pytest

from gflow_cli.api.image import Aspect, GenerateImageRequest, ImageRef, Model
from gflow_cli.api.transports.migrated_composer import (
    PICKER_OPTION,
    MigratedComposer,
    _guard_image_submit,
    _unported_image_form,
)
from gflow_cli.errors import ReferenceNotFoundError

PARENT = "3f4272fd-2897-4621-b0cd-0fb9576758d3"
OTHER = "90879017-ff54-4232-9186-f6a61298a6cc"


class _Loc:
    def __init__(self, page: FakePage, kind: str) -> None:
        self.page, self.kind = page, kind

    @property
    def first(self) -> _Loc:
        return self

    async def click(self, **_: Any) -> None:
        if self.kind == "composer":
            self.page.composer_clicks += 1


class _Keyboard:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def type(self, text: str, **_: Any) -> None:
        self.page.typed.append(text)
        if text == "@":
            self.page.dialog_open = True
            self.page.active = 0

    async def press(self, key: str) -> None:
        self.page.typed.append(f"<{key}>")
        if key == "ArrowDown":
            self.page.active += 1
        elif key == "Escape":
            self.page.dialog_open = False
        elif key == "Enter" and self.page.dialog_open:
            options = self.page.options()
            if self.page.active < len(options):
                self.page.bound.append(options[self.page.active][1])
                self.page.chips.append({"text": "x", "entity_id": "", "reference_type": "media"})
            self.page.dialog_open = False


class FakePage:
    def __init__(
        self,
        *,
        grid: dict[str, str],
        options: list[tuple[str, str]],
        miss_first: int = 0,
    ) -> None:
        self.keyboard = _Keyboard(self)
        self.grid = grid
        self._options = options
        self.miss_first = miss_first
        self.searches = 0
        self.typed: list[str] = []
        self.chips: list[dict[str, str]] = []
        self.bound: list[str] = []
        self.dialog_open = False
        self.active = 0
        self.composer_clicks = 0

    def options(self) -> list[tuple[str, str]]:
        return [] if self.searches <= self.miss_first else self._options

    def locator(self, css: str) -> _Loc:
        if css == "[contenteditable='true']":
            return _Loc(self, "composer")
        raise AssertionError(f"unmodelled selector: {css!r}")

    async def wait_for_timeout(self, _ms: float) -> None:
        return None

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if "data-media-id" in script:
            return self.grid.get(arg, "")
        if arg == PICKER_OPTION:
            self.searches += 1
            return [token for _caption, token in self.options()]
        return self.chips


def _ref(display_name: str = "a single red apple") -> ImageRef:
    return ImageRef(name=PARENT, display_name=display_name)


async def test_the_option_is_chosen_by_token_when_captions_collide() -> None:
    page: Any = FakePage(
        grid={PARENT: "tokNew", OTHER: "tokOld"},
        options=[("a single red apple", "tokOld"), ("a single red apple", "tokNew")],
    )
    ids = await MigratedComposer().attach_existing_references(page, (_ref(),))
    assert ids == (PARENT,)
    assert page.bound == ["tokNew"]
    assert page.typed.count("<ArrowDown>") == 1


async def test_a_parent_missing_from_the_grid_is_refused_before_searching() -> None:
    page: Any = FakePage(grid={}, options=[("a single red apple", "tokNew")])
    with pytest.raises(ReferenceNotFoundError, match=PARENT):
        await MigratedComposer().attach_existing_references(page, (_ref(),))
    assert "<Enter>" not in page.typed


async def test_a_late_index_is_retried_after_closing_the_dialog() -> None:
    page: Any = FakePage(grid={PARENT: "tokNew"}, options=[("c", "tokNew")], miss_first=1)
    ids = await MigratedComposer().attach_existing_references(page, (_ref("c"),))
    assert ids == (PARENT,)
    # The dialog covers the composer: a retry that does not close it first cannot click.
    first_escape = page.typed.index("<Escape>")
    second_at = [i for i, t in enumerate(page.typed) if t == "@"][1]
    assert first_escape < second_at


async def test_no_matching_option_is_refused_without_binding_anything() -> None:
    page: Any = FakePage(grid={PARENT: "tokNew"}, options=[("c", "tokOld")])
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().attach_existing_references(page, (_ref("c"),))
    assert page.bound == []
    assert "<Enter>" not in page.typed


@pytest.mark.parametrize("caption", ["two\nlines", "say @hi", "", "   "])
async def test_an_unusable_caption_is_refused_before_typing(caption: str) -> None:
    page: Any = FakePage(grid={PARENT: "tokNew"}, options=[(caption, "tokNew")])
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().attach_existing_references(page, (_ref(caption),))
    assert page.typed == []


def _req(**kw: Any) -> GenerateImageRequest:
    return GenerateImageRequest(
        prompt="p", aspect=Aspect.from_cli("1:1"), model=Model.from_cli("nano2"), **kw
    )


def test_only_a_captioned_reference_is_ported(tmp_path: Any) -> None:
    assert _unported_image_form(_req(refs=(_ref(),))) is None
    assert _unported_image_form(_req(refs=(ImageRef(name=PARENT),))) is not None
    local = tmp_path / "x.png"
    local.write_bytes(b"\x89PNG")
    assert _unported_image_form(_req(refs=(_ref(),), ref_paths=(local,))) is not None


class _Route:
    def __init__(self) -> None:
        self.aborted = False
        self.continued = False

    async def abort(self, *_: Any) -> None:
        self.aborted = True

    async def continue_(self, **_: Any) -> None:
        self.continued = True


class _Request:
    def __init__(self, body: str) -> None:
        self.post_data = body


async def test_a_submit_missing_its_reference_is_aborted_before_flow_acts() -> None:
    route = _Route()
    problem = await _guard_image_submit(route, _Request("ogiZ0b no ids here"), (PARENT,), None)
    assert problem is not None and PARENT in problem
    assert route.aborted and not route.continued


async def test_a_submit_carrying_its_reference_goes_through() -> None:
    route = _Route()
    problem = await _guard_image_submit(route, _Request(f"ogiZ0b {PARENT}"), (PARENT,), None)
    assert problem is None
    assert route.continued and not route.aborted
