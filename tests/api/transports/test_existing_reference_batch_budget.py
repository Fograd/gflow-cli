"""Exercise measured picker waits without browser, Google or generation calls."""

import asyncio
from types import SimpleNamespace

import pytest

from gflow_cli.api.image import GenerateImageRequest, ImageRef, Model
from gflow_cli.api.transports import migrated_composer as subject
from gflow_cli.errors import ConfigurationError, ReferenceNotFoundError


class Keyboard:
    def __init__(self, page):
        self.page = page

    async def type(self, text, *, delay):
        self.page.requested_ms += len(text) * delay
        await asyncio.sleep(len(text) * delay / 100_000)
        if text == "@":
            self.page.query = ""
        elif text != " ":
            self.page.query += text

    async def press(self, key):
        if key == "Enter":
            options = self.page.options()
            assert len(options) == 1
            self.page.bound.append(options[0])
            self.page.chips.append({"reference_type": "media"})


class Page:
    def __init__(self, refs, *, ambiguous=False):
        self.grid = {ref.name: f"owned-token-{i}" for i, ref in enumerate(refs)}
        self.queries = {ref.display_name: self.grid[ref.name] for ref in refs}
        self.query = ""
        self.ambiguous = ambiguous
        self.bound = []
        self.chips = []
        self.requested_ms = 0
        self.reloads = 0
        self.keyboard = Keyboard(self)

    @property
    def first(self):
        return self

    def locator(self, selector):
        assert selector == subject.COMPOSER
        return self

    async def click(self, **kwargs):
        pass

    def options(self):
        token = self.queries.get(self.query)
        return ([token] * (2 if self.ambiguous else 1)) if token else []

    async def wait_for_timeout(self, ms):
        self.requested_ms += ms
        await asyncio.sleep(ms / 100_000)

    async def reload(self, **kwargs):
        self.reloads += 1
        self.chips.clear()

    async def evaluate(self, script, arg=None):
        if isinstance(arg, dict):
            if arg["action"] == "restore":
                return True
            return {"valid": True, "tokens": self.grid, "can_scroll": False, "moved": False}
        if arg == subject.PICKER_OPTION:
            return self.options()
        return self.chips


def request(count, caption_length=40):
    refs = tuple(
        ImageRef(
            f"00000000-0000-4000-8000-{i + 1:012d}",
            display_name=f"reference-{i:02d}".ljust(caption_length, "x"),
            in_project=True,
        )
        for i in range(count)
    )
    return GenerateImageRequest(prompt="x", model=Model.from_cli("nano2"), refs=refs)


def composer():
    instance = subject.MigratedComposer()

    async def ready(*args):
        pass

    instance.ensure_editor = ready
    instance.apply_image_settings = ready
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize("caption_length", [40, 120])
async def test_ten_owned_exact_references_complete_measured_waits_in_order(
    monkeypatch, caption_length
):
    monkeypatch.setattr(subject, "EXISTING_REF_WAIT_S", 0.9)  # real waits scaled 100x
    monkeypatch.setattr(subject, "_EXISTING_REF_EXTRA_S", 0.2)
    req = request(10, caption_length)
    page = Page(req.refs)
    attached = await composer().reference_existing(page, "project", req)
    assert attached == tuple(ref.name for ref in req.refs)
    assert page.bound == [f"owned-token-{i}" for i in range(10)]
    assert page.requested_ms == 74_000 + 1000 * caption_length
    assert page.reloads == 0


@pytest.mark.asyncio
async def test_one_reference_keeps_existing_budget_and_exact_selection(monkeypatch):
    monkeypatch.setattr(subject, "EXISTING_REF_WAIT_S", 0.9)
    req = request(1)
    page = Page(req.refs)
    assert await composer().reference_existing(page, "project", req) == (req.refs[0].name,)
    assert page.bound == ["owned-token-0"]


@pytest.mark.asyncio
async def test_ambiguous_picker_token_never_attaches_or_renews_deadline(monkeypatch):
    monkeypatch.setattr(subject, "EXISTING_REF_WAIT_S", 0.08)
    monkeypatch.setattr(subject, "_EXISTING_REF_EXTRA_S", 0.02)
    req = request(10)
    page = Page(req.refs, ambiguous=True)
    with pytest.raises(ReferenceNotFoundError, match="overall deadline"):
        await asyncio.wait_for(composer().reference_existing(page, "project", req), 1.5)
    assert page.bound == []
    assert page.reloads >= 1


def test_count_aware_deadline_retains_one_and_is_bounded_at_ten():
    assert subject._existing_reference_budget(()) == 90
    assert subject._existing_reference_budget(request(1).refs) == 90
    assert subject._existing_reference_budget(request(10).refs) == 270


@pytest.mark.asyncio
async def test_over_cap_refuses_before_page_interaction():
    req = SimpleNamespace(refs=tuple(ImageRef(str(i)) for i in range(11)))
    with pytest.raises(ConfigurationError, match="at most 10"):
        await composer().reference_existing(None, "project", req)
