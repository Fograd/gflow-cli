"""Exact locally registered aliases for read-only native resource lookup.

Registration routes account selection; fresh Google reads still prove ownership.
Opaque vendor prefixes are never decoded, and UUID-only installations need no store.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.config import environment_root
from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore, alias_spec
from gflow_cli.selfhost.native_resource_aliases import (
    NativeResourceAlias,
    NativeResourceAliasStore,
    resource_alias_spec,
)
from gflow_cli.selfhost.store import Store

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient

Kind = Literal["media", "character", "voice"]
Binding = NativeAlias | NativeResourceAlias


def validate_lookup(value: str, kind: Kind) -> None:
    try:
        validate_identifier(value)
        return
    except ValueError:
        pass
    try:
        if kind == "media":
            alias_spec(value)
        elif resource_alias_spec(value).kind != kind:
            raise ValueError("Alias resource kind does not match lookup")
    except ValueError:
        raise ConfigurationError(
            detail="Lookup requires a native UUID or an exact registered composite alias; "
            "unknown UseAPI references cannot be decoded by assumption"
        ) from None


def resolve_lookup(profile: str, project: str, value: str, kind: Kind) -> Binding | None:
    validate_lookup(value, kind)
    try:
        validate_identifier(value)
        return None
    except ValueError:
        pass
    root = environment_root()
    filename = "aliases.sqlite3" if kind == "media" else "resource_aliases.sqlite3"
    if not (root / filename).is_file() or not (root / "jobs.sqlite3").is_file():
        raise ConfigurationError(
            detail="Composite reference has no registered mapping on this host"
        )
    store = Store(root)
    aliases = (
        NativeAliasStore(root, resolve_scope=store.resolve_profile_scope)
        if kind == "media"
        else NativeResourceAliasStore(root, resolve_scope=store.resolve_profile_scope)
    )
    binding = aliases.get(value)
    if binding is None:
        raise ConfigurationError(detail="Composite reference has no exact registered mapping")
    try:
        project = validate_identifier(project)
    except ValueError:
        raise ConfigurationError(
            detail="Alias lookup requires an explicit native project UUID"
        ) from None
    if (
        binding.profile != profile
        or binding.project_id != project
        or store.resolve_profile_scope(binding.profile, binding.account) != profile
    ):
        raise ConfigurationError(
            detail="Registered alias does not belong to the selected "
            "enabled account/profile and project"
        )
    return binding


def resolve_client_lookup(
    client: FlowApiClient, project: str, value: str, kind: Kind
) -> Binding | None:
    validate_lookup(value, kind)
    try:
        validate_identifier(value)
        return None
    except ValueError:
        pass
    root = environment_root()
    if not (root / "jobs.sqlite3").is_file():
        raise ConfigurationError(detail="Composite reference has no registered account mapping")
    profiles = [
        row["profile"]
        for row in Store(root).accounts()
        if row["enabled"] == 1
        and row["verified"] == 1
        and client.settings.profile_subdir(row["profile"]).resolve()
        == Path(client.profile_dir).resolve()
    ]
    if len(profiles) != 1:
        raise ConfigurationError(
            detail="Alias lookup requires an explicitly selected registered profile"
        )
    return resolve_lookup(profiles[0], project, value, kind)


def verify_resource(binding: Binding | None, row: dict[str, Any]) -> None:
    if binding is None:
        return
    if not isinstance(binding, NativeResourceAlias):
        raise ConfigurationError(detail="Resource alias kind mismatch")
    identity = "ref" if binding.kind == "voice" else "entity_id"
    valid = row.get("project_id") == binding.project_id and row.get(identity) == binding.native_id
    if binding.kind == "voice":
        valid = valid and row.get("workflow_id") == binding.workflow_id
    else:
        images = row.get("image_references")
        valid = (
            valid
            and isinstance(images, list)
            and len(cast(list[Any], images)) == binding.image_count
        )
        if binding.voice_workflow_id is not None:
            voice = row.get("voice_detail")
            valid = (
                valid
                and isinstance(voice, dict)
                and (
                    cast(dict[str, Any], voice).get("source") == "user"
                    and cast(dict[str, Any], voice).get("project_id") == binding.project_id
                    and cast(dict[str, Any], voice).get("workflow_id") == binding.voice_workflow_id
                )
            )
    if not valid:
        raise ConfigurationError(
            detail="Fresh native resource detail does not match registered alias"
        )
