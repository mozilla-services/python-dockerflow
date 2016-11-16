# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import redis
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.test.utils import CaptureQueriesContext

from dockerflow.django import checks
import pytest


# as documented on https://github.com/mozilla-services/Dockerflow/blob/master/docs/version_object.md
version_content = {
    'source': 'https://github.com/mozilla-services/python-dockerflow',
    'version': 'release tag or string for humans',
    'commit': '<git hash>',
    'build': 'uri to CI build job'
}


def test_version_exists(client, mocker):
    mocker.patch('dockerflow.version.get_version', return_value=version_content)
    response = client.get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.content.decode()) == version_content


def test_version_missing(client, mocker):
    mocker.patch('dockerflow.version.get_version', return_value=None)
    response = client.get('/__version__')
    assert response.status_code == 404


@pytest.mark.django_db
def test_heartbeat(client, reset_checks, settings):
    response = client.get('/__heartbeat__')
    assert response.status_code == 200

    settings.DOCKERFLOW_CHECKS = [
        'tests.checks.warning',
        'tests.checks.error',
    ]
    checks.register()
    response = client.get('/__heartbeat__')
    assert response.status_code == 500


@pytest.mark.django_db
def test_lbheartbeat_makes_no_db_queries(client):
    queries = CaptureQueriesContext(connection)
    with queries:
        res = client.get('/__lbheartbeat__')
        assert res.status_code == 200
    assert len(queries) == 0


@pytest.mark.django_db
def test_redis_check(client, reset_checks, settings):
    settings.DOCKERFLOW_CHECKS = [
        'dockerflow.django.checks.check_redis_connected',
    ]
    checks.register()
    response = client.get('/__heartbeat__')
    assert response.status_code == 200


def test_check_database_connected_cannot_connect(mocker):
    ensure_connection = mocker.patch('django.db.connection.ensure_connection')
    ensure_connection.side_effect = OperationalError
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == checks.ERROR_CANNOT_CONNECT_DATABASE


def test_check_database_connected_misconfigured(mocker):
    ensure_connection = mocker.patch('django.db.connection.ensure_connection')
    ensure_connection.side_effect = ImproperlyConfigured
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == checks.ERROR_MISCONFIGURED_DATABASE


@pytest.mark.django_db
def test_check_database_connected_unsuable(mocker):
    mocker.patch('django.db.connection.is_usable', return_value=False)
    errors = checks.check_database_connected([])
    assert len(errors) == 1
    assert errors[0].id == checks.ERROR_UNUSABLE_DATABASE


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
    assert errors[0].id == checks.INFO_CANT_CHECK_MIGRATIONS


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
    assert errors[0].id == checks.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.migrated_apps = ['app']
    errors = checks.check_migrations_applied([])
    assert len(errors) == 1
    assert errors[0].id == checks.WARNING_UNAPPLIED_MIGRATION

    mock_loader.return_value.applied_migrations = ['app']
    errors = checks.check_migrations_applied([])
    assert len(errors) == 0


@pytest.mark.parametrize('exception,error', [
    (redis.ConnectionError, checks.ERROR_CANNOT_CONNECT_REDIS),
    (NotImplementedError, checks.ERROR_MISSING_REDIS_CLIENT),
    (ImproperlyConfigured, checks.ERROR_MISCONFIGURED_REDIS),
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
    assert errors[0].id == checks.ERROR_REDIS_PING_FAILED
