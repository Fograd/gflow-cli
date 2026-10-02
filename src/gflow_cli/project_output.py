"""Shared interface-only formatting for local project catalog rows."""

from __future__ import annotations

from typing import Any

from gflow_cli.api import routes
from gflow_cli.data.queries import ProjectRow
from gflow_cli.profile_store import account_locale_for


def local_project_payload(row: ProjectRow) -> dict[str, Any]:
    """Preserve the local CLI/MCP wire fields and account-correct editor URL."""
    return {
        "project_id": row.project_id,
        "title": row.title,
        "profile": row.profile,
        "created_at": row.created_at.isoformat(),
        "image_count": row.image_count,
        "video_count": row.video_count,
        "url": routes.project_editor_url_or_none(account_locale_for(row.profile), row.project_id),
    }
