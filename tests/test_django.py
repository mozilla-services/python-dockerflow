# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import json
import redis
from django import VERSION as django_version
from django.core.checks.registry import registry
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.test.utils import CaptureQueriesContext

from dockerflow import health
from dockerflow.django import checks
from dockerflow.django.middleware import DockerflowMiddleware
import pytest


@pytest.fixture
def reset_checks():
    if django_version[0] < 2:
        registry.registered_checks = []
        registry.deployment_checks = []
    else:
        registry.registered_checks = set()
        registry.deployment_checks = set()


@pytest.fixture
def dockerflow_middleware():
    return DockerflowMiddleware()


def test_version_exists(dockerflow_middleware, mocker, rf, version_content):
    mocker.patch('dockerflow.version.get_version', return_value=version_content)
    request = rf.get('/__version__')
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 200
    assert json.loads(response.content.decode()) == version_content


def test_version_missing(dockerflow_middleware, mocker, rf):
    mocker.patch('dockerflow.version.get_version', return_value=None)
    request = rf.get('/__version__')
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 404


@pytest.mark.django_db
def test_heartbeat(dockerflow_middleware, reset_checks, rf, settings):
    request = rf.get('/__heartbeat__')
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 200

    settings.DOCKERFLOW_CHECKS = [
        'tests.django_checks.warning',
        'tests.django_checks.error',
    ]
    checks.register()
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 500


@pytest.mark.django_db
def test_lbheartbeat_makes_no_db_queries(dockerflow_middleware, rf):
    queries = CaptureQueriesContext(connection)
    request = rf.get('/__lbheartbeat__')
    with queries:
        response = dockerflow_middleware.process_request(request)
        assert response.status_code == 200
    assert len(queries) == 0


@pytest.mark.django_db
def test_redis_check(dockerflow_middleware, reset_checks, rf, settings):
    settings.DOCKERFLOW_CHECKS = [
        'dockerflow.django.checks.check_redis_connected',
    ]
    checks.register()
    request = rf.get('/__heartbeat__')
    response = dockerflow_middleware.process_request(request)
    assert response.status_code == 200


def assert_log_record(request, record, errno=0, level=logging.INFO):
    assert record.levelno == level
    assert record.errno == errno
    assert record.agent == 'dockerflow/tests'
    assert record.lang == 'tlh'
    assert record.method == 'GET'
    assert record.path == '/'
    assert record.rid == request._id
    assert isinstance(record.t, int)


@pytest.fixture
def dockerflow_request(rf):
    return rf.get(
        '/',
        HTTP_USER_AGENT='dockerflow/tests',
        HTTP_ACCEPT_LANGUAGE='tlh',
    )


def test_request_summary(admin_user, caplog,
                         dockerflow_middleware, dockerflow_request):
    response = dockerflow_middleware.process_request(dockerflow_request)
    assert getattr(dockerflow_request, '_id') is not None
    assert isinstance(getattr(dockerflow_request, '_start_timestamp'), float)

    response = dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record)
    assert getattr(dockerflow_request, 'uid', None) is None


def test_request_summary_admin_user(admin_user, caplog,
                                    dockerflow_middleware, dockerflow_request):
    dockerflow_request.user = admin_user
    response = dockerflow_middleware.process_request(dockerflow_request)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record)
    assert record.uid == admin_user.pk


def test_request_summary_exception(admin_user, caplog,
                                   dockerflow_middleware, dockerflow_request):
    exception = ValueError('exception message')
    response = dockerflow_middleware.process_request(dockerflow_request)
    dockerflow_middleware.process_exception(dockerflow_request, exception)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert_log_record(dockerflow_request, record, level=logging.ERROR, errno=500)
    assert record.getMessage() == 'exception message'


def test_request_summary_failed_request(caplog,
                                        dockerflow_middleware, dockerflow_request):
    dockerflow_middleware.process_request(dockerflow_request)

    class HostileMiddleware(object):
        def process_request(self, request):
            # simulating resetting request changes
            delattr(dockerflow_request, '_id')
            delattr(dockerflow_request, '_start_timestamp')
            return None

    response = HostileMiddleware().process_request(dockerflow_request)
    dockerflow_middleware.process_response(dockerflow_request, response)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert getattr(record, 'rid', None) is None
    assert getattr(record, 't', None) is None


def test_check_database_connected_cannot_connect(mocker):
    ensure_connection = mocker.patch('django.db.connection.ensure_connection')
    ensure_connection.side_effect = OperationalError
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_CANNOT_CONNECT_DATABASE


def test_check_database_connected_misconfigured(mocker):
    ensure_connection = mocker.patch('django.db.connection.ensure_connection')
    ensure_connection.side_effect = ImproperlyConfigured
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_MISCONFIGURED_DATABASE


@pytest.mark.django_db
def test_check_database_connected_unsuable(mocker):
    mocker.patch('django.db.connection.is_usable', return_value=False)
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_UNUSABLE_DATABASE


@pytest.mark.django_db
def test_check_database_connected_success(mocker):
    errors = checks.check_database_connected([])
    assert errors == []


@pytest.mark.parametrize('exception', [
    ImproperlyConfigured, ProgrammingError, OperationalError
])
def test_check_migrations_applied_cannot_check_migrations(exception, mocker):
    mocker.patch(
        'django.db.migrations.loader.MigrationLoader',
        side_effect=exception,
    )
    errors = checks.check_migrations_applied([])
    assert len(errors) == 1
    assert errors[0].id == health.INFO_CANT_CHECK_MIGRATIONS


@pytest.mark.django_db
def test_check_migrations_applied_unapplied_migrations(mocker):
    mock_loader = mocker.patch('django.db.migrations.loader.MigrationLoader')
    mock_loader.return_value.applied_migrations = ['spam', 'eggs']

    migration_mock = mocker.Mock()
    migration_mock.app_label = 'app'

    migration_mock2 = mocker.Mock()
    migration_mock2.app_label = 'app2'

    mock_loader.return_value.graph.nodes = {
        'app': migration_mock,
        'app2': migration_mock2,
    }

    app_config_mock = mocker.Mock()
    app_config_mock.label = 'app'

    errors = checks.check_migrations_applied([app_config_mock])
    assert len(errors) == 1
    assert errors[0].id == health.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.migrated_apps = ['app']
    errors = checks.check_migrations_applied([])
    assert len(errors) == 1
    assert errors[0].id == health.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.applied_migrations = ['app']
    errors = checks.check_migrations_applied([])
    assert len(errors) == 0


@pytest.mark.parametrize('exception,error', [
    (redis.ConnectionError, health.ERROR_CANNOT_CONNECT_REDIS),
    (NotImplementedError, health.ERROR_MISSING_REDIS_CLIENT),
    (ImproperlyConfigured, health.ERROR_MISCONFIGURED_REDIS),
])
def test_check_redis_connected(mocker, exception, error):
    get_redis_connection = mocker.patch('django_redis.get_redis_connection')
    get_redis_connection.side_effect = exception
    errors = checks.check_redis_connected([])
    assert len(errors) == 1
    assert errors[0].id == error


def test_check_redis_connected_ping_failed(mocker):
    get_redis_connection = mocker.patch('django_redis.get_redis_connection')
    get_redis_connection.return_value.ping.return_value = False
    errors = checks.check_redis_connected([])
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_REDIS_PING_FAILED
