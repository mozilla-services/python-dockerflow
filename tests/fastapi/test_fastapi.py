# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockerflow.fastapi import MozlogRequestSummaryLogger, dockerflow_router


def create_app():
    app = FastAPI()
    app.include_router(dockerflow_router)
    app.add_middleware(MozlogRequestSummaryLogger)
    return app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
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


def test_mozlog(client, caplog):
    client.get(
        "/__lbheartbeat__",
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
    assert record.path == "/__lbheartbeat__"
    assert isinstance(record.t, int)


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
    mocker.patch("dockerflow.fastapi.router.get_version", mock_get_version)

    response = client.get("/__version__")
    assert response.status_code == 200
    assert response.json() == VERSION_CONTENT
    mock_get_version.assert_called_with("/app")


