# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from logging.config import dictConfig
import json
import redis

import pytest
from flask import Flask, g, request, Response, has_request_context
from flask_login import LoginManager, login_user, current_user
from flask_login.mixins import UserMixin
from flask_redis import FlaskRedis
from flask_sqlalchemy import SQLAlchemy, get_debug_queries
from dockerflow import health
from dockerflow.flask import checks, Dockerflow


class MockUser(UserMixin):
    def __init__(self, id):
        self.id = id


def load_user(user_id):
    return MockUser(user_id)


def configure_logging():
    config = {
        'version': 1,
        'formatters': {
            'json': {
                '()': 'dockerflow.logging.JsonLogFormatter',
                'logger_name': 'tests'
            }
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'json'
            },
        },
        'loggers': {
            'request.summary': {
                'handlers': ['console'],
                'level': 'DEBUG',
            },
        }
    }
    dictConfig(config)


def create_app():
    configure_logging()
    app = Flask('dockerflow')
    app.secret_key = 'super sekrit'
    Dockerflow(app)
    login_manager = LoginManager(app)
    login_manager.user_loader(load_user)
    return app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def dockerflow(app):
    return app.extensions['dockerflow']


@pytest.fixture
def db(app):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['REDIS_URL'] = 'redis://127.0.0.1:6379/0'
    return SQLAlchemy(app)


@pytest.fixture
def redis_store(app):
    return FlaskRedis(app)


@pytest.yield_fixture
def flask_client(app):
    """A Flask test client. An instance of :class:`flask.testing.TestClient`
    by default.
    """
    with app.test_client() as client:
        yield client


def test_version_exists(dockerflow, mocker, flask_client, version_content):
    mocker.patch.object(dockerflow, '_version_callback',
                        return_value=version_content)
    response = flask_client.get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.data.decode()) == version_content


def test_version_path(mocker, flask_client, version_content):
    configure_logging()
    app = Flask('dockerflow')
    app.secret_key = 'super sekrit'
    login_manager = LoginManager(app)
    login_manager.user_loader(load_user)
    custom_version_path = '/something/extra/ordinary'
    dockerflow = Dockerflow(app, version_path=custom_version_path)
    version_callback = mocker.patch.object(dockerflow, '_version_callback',
                                           return_value=version_content)
    with app.test_client() as client:
        response = client.get('/__version__')
        assert response.status_code == 200
        assert json.loads(response.data.decode()) == version_content
        version_callback.assert_called_with(custom_version_path)


def test_version_missing(dockerflow, mocker, flask_client):
    mocker.patch.object(dockerflow, '_version_callback',
                        return_value=None)
    response = flask_client.get('/__version__')
    assert response.status_code == 404


def test_version_callback(dockerflow, flask_client):
    callback_version = {'version': '1.0'}

    @dockerflow.version_callback
    def version_callback(path):
        return callback_version

    response = flask_client.get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.data.decode()) == callback_version


def test_heartbeat(app, dockerflow, flask_client):
    # app.debug = True
    dockerflow.checks.clear()

    response = flask_client.get('/__heartbeat__')
    assert response.status_code == 200

    @dockerflow.check
    def error_check():
        return [checks.Error('some error', id='tests.checks.E001')]

    @dockerflow.check()
    def warning_check():
        return [checks.Warning('some warning', id='tests.checks.W001')]

    @dockerflow.check(name='warning-check-two')
    def warning_check2():
        return [checks.Warning('some other warning', id='tests.checks.W002')]

    response = flask_client.get('/__heartbeat__')
    assert response.status_code == 500
    payload = json.loads(response.data.decode())
    assert payload['status'] == 'error'
    defaults = payload['details']
    assert 'error_check' in defaults
    assert 'warning_check' in defaults
    assert 'warning-check-two' in defaults


def test_lbheartbeat_makes_no_db_queries(dockerflow, flask_client):
    assert len(get_debug_queries()) == 0
    response = flask_client.get('/__lbheartbeat__')
    assert response.status_code == 200
    assert len(get_debug_queries()) == 0


def test_full_redis_check(flask_client, mocker, redis_store):
    app = Flask('redis-check')
    dockerflow = Dockerflow(app, redis=redis_store)
    assert 'check_redis_connected' in dockerflow.checks

    response = flask_client.get('/__heartbeat__')
    assert response.status_code == 200
    assert json.loads(response.data.decode())['status'] == 'ok'


def test_full_redis_check_error(mocker, redis_store):
    make_connection = mocker.patch('redis.connection.ConnectionPool.make_connection')
    make_connection.side_effect = redis.ConnectionError
    app = Flask('redis-check')
    dockerflow = Dockerflow(app, redis=redis_store)
    assert 'check_redis_connected' in dockerflow.checks

    with app.test_client() as flask_client:
        response = flask_client.get('/__heartbeat__')
        assert response.status_code == 500
        assert json.loads(response.data.decode())['status'] == 'error'


def assert_log_record(request, record, errno=0, level=logging.INFO):
    assert record.levelno == level
    assert record.errno == errno
    assert record.agent == 'dockerflow/tests'
    assert record.lang == 'tlh'
    assert record.method == 'GET'
    assert record.path == '/'
    assert record.rid == g._request_id
    assert isinstance(record.t, int)


headers = {
    'User-Agent': 'dockerflow/tests',
    'Accept-Language': 'tlh',
}


def test_request_summary(caplog, dockerflow, flask_client):
    flask_client.get('/', headers=headers)
    assert getattr(g, '_request_id') is not None
    assert isinstance(getattr(g, '_start_timestamp'), float)

    assert len(caplog.records) == 1
    for record in caplog.records:
        assert_log_record(request, record)
        assert getattr(request, 'uid', None) is None


def assert_user(app, caplog, user, callback):
    with app.test_request_context('/', headers=headers):
        assert has_request_context()
        login_user(user)
        assert user == current_user
        app.preprocess_request()
        response = Response('')
        response = app.process_response(response)
        assert len(caplog.records) == 1
        for record in caplog.records:
            assert_log_record(request, record)
            assert record.uid == callback(user)


def test_request_summary_user_success(caplog, dockerflow, mocker, app):
    user = MockUser(100)
    assert_user(app, caplog, user, lambda user: user.get_id())


def test_request_summary_user_is_authenticated_missing(caplog, dockerflow, app):

    class MissingIsAuthenticatedUser(object):
        id = 0
        is_active = True

        def get_id(self):
            return self.id

    assert_user(app, caplog, MissingIsAuthenticatedUser(), lambda user: '')


def test_request_summary_user_is_authenticated_callable(caplog, dockerflow, app):

    class CallableIsAuthenticatedUser(object):
        id = 0
        is_active = True

        def get_id(self):
            return self.id

        def is_authenticated(self):
            return True

    assert_user(app, caplog, CallableIsAuthenticatedUser(),
                lambda user: user.get_id())


def test_request_summary_user_flask_login_missing(caplog, dockerflow, app, monkeypatch):
    monkeypatch.setattr('dockerflow.flask.app.has_flask_login', False)
    user = MockUser(100)
    assert_user(app, caplog, user, lambda user: '')


def test_request_summary_exception(caplog, dockerflow, flask_client, app):
    @app.route('/')
    def index():
        raise ValueError('exception message')

    flask_client.get('/', headers=headers)
    assert len(caplog.records) == 1
    for record in caplog.records:
        if not hasattr(record, 'errno'):
            continue
        assert_log_record(request, record, level=logging.ERROR, errno=500)
        assert record.getMessage() == 'exception message'


def test_request_summary_failed_request(caplog, dockerflow, app, flask_client):
    @app.before_request
    def hostile_callback():
        # simulating resetting request changes
        delattr(g, '_request_id')
        delattr(g, '_start_timestamp')

    flask_client.get('/', headers=headers)
    assert len(caplog.records) == 1
    for record in caplog.records:
        assert getattr(record, 'rid', None) is None
        assert getattr(record, 't', None) is None


def test_db_check_sqlalchemy_error(mocker, db):
    from sqlalchemy.exc import SQLAlchemyError
    engine_connect = mocker.patch.object(db.engine, 'connect')
    engine_connect.side_effect = SQLAlchemyError
    errors = checks.check_database_connected(db)
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_SQLALCHEMY_EXCEPTION


def test_db_check_dbapi_error(mocker, db):
    from sqlalchemy.exc import DBAPIError
    exception = DBAPIError.instance('', [], Exception(), Exception)
    engine_connect = mocker.patch.object(db.engine, 'connect')
    engine_connect.side_effect = exception
    errors = checks.check_database_connected(db)
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_DB_API_EXCEPTION


def test_db_check_success(db):
    errors = checks.check_database_connected(db)
    assert errors == []


def test_check_message():
    message = checks.Error('some error', level=100, id='tests.checks.E001')
    assert str(message) == '?: (tests.checks.E001) some error'
    assert message.is_serious()

    obj = 'test'
    message = checks.Error('some error', level=100,
                           id='tests.checks.E001', obj=obj)
    assert str(message) == 'test: (tests.checks.E001) some error'
    assert (
        repr(message) ==
        "<Error: level=100, msg='some error', hint=None, obj='test', id='tests.checks.E001'>"
    )

    message2 = checks.Error('some error', level=100,
                            id='tests.checks.E001', obj=obj)
    assert message == message2

    message3 = checks.Error('some error', level=101,
                            id='tests.checks.E001', obj=obj)
    assert message != message3


# @pytest.mark.parametrize('exception', [
#     ImproperlyConfigured, ProgrammingError, OperationalError
# ])
# def test_check_migrations_applied_cannot_check_migrations(exception, mocker):
#     mocker.patch(
#         'django.db.migrations.loader.MigrationLoader',
#         side_effect=exception,
#     )
#     errors = checks.check_migrations_applied([])
#     assert len(errors) == 1
#     assert errors[0].id == checks.INFO_CANT_CHECK_MIGRATIONS


# @pytest.mark.django_db
# def test_check_migrations_applied_unapplied_migrations(mocker):
#     mock_loader = mocker.patch('django.db.migrations.loader.MigrationLoader')
#     mock_loader.return_value.applied_migrations = ['spam', 'eggs']

#     migration_mock = mocker.Mock()
#     migration_mock.app_label = 'app'

#     migration_mock2 = mocker.Mock()
#     migration_mock2.app_label = 'app2'

#     mock_loader.return_value.graph.nodes = {
#         'app': migration_mock,
#         'app2': migration_mock2,
#     }

#     app_config_mock = mocker.Mock()
#     app_config_mock.label = 'app'

#     errors = checks.check_migrations_applied([app_config_mock])
#     assert len(errors) == 1
#     assert errors[0].id == checks.WARNING_UNAPPLIED_MIGRATION

#     mock_loader.return_value.migrated_apps = ['app']
#     errors = checks.check_migrations_applied([])
#     assert len(errors) == 1
#     assert errors[0].id == checks.WARNING_UNAPPLIED_MIGRATION

#     mock_loader.return_value.applied_migrations = ['app']
#     errors = checks.check_migrations_applied([])
#     assert len(errors) == 0


@pytest.mark.parametrize('exception,error', [
    (redis.ConnectionError, health.ERROR_CANNOT_CONNECT_REDIS),
    (redis.RedisError, health.ERROR_REDIS_EXCEPTION),
])
def test_check_redis_connected(mocker, redis_store, exception, error):
    make_connection = mocker.patch('redis.connection.ConnectionPool.make_connection')
    make_connection.side_effect = exception
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 1
    assert errors[0].id == error


def test_check_redis_connected_ping_check(mocker, redis_store):
    make_connection = mocker.patch('redis.connection.ConnectionPool.make_connection')
    make_connection.return_value.ping.return_value = True
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 0

    make_connection.return_value.ping.return_value = False
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_REDIS_PING_FAILED
