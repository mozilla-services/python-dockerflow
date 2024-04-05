# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockerflow import checks
from dockerflow.fastapi import router as dockerflow_router
from dockerflow.fastapi.middleware import (
    MozlogRequestSummaryLogger,
    RequestIdMiddleware,
)
from dockerflow.logging import JsonLogFormatter, RequestIdLogFilter


def create_app():
    app = FastAPI()
    app.include_router(dockerflow_router)
    app.add_middleware(MozlogRequestSummaryLogger)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    return TestClient(app)


def test_lbheartbeat_get(client):
    response = client.get("/__lbheartbeat__")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lbheartbeat_head(client):
    response = client.head("/__lbheartbeat__")
    assert response.status_code == 200
    assert response.content == b""


def test_mozlog_record_formatted_as_json(app, client, capsys):
    app.state.DOCKERFLOW_SUMMARY_LOG_QUERYSTRING = True

    client.get(
        "/__lbheartbeat__?x=شكر",
        headers={
            "User-Agent": "dockerflow/tests",
            "Accept-Language": "en-US",
        },
    )
    stdout = capsys.readouterr().out
    assert json.loads(stdout)


def test_mozlog_record_attrs(app, client, caplog):
    app.state.DOCKERFLOW_SUMMARY_LOG_QUERYSTRING = True

    client.get(
        "/__lbheartbeat__?x=شكر",
        headers={
            "User-Agent": "dockerflow/tests",
            "Accept-Language": "en-US",
        },
    )
    record = caplog.records[0]

    assert record.levelno == logging.INFO
    assert record.agent == "dockerflow/tests"
    assert record.lang == "en-US"
    assert record.method == "GET"
    assert record.code == 200
    assert record.path == "/__lbheartbeat__"
    assert record.querystring == "x=شكر"
    assert isinstance(record.t, int)


def test_mozlog_request_id(client, caplog):
    client.get(
        "/__lbheartbeat__",
        headers={
            "X-Request-ID": "tracked-value",
        },
    )
    record = caplog.records[0]

    assert record.rid == "tracked-value"


def test_mozlog_without_correlation_id_middleware(client, caplog):
    app = FastAPI()
    app.include_router(dockerflow_router)
    app.add_middleware(MozlogRequestSummaryLogger)
    client = TestClient(app)

    client.get("/__lbheartbeat__")
    record = caplog.records[0]

    assert record.rid is None


def test_request_id_passed_to_all_log_messages(caplog):
    caplog.handler.addFilter(RequestIdLogFilter())
    caplog.handler.setFormatter(JsonLogFormatter())

    app = create_app()

    @app.get("/ping")
    def ping():
        logger = logging.getLogger("some_logger")
        logger.info("returning pong")
        return "pong"

    client = TestClient(app)

    client.get("/ping")

    log_message = next(r for r in caplog.records if r.name == "some_logger")
    assert log_message.rid is not None
    parsed_log = json.loads(caplog.text.splitlines()[0])
    assert "rid" in parsed_log["Fields"]


def test_mozlog_failure(client, mocker, caplog):
    mocker.patch(
        "dockerflow.fastapi.views.get_version", side_effect=ValueError("crash")
    )

    with pytest.raises(expected_exception=ValueError):
        client.get("/__version__")

    record = caplog.records[0]
    assert record.code == 500


VERSION_CONTENT = {"foo": "bar"}


def test_version_app_state(client, tmp_path, app):
    version_path = tmp_path / "version.json"
    version_path.write_text(json.dumps(VERSION_CONTENT))

    app.state.APP_DIR = tmp_path.resolve()
    response = client.get("/__version__")
    assert response.status_code == 200
    assert response.json() == VERSION_CONTENT


def test_version_env_var(client, tmp_path, monkeypatch):
    version_path = tmp_path / "version.json"
    version_path.write_text(json.dumps(VERSION_CONTENT))

    monkeypatch.setenv("APP_DIR", tmp_path.resolve())

    response = client.get("/__version__")
    assert response.status_code == 200
    assert response.json() == VERSION_CONTENT


def test_version_default(client, mocker):
    mock_get_version = mocker.MagicMock(return_value=VERSION_CONTENT)
    mocker.patch("dockerflow.fastapi.views.get_version", mock_get_version)

    response = client.get("/__version__")
    assert response.status_code == 200
    assert response.json() == VERSION_CONTENT
    mock_get_version.assert_called_with("/app")


def test_heartbeat_get(client):
    @checks.register
    def return_error():
        return [checks.Error("BOOM", id="foo")]

    response = client.get("/__heartbeat__")
    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "checks": {"return_error": "error"},
        "details": {
            "return_error": {
                "level": 40,
                "messages": {"foo": "BOOM"},
                "status": "error",
            }
        },
    }


def test_heartbeat_head(client):
    @checks.register
    def return_sucess():
        return [checks.Info("Nice", id="foo")]

    response = client.head("/__heartbeat__")
    assert response.status_code == 200
    assert response.content == b""


def test_heartbeat_custom_name(client):
    @checks.register(name="my_check_name")
    def return_error():
        return [checks.Error("BOOM", id="foo")]

    response = client.get("/__heartbeat__")
    assert response.json()["checks"]["my_check_name"]
