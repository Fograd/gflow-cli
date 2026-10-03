"""Opaque native aliases bind exact identities without decoding account prefixes."""

import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore, alias_spec

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
A = "user:opaque_user-email:opaque-email-image:" + M


def binding():
    return NativeAlias(A, "pro1", "account-one", P, M, "image")


@pytest.mark.parametrize(
    "value",
    [
        M,
        "reserved",
        A + "?x=1",
        A + "/",
        A + "\n",
        A.replace("opaque_user", ""),
        A.replace("opaque-email", ""),
        A.replace("image:", "audio:"),
        A.replace("opaque_user", "é"),
        "user:" + "x" * 129 + "-email:e-image:" + M,
    ],
)
def test_alias_policy_refuses_invalid(value):
    with pytest.raises(ValueError):
        alias_spec(value)


def test_alias_spec_keeps_prefix_opaque_and_returns_canonical_identity():
    assert alias_spec(A) == ("image", M)
    assert alias_spec(A.replace(M, M.upper())) == ("image", M)


@pytest.mark.parametrize(
    "change",
    [
        {"media_id": W},
        {"kind": "video"},
        {"project_id": "bad"},
        {"profile": "../other"},
        {"account": "bad\naccount"},
    ],
)
def test_binding_validation_inside_boundary(tmp_path, change):
    store = NativeAliasStore(tmp_path)
    with pytest.raises(ValueError):
        store.register(replace(binding(), **change))
    assert store.get(A) is None


def test_idempotence_persistence_privacy_and_exact_lookup(tmp_path):
    store = NativeAliasStore(tmp_path)
    store.register(binding())
    store.register(binding())
    assert NativeAliasStore(tmp_path).get(A) == binding()
    assert store.get(A.replace("opaque_user", "other_user")) is None
    with pytest.raises(ValueError):
        store.get(M)
    assert A not in repr(binding()) and "account-one" not in repr(binding())
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "change", [{"profile": "pro2"}, {"account": "account-two"}, {"project_id": W}]
)
def test_conflicting_binding_cannot_replace_existing(tmp_path, change):
    store = NativeAliasStore(tmp_path)
    store.register(binding())
    with pytest.raises(ValueError):
        store.register(replace(binding(), **change))
    assert store.get(A) == binding()


def test_concurrent_conflict_has_exactly_one_winner(tmp_path):
    store = NativeAliasStore(tmp_path)
    candidates = [binding(), replace(binding(), profile="pro2")]

    def register(item):
        try:
            store.register(item)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(register, candidates))
    assert sorted(outcomes) == [False, True]
    assert store.get(A) in candidates


def test_remove_is_local_and_scope_checked(tmp_path):
    store = NativeAliasStore(tmp_path)
    store.register(binding())
    with pytest.raises(ValueError):
        store.remove(A, "pro2", "account-one")
    with pytest.raises(ValueError):
        store.remove(A, "pro1", "other-account")
    assert store.get(A) == binding()
    assert store.remove(A, "pro1", "account-one") is True
    assert store.remove(A, "pro1", "account-one") is False


def test_concurrent_identical_registration_is_idempotent(tmp_path):
    store = NativeAliasStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.register, [binding()] * 8))
    assert store.get(A) == binding()


@pytest.mark.parametrize(
    "unsafe", ["directory-permissions", "database-permissions", "database-symlink"]
)
def test_storage_rejects_insecure_paths(tmp_path, unsafe):
    if unsafe == "directory-permissions":
        tmp_path.chmod(0o755)
    elif unsafe == "database-permissions":
        NativeAliasStore(tmp_path)
        (tmp_path / "aliases.sqlite3").chmod(0o644)
    else:
        target = tmp_path / "other.sqlite3"
        target.touch(mode=0o600)
        (tmp_path / "aliases.sqlite3").symlink_to(target)
    with pytest.raises(ValueError):
        NativeAliasStore(tmp_path)
