import json
from pathlib import Path

import pytest

from gflow_cli.api.transports.migrated_video_upload import parse_upload_reply, validate_video

PID = "11111111-1111-4111-8111-111111111111"
MID = "22222222-2222-4222-8222-222222222222"


def test_video_upload_reply_matches_project():
    result = parse_upload_reply(
        json.dumps({"mediaId": MID, "media": {"name": MID, "projectId": PID}}), PID
    )
    assert result == MID


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"mediaId": MID, "media": {"name": MID, "projectId": MID}},
        {"mediaId": "wrong", "media": {"name": "wrong", "projectId": PID}},
        {"mediaId": MID, "media": {"name": PID, "projectId": PID}},
    ],
)
def test_video_upload_reply_rejects_unmatched(data):
    with pytest.raises(ValueError):
        parse_upload_reply(json.dumps(data), PID)


def test_validate_mp4_header(tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 24)
    validate_video(path)
    path.write_bytes(b"not a video")
    with pytest.raises(ValueError):
        validate_video(path)


def test_non_mp4_rejected(tmp_path: Path):
    path = tmp_path / "clip.txt"
    path.write_bytes(b"\x00\x00\x00\x20ftypisom")
    with pytest.raises(ValueError):
        validate_video(path)
