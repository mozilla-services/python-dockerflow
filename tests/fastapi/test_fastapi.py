# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockerflow.fastapi import dockerflow_router


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
