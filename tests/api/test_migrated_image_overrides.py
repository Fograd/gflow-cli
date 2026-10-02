import json
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, rewrite_submit
from gflow_cli.errors import WireFormatError

PROJECT = "11111111-1111-4111-8111-111111111111"


def body(count=1):
    context = [None] * 11
    context[5] = PROJECT
    context[10] = ["browser-token" * 5, 1]
    rows = [[None, None, None, 42, 1, "NARWHAL", None, context.copy()] for _ in range(count)]
    args = [None, rows, count, context, ["batch"]]
    return urlencode(
        {"f.req": json.dumps([[["ogiZ0b", json.dumps(args), None, "generic"]]]), "at": "auth-field"}
    )


def test_seed_and_token_rewrite_preserves_all_other_fields():
    original = body(2)
    result = rewrite_submit(original, project=PROJECT, count=2, seed=0, token="provided-token" * 5)
    args = json.loads(json.loads(parse_qs(result)["f.req"][0])[0][0][1])
    assert [row[3] for row in args[1]] == [0, 1]
    assert args[3][10][0] == "provided-token" * 5
    assert all(row[7][10][0] == "provided-token" * 5 for row in args[1])
    assert parse_qs(result)["at"] == ["auth-field"]
    assert args[1][0][5] == "NARWHAL"


@pytest.mark.parametrize("project,count", [("wrong", 1), (PROJECT, 2)])
def test_wrong_project_or_count_is_refused(project, count):
    with pytest.raises(WireFormatError):
        rewrite_submit(body(), project=project, count=count, seed=3)


def test_corrupt_shape_or_duplicate_form_fields_is_refused():
    for value in ["bad", body() + "&f.req=other"]:
        with pytest.raises(WireFormatError):
            rewrite_submit(value, project=PROJECT, count=1, seed=3)


@pytest.mark.asyncio
async def test_override_is_single_use_and_no_implicit_replay():
    override = ImageOverrides(PROJECT, 1, seed=3)
    await override.apply(None, body())
    with pytest.raises(WireFormatError):
        await override.apply(None, body())
