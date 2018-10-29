# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import json
import os
import redis

import pytest
from fakeredis import FakeStrictRedis
from flask import Flask, g, request, Response, has_request_context
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, current_user
from flask_login.mixins import UserMixin
from flask_redis import FlaskRedis
from flask_sqlalchemy import SQLAlchemy, get_debug_queries
from dockerflow import health
from dockerflow.flask import checks, Dockerflow
from sqlalchemy.exc import DBAPIError, SQLAlchemyError


class MockUser(UserMixin):
    def __init__(self, id):
        self.id = id


def load_user(user_id):
    return MockUser(user_id)


def create_app():
    app = Flask('dockerflow')
    app.secret_key = 'super sekrit'
    login_manager = LoginManager(app)
    login_manager.user_loader(load_user)
    return app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def dockerflow(app):
    return Dockerflow(app)


@pytest.fixture
def db(app):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    return SQLAlchemy(app)


@pytest.fixture
def migrate(app, db):
    test_migrations = os.path.join(os.path.dirname(__file__), 'migrations')
    return Migrate(app, db, directory=test_migrations)


@pytest.fixture
def redis_store(app):
    return FlaskRedis.from_custom_provider(FakeStrictRedis, app)


def test_instantiating(app):
    dockerflow = Dockerflow()
    assert 'dockerflow.heartbeat' not in app.view_functions
    dockerflow.init_app(app)
    assert 'dockerflow.heartbeat' in app.view_functions


def test_version_exists(dockerflow, mocker, app, version_content):
    mocker.patch.object(dockerflow, '_version_callback',
                        return_value=version_content)
    response = app.test_client().get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.data.decode()) == version_content


def test_version_path(mocker, version_content):
    app = Flask('dockerflow')
    app.secret_key = 'super sekrit'
    login_manager = LoginManager(app)
    login_manager.user_loader(load_user)
    custom_version_path = '/something/extra/ordinary'
    dockerflow = Dockerflow(app, version_path=custom_version_path)
    version_callback = mocker.patch.object(dockerflow, '_version_callback',
                                           return_value=version_content)
    with app.test_client() as test_client:
        response = test_client.get('/__version__')
        assert response.status_code == 200
        assert json.loads(response.data.decode()) == version_content
        version_callback.assert_called_with(custom_version_path)


def test_version_missing(dockerflow, mocker, app):
    mocker.patch.object(dockerflow, '_version_callback',
                        return_value=None)
    response = app.test_client().get('/__version__')
    assert response.status_code == 404


def test_version_callback(dockerflow, app):
    callback_version = {'version': '1.0'}

    @dockerflow.version_callback
    def version_callback(path):
        return callback_version

    response = app.test_client().get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.data.decode()) == callback_version


def test_heartbeat(app, dockerflow):
    # app.debug = True
    dockerflow.checks.clear()

    response = app.test_client().get('/__heartbeat__')
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

    response = app.test_client().get('/__heartbeat__')
    assert response.status_code == 500
    payload = json.loads(response.data.decode())
    assert payload['status'] == 'error'
    defaults = payload['details']
    assert 'error_check' in defaults
    assert 'warning_check' in defaults
    assert 'warning-check-two' in defaults


def test_lbheartbeat_makes_no_db_queries(dockerflow, app):
    assert len(get_debug_queries()) == 0
    response = app.test_client().get('/__lbheartbeat__')
    assert response.status_code == 200
    assert len(get_debug_queries()) == 0


def test_full_redis_check(mocker):
    app = Flask('redis-check')
    app.debug = True
    redis_store = FlaskRedis.from_custom_provider(FakeStrictRedis, app)
    dockerflow = Dockerflow(app, redis=redis_store)
    assert 'check_redis_connected' in dockerflow.checks

    with app.test_client() as test_client:
        response = test_client.get('/__heartbeat__')
        assert response.status_code == 200
        assert json.loads(response.data.decode())['status'] == 'ok'


def test_full_redis_check_error(mocker):
    app = Flask('redis-check')
    redis_store = FlaskRedis.from_custom_provider(FakeStrictRedis, app)
    ping = mocker.patch.object(redis_store, 'ping')
    ping.side_effect = redis.ConnectionError
    dockerflow = Dockerflow(app, redis=redis_store)
    assert 'check_redis_connected' in dockerflow.checks

    with app.test_client() as test_client:
        response = test_client.get('/__heartbeat__')
        assert response.status_code == 500
        assert json.loads(response.data.decode())['status'] == 'error'


def test_full_db_check(mocker):
    app = Flask('db-check')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)
    dockerflow = Dockerflow(app, db=db)
    assert 'check_database_connected' in dockerflow.checks

    response = app.test_client().get('/__heartbeat__')
    assert response.status_code == 200
    assert json.loads(response.data.decode())['status'] == 'ok'


def test_full_db_check_error(mocker):
    app = Flask('db-check')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)

    engine_connect = mocker.patch.object(db.engine, 'connect')
    engine_connect.side_effect = SQLAlchemyError
    dockerflow = Dockerflow(app, db=db)
    assert 'check_database_connected' in dockerflow.checks

    with app.test_client() as test_client:
        response = test_client.get('/__heartbeat__')
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


def test_request_summary(caplog, dockerflow, app):
    with app.test_client() as test_client:
        test_client.get('/', headers=headers)
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


def test_request_summary_exception(caplog, app):
    Dockerflow(app)

    with app.test_request_context('/', headers=headers):
        assert has_request_context()
        app.preprocess_request()
        app.handle_exception(ValueError('exception message'))
        response = Response('')
        response = app.process_response(response)
        for record in caplog.records:
            if record != 'request.summary':
                continue
            assert_log_record(request, record, level=logging.ERROR, errno=500)
            assert record.getMessage() == 'exception message'


def test_request_summary_failed_request(caplog, dockerflow, app):
    @app.before_request
    def hostile_callback():
        # simulating resetting request changes
        delattr(g, '_request_id')
        delattr(g, '_start_timestamp')

    app.test_client().get('/', headers=headers)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert getattr(record, 'rid', None) is None
    assert getattr(record, 't', None) is None


def test_db_check_sqlalchemy_error(mocker, db):
    engine_connect = mocker.patch.object(db.engine, 'connect')
    engine_connect.side_effect = SQLAlchemyError
    errors = checks.check_database_connected(db)
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_SQLALCHEMY_EXCEPTION


def test_db_check_dbapi_error(mocker, db):
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
        repr(message) == "<Error: level=100, msg='some error', "
                         "hint=None, obj='test', id='tests.checks.E001'>"
    )

    message2 = checks.Error('some error', level=100,
                            id='tests.checks.E001', obj=obj)
    assert message == message2

    message3 = checks.Error('some error', level=101,
                            id='tests.checks.E001', obj=obj)
    assert message != message3


@pytest.mark.parametrize('exception', [
    SQLAlchemyError(), DBAPIError.instance('', [], Exception(), Exception)
])
def test_check_migrations_applied_cannot_check_migrations(exception, mocker, db, migrate):
    engine_connect = mocker.patch.object(db.engine, 'connect')
    engine_connect.side_effect = exception
    errors = checks.check_migrations_applied(migrate)
    assert len(errors) == 1
    assert errors[0].id == health.INFO_CANT_CHECK_MIGRATIONS


def test_check_migrations_applied_success(mocker, db, migrate):
    get_heads = mocker.patch(
        'alembic.script.ScriptDirectory.get_heads',
        return_value=('17164a7d1c2e',)
    )
    get_current_heads = mocker.patch(
        'alembic.migration.MigrationContext.get_current_heads',
        return_value=('17164a7d1c2e',)
    )
    errors = checks.check_migrations_applied(migrate)
    assert get_heads.called
    assert get_current_heads.called
    assert len(errors) == 0


def test_check_migrations_applied_unapplied_migrations(mocker, db, migrate):
    get_heads = mocker.patch(
        'alembic.script.ScriptDirectory.get_heads',
        return_value=('7f447c94347a',)
    )
    get_current_heads = mocker.patch(
        'alembic.migration.MigrationContext.get_current_heads',
        return_value=('73d96d3120ff',)
    )
    errors = checks.check_migrations_applied(migrate)
    assert get_heads.called
    assert get_current_heads.called
    assert len(errors) == 1
    assert errors[0].id == health.WARNING_UNAPPLIED_MIGRATION


@pytest.mark.parametrize('exception,error', [
    (redis.ConnectionError, health.ERROR_CANNOT_CONNECT_REDIS),
    (redis.RedisError, health.ERROR_REDIS_EXCEPTION),
])
def test_check_redis_connected(mocker, redis_store, exception, error):
    ping = mocker.patch.object(redis_store, 'ping')
    ping.side_effect = exception
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 1
    assert errors[0].id == error


def test_check_redis_connected_ping_check(mocker, redis_store):
    ping = mocker.patch.object(redis_store, 'ping')
    ping.return_value = True
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 0

    ping.return_value = False
    errors = checks.check_redis_connected(redis_store)
    assert len(errors) == 1
    assert errors[0].id == health.ERROR_REDIS_PING_FAILED
