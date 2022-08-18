# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import functools
import logging
import uuid

import aioredis
import pytest
import sanic
import sanic_redis.core
from sanic import Sanic, response
from sanic_redis import SanicRedis

from dockerflow import health
from dockerflow.sanic import Dockerflow, checks

if sanic.__version__.startswith("20."):
    from sanic.testing import SanicTestClient
else:
    from sanic_testing.testing import SanicTestClient


class FakeRedis:
    def __init__(self, *args, error=None, **kw):
        self.error = error

    def __await__(self):
        return self
        yield

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    async def close(self):
        pass

    async def wait_closed(self):
        pass

    async def ping(self):
        if self.error == "connection":
            if aioredis.__version__.startswith("1."):
                RedisConnectionError = aioredis.ConnectionClosedError
            else:
                RedisConnectionError = aioredis.ConnectionError
            raise RedisConnectionError("fake")
        elif self.error == "redis":
            raise aioredis.RedisError("fake")
        elif self.error == "malformed":
            return b"PING"
        else:
            return b"PONG"


class FakeRedis1(FakeRedis):
    def close(self):
        pass


async def fake_redis(*args, **kw):
    if aioredis.__version__.startswith("1."):
        return FakeRedis1(*args, **kw)
    return FakeRedis(*args, **kw)


@pytest.fixture(scope="function")
def app():
    app = Sanic(f"dockerflow-{uuid.uuid4().hex}")

    @app.route("/")
    async def root(request):
        if request.body:
            raise ValueError(request.body.decode())
        return response.raw(b"")

    return app


@pytest.fixture
def dockerflow(app):
    return Dockerflow(app)


@pytest.fixture
def dockerflow_redis(app):
    app.config["REDIS"] = {"address": "redis://:password@localhost:6379/0"}
    return Dockerflow(app, redis=SanicRedis(app))


@pytest.fixture
def test_client(app):
    return SanicTestClient(app)


@pytest.mark.skipif(not sanic.__version__.startswith("20."), reason="requires sanic 20")
def test_instantiating_sanic_20(app):
    dockerflow = Dockerflow()
    assert "dockerflow.heartbeat" not in app.router.routes_names
    dockerflow.init_app(app)
    assert "dockerflow.heartbeat" in app.router.routes_names


@pytest.mark.skipif(
    sanic.__version__.startswith("20."), reason="requires sanic 21 or later"
)
def test_instantiating(app):
    Dockerflow()
    assert ("__heartbeat__",) not in app.router.routes_all
    Dockerflow(app)
    assert ("__heartbeat__",) in app.router.routes_all


def test_version_exists(dockerflow, mocker, test_client, version_content):
    mocker.patch.object(dockerflow, "_version_callback", return_value=version_content)
    _, response = test_client.get("/__version__")
    assert response.status == 200
    assert response.json == version_content


def test_version_path(app, mocker, test_client, version_content):
    custom_version_path = "/something/extra/ordinary"
    dockerflow = Dockerflow(app, version_path=custom_version_path)
    version_callback = mocker.patch.object(
        dockerflow, "_version_callback", return_value=version_content
    )
    _, response = test_client.get("/__version__")
    assert response.status == 200
    assert response.json == version_content
    version_callback.assert_called_with(custom_version_path)


def test_version_missing(dockerflow, mocker, test_client):
    mocker.patch.object(dockerflow, "_version_callback", return_value=None)
    _, response = test_client.get("/__version__")
    assert response.status == 404


def test_version_callback(dockerflow, test_client):
    callback_version = {"version": "1.0"}

    @dockerflow.version_callback
    async def version_callback(path):
        return callback_version

    _, response = test_client.get("/__version__")
    assert response.status == 200
    assert response.json == callback_version


def test_lbheartbeat(dockerflow, test_client):
    _, response = test_client.get("/__lbheartbeat__")
    assert response.status == 200
    assert response.body == b""


def test_heartbeat(dockerflow, test_client):
    dockerflow.checks.clear()

    _, response = test_client.get("/__heartbeat__")
    assert response.status == 200


def test_heartbeat_checks(dockerflow, test_client):
    dockerflow.checks.clear()

    @dockerflow.check
    def error_check():
        return [checks.Error("some error", id="tests.checks.E001")]

    @dockerflow.check()
    def warning_check():
        return [checks.Warning("some warning", id="tests.checks.W001")]

    @dockerflow.check(name="warning-check-two")
    async def warning_check2():
        return [checks.Warning("some other warning", id="tests.checks.W002")]

    _, response = test_client.get("/__heartbeat__")
    assert response.status == 500
    payload = response.json
    assert payload["status"] == "error"
    details = payload["details"]
    assert "error_check" in details
    assert "warning_check" in details
    assert "warning-check-two" in details


def test_redis_check(dockerflow_redis, mocker, test_client):
    assert "check_redis_connected" in dockerflow_redis.checks
    if aioredis.__version__.startswith("1."):
        mocker.patch.object(sanic_redis.core, "create_redis_pool", fake_redis)
    else:
        mocker.patch.object(sanic_redis.core, "from_url", fake_redis)
    _, response = test_client.get("/__heartbeat__")
    assert response.status == 200
    assert response.json["status"] == "ok"


@pytest.mark.parametrize(
    "error,messages",
    [
        (
            "connection",
            {health.ERROR_CANNOT_CONNECT_REDIS: "Could not connect to " "redis: fake"},
        ),
        ("redis", {health.ERROR_REDIS_EXCEPTION: 'Redis error: "fake"'}),
        ("malformed", {health.ERROR_REDIS_PING_FAILED: "Redis ping failed"}),
    ],
)
def test_redis_check_error(dockerflow_redis, mocker, test_client, error, messages):
    assert "check_redis_connected" in dockerflow_redis.checks
    fake_redis_error = functools.partial(fake_redis, error=error)
    if aioredis.__version__.startswith("1."):
        mocker.patch.object(sanic_redis.core, "create_redis_pool", fake_redis_error)
    else:
        mocker.patch.object(sanic_redis.core, "from_url", fake_redis_error)
    _, response = test_client.get("/__heartbeat__")
    assert response.status == 500
    assert response.json["status"] == "error"
    assert response.json["details"]["check_redis_connected"]["messages"] == messages


def assert_log_record(caplog, errno=0, level=logging.INFO, rid=None, t=int, path="/"):
    records = [r for r in caplog.records if r.name == "request.summary"]
    assert len(records) == 1
    record = records.pop()
    assert record.agent == "dockerflow/tests"
    assert record.lang == "tlh"
    assert record.method == "GET"
    assert record.path == path
    assert record.errno == errno
    assert record.levelno == level
    assert getattr(record, "rid", None) == rid
    if t is None:
        assert getattr(record, "t", None) is None
    else:
        assert isinstance(record.t, t)
    return record


headers = {"User-Agent": "dockerflow/tests", "Accept-Language": "tlh"}


def test_request_summary(caplog, dockerflow, test_client):
    request, _ = test_client.get(headers=headers)
    assert isinstance(request.ctx.start_timestamp, float)
    assert request.ctx.id is not None
    assert_log_record(caplog, rid=request.ctx.id)


def test_request_summary_exception(app, caplog, dockerflow, test_client):
    @app.route("/exception")
    def exception_raiser(request):
        raise ValueError("exception message")

    request, _ = test_client.get("/exception", headers=headers)
    record = assert_log_record(
        caplog, 500, logging.ERROR, request.ctx.id, path="/exception"
    )
    assert record.getMessage() == "exception message"


def test_request_summary_failed_request(app, caplog, dockerflow, test_client):
    @app.middleware
    def hostile_callback(request):
        # simulating resetting request changes
        del request.ctx.id
        del request.ctx.start_timestamp

    test_client.get(headers=headers)
    assert_log_record(caplog, rid=None, t=None)
