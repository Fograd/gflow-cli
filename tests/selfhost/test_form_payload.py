"""Text-only multipart matches JSON contracts and refuses ambiguous/private files."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_account_scheduler import configuration
from tests.selfhost.test_job_statistics import AUTH


def form(client, fields, path="/v1/google-flow/images"):
    return client.post(path, headers=AUTH, files=fields)


def test_multipart_image_matches_existing_json_handler(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = form(
            client,
            [
                ("prompt", (None, "A blue circle")),
                ("count", (None, "2")),
                ("async", (None, "true")),
                ("email", (None, "public-one")),
            ],
        )
        assert response.status_code == 201, response.text
        with client.app.state.store.connection() as conn:
            row = conn.execute(
                "SELECT profile,payload FROM jobs WHERE id=?", (response.json()["jobId"],)
            ).fetchone()
        assert row["profile"] == "one"
        payload = json.loads(row["payload"])
        assert payload["prompt"] == "A blue circle"
        assert payload["count"] == 2


@pytest.mark.parametrize(
    "fields",
    [
        [("prompt", (None, "one")), ("prompt", (None, "two"))],
        [("prompt", ("private.txt", "one"))],
        [("prompt", (None, "one")), ("count", (None, "NaN"))],
        [("prompt", (None, "one")), ("async", (None, "yes"))],
        [("prompt", (None, "one")), ("count", (None, "true"))],
    ],
)
def test_multipart_ambiguity_refuses_before_queue(tmp_path, fields):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = form(client, fields)
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []


def test_malformed_multipart_refuses_without_echoing_body(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers={**AUTH, "Content-Type": "multipart/form-data; boundary=fixture"},
            content=b"private-body-with-no-delimiter",
        )
        assert response.status_code == 422
        assert "private-body" not in response.text
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("value", [[], "secret", 1, None])
def test_json_non_object_preserves_prequeue_refusal(tmp_path, value):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers={**AUTH, "Content-Type": "application/json"},
            content=json.dumps(value),
        )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []


def test_json_types_are_not_coerced_by_form_transport(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "fixture", "count": "2", "async": True},
        )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []


def test_media_form_decodes_only_documented_json_collection(tmp_path):
    from gflow_cli.selfhost.form_payload import form_value

    assert form_value("media", '[{"mediaGenerationId":"fixture","trimStart":0}]') == [
        {"mediaGenerationId": "fixture", "trimStart": 0}
    ]
    assert form_value("prompt", '{"secret":"literal"}') == '{"secret":"literal"}'
    assert form_value("cookies", "Name\tValue\nprivate") == "Name\tValue\nprivate"


def test_capabilities_declare_current_provider_and_form_scope(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.get("/v1/google-flow/capabilities", headers=AUTH)
        assert response.status_code == 200
        value = response.json()
        assert "requests/multipart-text-fields" in value["implemented"]
        assert "images/provider-captcha-generation" in value["implemented"]
        assert "images/provider-captcha-generation" not in value["notImplemented"]
        assert "captcha-google-refusal-retries" not in value["notImplemented"]
        assert "captcha-provider-google-acceptance" in value["verificationPending"]


def test_multipart_supplied_token_stays_offqueue_and_offpublic_response(tmp_path):
    token = "synthetic-provider-token-" * 3
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = form(
            client,
            [
                ("prompt", (None, "fixture")),
                ("count", (None, "1")),
                ("async", (None, "true")),
                ("captchaToken", (None, token)),
            ],
        )
        assert response.status_code == 201 and token not in response.text
        with client.app.state.store.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM jobs WHERE id=?", (response.json()["jobId"],)
            ).fetchone()
        assert token not in row["payload"] and "captchaToken" not in row["payload"]
        files = list((tmp_path / "captcha-input").glob("*.token"))
        assert len(files) == 1 and files[0].read_text() == token
        assert files[0].stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "content_type,disposition",
    [
        ("multipart/form-data; boundary=fixture", "form-data; name=prompt;name=email"),
        ("multipart/form-data; boundary=fixture", 'form-data; name="prompt'),
        ("multipart/form-data; boundary=fixture;boundary=other", "form-data; name=prompt"),
    ],
)
def test_multipart_header_parameter_defects_refuse_before_queue(
    tmp_path, content_type, disposition
):
    body = (
        "--fixture\r\nContent-Disposition: "
        + disposition
        + "\r\n\r\nprivate-fixture\r\n--fixture--\r\n"
    ).encode()
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers={**AUTH, "Content-Type": content_type},
            content=body,
        )
        assert response.status_code == 422
        assert "private-fixture" not in response.text
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("kind", ["multipart", "json"])
def test_excessive_json_nesting_refuses_before_queue(tmp_path, kind):
    deep = "[" * 2000 + "0" + "]" * 2000
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        if kind == "multipart":
            response = form(client, [("prompt", (None, "fixture")), ("media", (None, deep))])
        else:
            response = client.post(
                "/v1/google-flow/images",
                headers={**AUTH, "Content-Type": "application/json"},
                content='{"prompt":"fixture","media":' + deep + "}",
            )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []


def test_openapi_preserves_json_and_text_form_body_contracts(tmp_path):
    schema = create_app(configuration(tmp_path), start_workers=False).openapi()
    for path in (
        "/v1/google-flow/images",
        "/v1/google-flow/videos",
        "/v1/google-flow/accounts/captcha-providers",
    ):
        body = schema["paths"][path]["post"]["requestBody"]
        assert body["required"] is True
        assert set(body["content"]) == {"application/json", "multipart/form-data"}
        assert body["content"]["application/json"]["schema"]["type"] == "object"
        assert body["content"]["multipart/form-data"]["schema"]["additionalProperties"] == {
            "type": "string"
        }


@pytest.mark.parametrize(
    "name,raw,expected",
    [("localOnly", "true", True), ("startFrameIndex_1", "0", 0), ("endFrameIndex_1", "240", 240)],
)
def test_existing_route_typed_form_fields_preserve_json_types(name, raw, expected):
    from gflow_cli.selfhost.form_payload import form_value

    result = form_value(name, raw)
    assert result == expected and type(result) is type(expected)


def test_multipart_local_only_delete_matches_json_without_remote_job(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        response = client.request(
            "DELETE",
            "/v1/google-flow/assets/public-one",
            headers=AUTH,
            files=[("mediaGenerationIds", (None, "[]")), ("localOnly", (None, "true"))],
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "deleted": [],
            "scope": "local-cache",
            "googleLibraryModified": False,
        }
        assert client.app.state.store.jobs() == []


def test_every_form_enabled_route_has_both_openapi_body_formats(tmp_path):
    from fastapi.routing import APIRoute

    from gflow_cli.selfhost.form_payload import parse_payload

    app = create_app(configuration(tmp_path), start_workers=False)
    schema = app.openapi()
    observed = 0
    for route in app.routes:
        if isinstance(route, APIRoute) and any(
            dependency.call is parse_payload for dependency in route.dependant.dependencies
        ):
            for method in route.methods:
                body = schema["paths"][route.path][method.lower()]["requestBody"]
                assert set(body["content"]) == {"application/json", "multipart/form-data"}
                assert body["required"] is True
                observed += 1
    assert observed >= 18
