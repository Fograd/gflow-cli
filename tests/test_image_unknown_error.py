"""A dispatched image outcome is never retryable."""

from gflow_cli.errors import EXIT_CODE_MAP, ImageGenerationUnknownError, is_retryable

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def test_unknown_image_preserves_safe_handles_and_refuses_retry():
    error = ImageGenerationUnknownError(
        project_id=P, media_ids=(M,), workflow_ids=(W,), phase="image_response"
    )
    assert EXIT_CODE_MAP[type(error)] == 40
    assert not is_retryable(error)
    detail = error.to_problem_details()
    assert detail["outcome_unknown"] is True
    assert detail["project_id"] == P
    assert detail["media_ids"] == [M]
    assert detail["workflow_ids"] == [W]


def test_unknown_image_without_handles_is_still_nonretryable():
    error = ImageGenerationUnknownError()
    assert not is_retryable(error)
    detail = error.to_problem_details()
    assert detail["outcome_unknown"] is True
    assert "media_ids" not in detail
    assert "workflow_ids" not in detail
