# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import logging

import pytest
import redis
from django.core.checks.registry import registry
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext
from django.utils.deprecation import MiddlewareMixin

from dockerflow import health
from dockerflow.django import checks
from dockerflow.django.middleware import DockerflowMiddleware


@pytest.fixture(autouse=True)
def _reset_checks():
    yield
    registry.registered_checks = set()
    registry.deployment_checks = set()


@pytest.fixture(autouse=True)
def _setup_request_summary_logger(dockerflow_middleware):
    dockerflow_middleware.summary_logger.addHandler(logging.NullHandler())
    dockerflow_middleware.summary_logger.setLevel(logging.INFO)


@pytest.fixture()
def dockerflow_middleware():
    return DockerflowMiddleware(get_response=HttpResponse())


@pytest.mark.parametrize("request_path", ["/__version__", "/__version__/"])
def test_version_exists(
    dockerflow_middleware, mocker, request_path, rf, version_content
):
    mocker.patch("dockerflow.version.get_version", return_value=version_content)
    request = rf.get(request_path)
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 200
    assert json.loads(response.content.decode()) == version_content


def test_version_missing(dockerflow_middleware, mocker, rf):
    mocker.patch("dockerflow.version.get_version", return_value=None)
    request = rf.get("/__version__")
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 404


@pytest.mark.django_db()
def test_heartbeat(client, settings):
    response = client.get("/__heartbeat__")
    assert response.status_code == 200

    settings.DOCKERFLOW_CHECKS = [
        "tests.django.django_checks.warning",
        "tests.django.django_checks.error",
    ]
    checks.register()
    response = client.get("/__heartbeat__")
    assert response.status_code == 500
    content = response.json()
    assert content["status"] == "error"
    assert content.get("checks") is None
    assert content.get("details") is None


@pytest.mark.django_db()
def test_heartbeat_debug(client, settings):
    settings.DOCKERFLOW_CHECKS = [
        "tests.django.django_checks.warning",
        "tests.django.django_checks.error",
    ]
    settings.DEBUG = True
    checks.register()
    response = client.get("/__heartbeat__")
    assert response.status_code == 500
    content = response.json()
    assert content["status"]
    assert content["checks"]
    assert content["details"]


@pytest.mark.django_db()
def test_heartbeat_silenced(client, settings):
    settings.DOCKERFLOW_CHECKS = [
        "tests.django.django_checks.warning",
        "tests.django.django_checks.error",
    ]
    settings.SILENCED_SYSTEM_CHECKS.append("tests.checks.E001")
    settings.DEBUG = True
    checks.register()

    response = client.get("/__heartbeat__")
    assert response.status_code == 200
    content = response.json()
    assert content["status"] == "warning"
    assert "warning" in content["details"]
    assert "error" not in content["details"]


@pytest.mark.django_db()
@pytest.mark.usefixtures("_reset_checks")
def test_heartbeat_logging(dockerflow_middleware, rf, settings, caplog):
    request = rf.get("/__heartbeat__")
    settings.DOCKERFLOW_CHECKS = [
        "tests.django.django_checks.warning",
        "tests.django.django_checks.error",
    ]
    checks.register()

    with caplog.at_level(logging.INFO, logger="dockerflow.checks.registry"):
        dockerflow_middleware.process_request(request)
    logged = [(record.levelname, record.message) for record in caplog.records]
    assert ("ERROR", "tests.checks.E001: some error") in logged
    assert ("WARNING", "tests.checks.W001: some warning") in logged


@pytest.mark.django_db()
def test_lbheartbeat_makes_no_db_queries(dockerflow_middleware, rf):
    queries = CaptureQueriesContext(connection)
    request = rf.get("/__lbheartbeat__")
    with queries:
        response = dockerflow_middleware.process_request(request)
        assert response.status_code == 200
    assert len(queries) == 0


@pytest.mark.django_db()
def test_redis_check(client, settings):
    settings.DOCKERFLOW_CHECKS = ["dockerflow.django.checks.check_redis_connected"]
    checks.register()
    response = client.get("/__heartbeat__")
    assert response.status_code == 200


def assert_log_record(request, record, errno=0, level=logging.INFO):
    assert record.levelno == level
    assert record.errno == errno
    assert record.agent == "dockerflow/tests"
    assert record.lang == "tlh"
    assert record.method == "GET"
    assert record.path == "/"
    assert record.rid == request._id
    assert isinstance(record.t, int)


@pytest.fixture()
def dockerflow_request(rf):
    return rf.get("/", HTTP_USER_AGENT="dockerflow/tests", HTTP_ACCEPT_LANGUAGE="tlh")


def test_request_summary(admin_user, caplog, dockerflow_middleware, dockerflow_request):
    response = dockerflow_middleware.process_request(dockerflow_request)
    assert getattr(dockerflow_request, "_id") is not None
    assert isinstance(getattr(dockerflow_request, "_start_timestamp"), float)

    response = dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record)
    assert getattr(dockerflow_request, "uid", None) is None


def test_request_summary_querystring(
    settings, admin_user, caplog, dockerflow_middleware, rf
):
    settings.DOCKERFLOW_SUMMARY_LOG_QUERYSTRING = True

    request = rf.get("/?x=%D8%B4%D9%83%D8%B1")
    response = dockerflow_middleware.process_request(request)
    response = dockerflow_middleware.process_response(request, response)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.querystring == "x=شكر"
    assert isinstance(record.t, int)


def test_request_summary_admin_user(
    admin_user, caplog, dockerflow_middleware, dockerflow_request
):
    dockerflow_request.user = admin_user
    response = dockerflow_middleware.process_request(dockerflow_request)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record)
    assert record.uid == admin_user.pk


def test_request_summary_exception(
    admin_user, caplog, dockerflow_middleware, dockerflow_request
):
    exception = ValueError("exception message")
    response = dockerflow_middleware.process_request(dockerflow_request)
    dockerflow_middleware.process_exception(dockerflow_request, exception)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record, level=logging.ERROR, errno=500)
    assert record.getMessage() == "exception message"


def test_request_summary_failed_request(
    admin_user, caplog, dockerflow_middleware, dockerflow_request
):
    class HostileMiddleware(MiddlewareMixin):
        def process_request(self, request):
            delattr(request, "_id")
            # simulating resetting request changes
            delattr(request, "_start_timestamp")

        def process_response(self, request, response):
            return response

    hostile_middleware = HostileMiddleware(get_response=HttpResponse())
    response = dockerflow_middleware.process_request(dockerflow_request)
    response = hostile_middleware.process_request(dockerflow_request)
    response = hostile_middleware.process_response(dockerflow_request, response)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert getattr(record, "rid", None) is not None
    assert getattr(record, "t", None) is None


def test_check_database_connected_cannot_connect(mocker):
    ensure_connection = mocker.patch("django.db.connection.ensure_connection")
    ensure_connection.side_effect = OperationalError
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_CANNOT_CONNECT_DATABASE


def test_check_database_connected_misconfigured(mocker):
    ensure_connection = mocker.patch("django.db.connection.ensure_connection")
    ensure_connection.side_effect = ImproperlyConfigured
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_MISCONFIGURED_DATABASE


@pytest.mark.django_db()
def test_check_database_connected_unsuable(mocker):
    mocker.patch("django.db.connection.is_usable", return_value=False)
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_UNUSABLE_DATABASE


@pytest.mark.django_db()
def test_check_database_connected_success(mocker):
    errors = checks.check_database_connected([])
    assert errors == []


@pytest.mark.parametrize(
    "exception", [ImproperlyConfigured, ProgrammingError, OperationalError]
)
def test_check_migrations_applied_cannot_check_migrations(exception, mocker):
    mocker.patch("django.db.migrations.loader.MigrationLoader", side_effect=exception)
    errors = checks.check_migrations_applied([])
    assert len(errors) == 1
    assert errors[0].id == health.INFO_CANT_CHECK_MIGRATIONS


@pytest.mark.django_db()
def test_check_migrations_applied_unapplied_migrations(mocker):
    mock_loader = mocker.patch("django.db.migrations.loader.MigrationLoader")
    mock_loader.return_value.applied_migrations = ["spam", "eggs"]

    migration_mock = mocker.Mock()
    migration_mock.app_label = "app"

    migration_mock2 = mocker.Mock()
    migration_mock2.app_label = "app2"

    mock_loader.return_value.graph.nodes = {
        "app": migration_mock,
        "app2": migration_mock2,
    }

    app_config_mock = mocker.Mock()
    app_config_mock.label = "app"

    errors = checks.check_migrations_applied([app_config_mock])
    assert len(errors) == 1
    assert errors[0].id == health.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.migrated_apps = ["app"]
    errors = checks.check_migrations_applied([])
    assert len(errors) == 1
    assert errors[0].id == health.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.applied_migrations = ["app"]
    errors = checks.check_migrations_applied([])
    assert len(errors) == 0


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (redis.ConnectionError, health.ERROR_CANNOT_CONNECT_REDIS),
        (NotImplementedError, health.ERROR_MISSING_REDIS_CLIENT),
        (ImproperlyConfigured, health.ERROR_MISCONFIGURED_REDIS),
    ],
)
def test_check_redis_connected(mocker, exception, error):
    get_redis_connection = mocker.patch("django_redis.get_redis_connection")
    get_redis_connection.side_effect = exception
    errors = checks.check_redis_connected([])
    assert len(errors) == 1
    assert errors[0].id == error


def test_check_redis_connected_ping_failed(mocker):
    get_redis_connection = mocker.patch("django_redis.get_redis_connection")
    get_redis_connection.return_value.ping.return_value = False
    errors = checks.check_redis_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_REDIS_PING_FAILED
