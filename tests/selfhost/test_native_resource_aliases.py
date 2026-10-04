"""Resource alias registries preserve exact opaque mappings, never ownership proof."""

import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from gflow_cli.selfhost.native_resource_aliases import (
    NativeResourceAlias,
    NativeResourceAliasStore,
    resource_alias_spec,
)

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
C = "user:opaque-email:opaque-character:" + E + "-imgs:2-voice:" + W
V = "user:opaque-email:opaque-voice:" + W + "-mid:" + M


def character():
    return NativeResourceAlias(
        C, "pro1", "one", P, "character", E, image_count=2, voice_workflow_id=W
    )


def voice():
    return NativeResourceAlias(V, "pro1", "one", P, "voice", M, workflow_id=W)


def test_character_and_voice_suffixes_have_distinct_identities():
    c = resource_alias_spec(C)
    assert (c.kind, c.native_id, c.image_count, c.voice_workflow_id, c.workflow_id) == (
        "character",
        E,
        2,
        W,
        None,
    )
    v = resource_alias_spec(V)
    assert (v.kind, v.native_id, v.workflow_id, v.image_count) == ("voice", M, W, None)
    assert resource_alias_spec(C.split("-voice:")[0]).voice_workflow_id is None


@pytest.mark.parametrize(
    "alias",
    [
        E,
        C.replace("imgs:2", "imgs:0"),
        C.replace("imgs:2", "imgs:3"),
        C.replace(E, "bad"),
        C + "?x=1",
        C + "/",
        C + "\\n",
        C.replace("opaque", "é", 1),
        V.replace("-mid:", "-audio:"),
        V.replace(W, "bad"),
        C.replace("user:opaque", "user:"),
        C.replace("email:opaque", "email:"),
    ],
)
def test_bad_resource_alias_policy(alias):
    with pytest.raises(ValueError):
        resource_alias_spec(alias)


@pytest.mark.parametrize(
    "changes",
    [
        {"native_id": M},
        {"image_count": 1},
        {"voice_workflow_id": M},
        {"workflow_id": W},
        {"kind": "voice"},
        {"profile": "../bad"},
        {"account": "bad\\n"},
    ],
)
def test_binding_suffix_mismatch_refused_before_registry(tmp_path, changes):
    store = NativeResourceAliasStore(tmp_path)
    with pytest.raises(ValueError):
        store.register(replace(character(), **changes))
    assert store.get(C) is None


def test_persistence_idempotence_exactmatch_and_privacy(tmp_path):
    store = NativeResourceAliasStore(tmp_path)
    for item in (character(), voice()):
        store.register(item)
        store.register(item)
        assert NativeResourceAliasStore(tmp_path).get(item.alias) == item
        assert item.alias not in repr(item)
    assert store.get(C.replace("user:opaque", "user:unknown")) is None
    with pytest.raises(ValueError):
        store.get(E)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_concurrent_conflict_preserves_one_exact_binding(tmp_path):
    store = NativeResourceAliasStore(tmp_path)
    candidates = [character(), replace(character(), account="two")]

    def register(item):
        try:
            store.register(item)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, candidates))
    assert sorted(results) == [False, True]
    assert store.get(C) in candidates


def test_scoped_local_remove_and_conflict(tmp_path):
    store = NativeResourceAliasStore(tmp_path)
    store.register(voice())
    with pytest.raises(ValueError):
        store.register(replace(voice(), project_id=E))
    with pytest.raises(ValueError):
        store.remove(V, "pro2", "one")
    with pytest.raises(ValueError):
        store.remove(V, "pro1", "two")
    assert store.remove(V, "pro1", "one") is True
    assert store.remove(V, "pro1", "one") is False


@pytest.mark.parametrize(
    "alias",
    [
        C.replace("user:opaque", "user:" + "x" * 129),
        C.replace("email:opaque", "email:" + "x" * 513),
    ],
)
def test_resource_alias_component_bounds(alias):
    with pytest.raises(ValueError):
        resource_alias_spec(alias)


def test_boolean_image_count_is_not_a_valid_binding(tmp_path):
    alias = C.replace("imgs:2", "imgs:1")
    item = replace(character(), alias=alias, image_count=True)
    with pytest.raises(ValueError):
        NativeResourceAliasStore(tmp_path).register(item)


def test_concurrent_identical_resource_alias_registration(tmp_path):
    store = NativeResourceAliasStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.register, [voice()] * 8))
    assert store.get(V) == voice()


@pytest.mark.parametrize("unsafe", ["directory", "file", "symlink"])
def test_resource_alias_storage_refuses_unsafe_paths(tmp_path, unsafe):
    if unsafe == "directory":
        tmp_path.chmod(0o755)
    elif unsafe == "file":
        NativeResourceAliasStore(tmp_path)
        (tmp_path / "resource_aliases.sqlite3").chmod(0o644)
    else:
        target = tmp_path / "target"
        target.touch(mode=0o600)
        (tmp_path / "resource_aliases.sqlite3").symlink_to(target)
    with pytest.raises(ValueError):
        NativeResourceAliasStore(tmp_path)
