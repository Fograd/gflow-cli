"""Account history project summaries never infer generation from unknown origins."""

from copy import deepcopy

import pytest

from gflow_cli.api import native_history

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def history():
    rows = []
    for index, (project, kind, source, date) in enumerate(
        [
            (P, "image", "generated", "2026-01-01T00:00:00Z"),
            (P, "video", "generated", "2026-01-03T00:00:00Z"),
            (Q, "image", "generated", "2026-01-02T00:00:00Z"),
            (P, "image", "uploaded", "2026-01-04T00:00:00Z"),
            (Q, "video", "unknown", "2026-01-05T00:00:00Z"),
            (Q, "audio", "generated", "2026-01-06T00:00:00Z"),
            (Q, "unknown", "generated", "2026-01-07T00:00:00Z"),
            (Q, "image", None, "2026-01-08T00:00:00Z"),
        ]
    ):
        row = {
            "media_id": f"{index + 10:08x}-4444-4444-8444-444444444444",
            "project_id": project,
            "workflow_id": W if project == P else "44444444-3333-4333-8333-333333333333",
            "kind": kind,
            "created_time": date,
        }
        if source is not None:
            row["generation_source"] = source
        rows.append(row)
    return {
        "media": rows,
        "media_returned_count": len(rows),
        "media_scanned_count": len(rows),
        "pagination_exhausted": True,
        "next_cursor": None,
        "timed_out": False,
        "complete": None,
    }


def summarize(value):
    function = getattr(native_history, "summarize_history_projects", None)
    assert callable(function), "Missing source-backed native history project summary"
    return function(value)


def test_project_summary_counts_only_positive_generated_images_and_videos():
    value = history()
    result = summarize(value)
    assert result["project_summaries"] == [
        {
            "project_id": P,
            "total": 2,
            "by_type": {"image": 1, "video": 1},
            "oldest": "2026-01-01T00:00:00Z",
            "newest": "2026-01-03T00:00:00Z",
        },
        {
            "project_id": Q,
            "total": 1,
            "by_type": {"image": 1, "video": 0},
            "oldest": "2026-01-02T00:00:00Z",
            "newest": "2026-01-02T00:00:00Z",
        },
    ]
    assert result["scanned"] == 8
    assert result["truncated"] is False and result["cursor"] is None
    assert result["complete"] is None
    assert value == history()


def test_partial_summary_preserves_cursor_and_time_budget_without_cumulative_counts():
    value = history()
    value.update(pagination_exhausted=False, next_cursor="opaque-page-2", timed_out=True)
    result = summarize(value)
    assert result["truncated"] is True and result["cursor"] == "opaque-page-2"
    assert result["stopped_on"] == "timeBudget"
    assert summarize(value) == result
    value["pagination_exhausted"] = True
    value["timed_out"] = False
    assert summarize(value)["cursor"] is None


def test_summary_ties_sort_by_project_identity_and_missing_dates_stay_unknown():
    value = history()
    value["media"] = [value["media"][0], value["media"][2]]
    for row in value["media"]:
        row.pop("created_time")
    value.update(media_returned_count=2, media_scanned_count=2)
    rows = summarize(value)["project_summaries"]
    assert [row["project_id"] for row in rows] == [P, Q]
    assert all(row["oldest"] is None and row["newest"] is None for row in rows)


@pytest.mark.parametrize(
    "fault",
    ["media_uuid", "project_uuid", "duplicate", "timestamp", "returned", "scanned", "bool_count"],
)
def test_summary_rejects_invalid_source_metadata_and_counts(fault):
    value = deepcopy(history())
    if fault == "media_uuid":
        value["media"][0]["media_id"] = "not-a-uuid"
    elif fault == "project_uuid":
        value["media"][0]["project_id"] = "not-a-project"
    elif fault == "duplicate":
        value["media"][1]["media_id"] = value["media"][0]["media_id"]
    elif fault == "timestamp":
        value["media"][0]["created_time"] = "tomorrow"
    elif fault == "returned":
        value["media_returned_count"] = 7
    elif fault == "scanned":
        value["media_scanned_count"] = 7
    else:
        value["media_scanned_count"] = True
    with pytest.raises(ValueError):
        summarize(value)


def test_source_nanoseconds_sort_after_same_second_zero_and_scanned_can_include_unretained():
    value = history()
    value["media"] = [value["media"][0], value["media"][1]]
    value["media"][0]["created_time"] = "1970-01-01T00:00:00.000000001Z"
    value["media"][1]["created_time"] = "1970-01-01T00:00:00Z"
    value.update(media_returned_count=2, media_scanned_count=5)
    result = summarize(value)
    row = result["project_summaries"][0]
    assert row["oldest"] == "1970-01-01T00:00:00Z"
    assert row["newest"] == "1970-01-01T00:00:00.000000001Z"
    assert result["scanned"] == 5


@pytest.mark.parametrize(
    "field,value", [("pagination_exhausted", 1), ("timed_out", 0), ("media_scanned_count", 1001)]
)
def test_summary_rejects_coerced_flags_and_out_of_budget_scanned(field, value):
    source = history()
    source[field] = value
    with pytest.raises(ValueError):
        summarize(source)


def test_summary_rejects_one_workflow_claiming_two_projects():
    source = history()
    source["media"][2]["workflow_id"] = source["media"][0]["workflow_id"]
    with pytest.raises(ValueError):
        summarize(source)


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "generated,uploaded,expected",
    [
        ([["positive"]], None, "generated"),
        (None, [["positive"]], "uploaded"),
        ([], None, "unknown"),
        (None, [], "unknown"),
        ([["positive"]], [["positive"]], "unknown"),
        ([["positive"]], [], "unknown"),
        ([["positive"]], "malformed", "unknown"),
    ],
)
def test_parser_origin_requires_positive_exclusive_native_union(
    kind, generated, uploaded, expected
):
    media_id = "55555555-5555-4555-8555-555555555555"
    row = [media_id, P, W, None, None, [[0, 1]], None, None]
    arm = [generated, uploaded] if kind == "image" else [generated, None, None, None, uploaded]
    row[6 if kind == "image" else 7] = arm
    payload = [[[W, None, None, [], P]], None, [row]]
    result = native_history.parse_history_page(payload)
    assert result["media"][0]["generation_source"] == expected
    assert result["media"][0]["created_time"] == "1970-01-01T00:00:00.000000001Z"
