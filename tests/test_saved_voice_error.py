from gflow_cli import errors

P = "00000000-0000-4000-8000-000000000001"
M = "00000000-0000-4000-8000-000000000002"
W = "00000000-0000-4000-8000-000000000003"


def test_voice_uncertainty_retains_preview_handles_without_retry():
    error = errors.VoiceMutationUnknownError(
        phase="save",
        project_id=P,
        media_id=M,
        workflow_id=W,
    )
    details = error.to_problem_details()
    assert details["outcome_unknown"] is True
    assert details["known_media_ids"] == [M]
    assert details["workflow_ids"] == [W]
    assert error.retryable is False
    assert errors.EXIT_CODE_MAP[type(error)] == 40
