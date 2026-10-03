import pytest

from gflow_cli._cli_helpers import _exit_code_for
from gflow_cli.errors import NativeMediaMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def test_safe_known_handles_and_nonretryable_unknown():
    error = NativeMediaMutationUnknownError(
        operation="archive",
        phase="response",
        project_id=P,
        known_media_ids=(M,),
        pending_media_ids=(),
    )
    value = error.to_problem_details()
    assert value["outcome_unknown"] is True
    assert value["known_media_ids"] == [M]
    assert error.retryable is False
    assert _exit_code_for(error) == 40
    assert "http" not in str(error)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation": "other"},
        {"phase": "raw exception"},
        {"project_id": "bad"},
        {"known_media_ids": ("https://private/token",)},
        {"pending_media_ids": (M,) * 101},
    ],
)
def test_invalid_recovery_metadata_refused(kwargs):
    args = dict(operation="upload", phase="dispatch", project_id=P)
    args.update(kwargs)
    with pytest.raises(ValueError):
        NativeMediaMutationUnknownError(**args)
