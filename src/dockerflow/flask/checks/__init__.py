# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
This module contains a few built-in checks for the Flask integration.
"""
from ... import health
from .messages import (  # noqa
    DEBUG, INFO, WARNING, ERROR, CRITICAL, STATUSES, level_to_text,
    CheckMessage, Debug, Info, Warning, Error, Critical,
)


def check_database_connected(db):
    """
    A built-in check to see if connecting to the configured default
    database backend succeeds.

    It's automatically added to the list of Dockerflow checks if a
    :class:`~flask_sqlalchemy.SQLAlchemy` object is passed
    to the :class:`~dockerflow.flask.app.Dockerflow` class during
    instantiation, e.g.::

        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from dockerflow.flask import Dockerflow

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
        db = SQLAlchemy(app)

        dockerflow = Dockerflow(app, db=db)
    """
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError

    errors = []
    try:
        with db.engine.connect() as connection:
            connection.execute('SELECT 1;')
    except DBAPIError as e:
        msg = 'DB-API error: {!s}'.format(e)
        errors.append(Error(msg, id=health.ERROR_DB_API_EXCEPTION))
    except SQLAlchemyError as e:
        msg = 'Database misconfigured: "{!s}"'.format(e)
        errors.append(Error(msg, id=health.ERROR_SQLALCHEMY_EXCEPTION))
    return errors


def check_migrations_applied(migrate):
    """
    A built-in check to see if all migrations have been applied correctly.

    It's automatically added to the list of Dockerflow checks if a
    `flask_migrate.Migrate <https://flask-migrate.readthedocs.io/>`_ object
    is passed to the :class:`~dockerflow.flask.app.Dockerflow` class during
    instantiation, e.g.::

        from flask import Flask
        from flask_migrate import Migrate
        from flask_sqlalchemy import SQLAlchemy
        from dockerflow.flask import Dockerflow

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
        db = SQLAlchemy(app)
        migrate = Migrate(app, db)

        dockerflow = Dockerflow(app, db=db, migrate=migrate)
    """
    errors = []

    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError

    # pass in Migrate.directory here explicitly to be compatible with
    # older versions of Flask-Migrate that required the directory to be passed
    config = migrate.get_config(directory=migrate.directory)
    script = ScriptDirectory.from_config(config)

    try:
        with migrate.db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            db_heads = set(context.get_current_heads())
            script_heads = set(script.get_heads())
    except (DBAPIError, SQLAlchemyError) as e:
        msg = "Can't connect to database to check migrations: {!s}".format(e)
        return [Info(msg, id=health.INFO_CANT_CHECK_MIGRATIONS)]

    if db_heads != script_heads:
        msg = "Unapplied migrations found: {}".format(', '.join(script_heads))
        errors.append(Warning(msg, id=health.WARNING_UNAPPLIED_MIGRATION))
    return errors


def check_redis_connected(client):
    """
    A built-in check to connect to Redis using the given client and see
    if it responds to the ``PING`` command.

    It's automatically added to the list of Dockerflow checks if a
    :class:`~redis.StrictRedis` instances is passed
    to the :class:`~dockerflow.flask.app.Dockerflow` class during
    instantiation, e.g.::

        import redis
        from flask import Flask
        from dockerflow.flask import Dockerflow

        app = Flask(__name__)
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

        dockerflow = Dockerflow(app, redis=redis)

    An alternative approach to instantiating a Redis client directly
    would be using the `Flask-Redis <https://github.com/underyx/flask-redis>`_
    Flask extension::

        from flask import Flask
        from flask_redis import FlaskRedis
        from dockerflow.flask import Dockerflow

        app = Flask(__name__)
        app.config['REDIS_URL'] = 'redis://:password@localhost:6379/0'
        redis_store = FlaskRedis(app)

        dockerflow = Dockerflow(app, redis=redis_store)

    """
    import redis
    errors = []

    try:
        result = client.ping()
    except redis.ConnectionError as e:
        msg = 'Could not connect to redis: {!s}'.format(e)
        errors.append(Error(msg, id=health.ERROR_CANNOT_CONNECT_REDIS))
    except redis.RedisError as e:
        errors.append(Error('Redis error: "{!s}"'.format(e),
                            id=health.ERROR_REDIS_EXCEPTION))
    else:
        if not result:
            errors.append(Error('Redis ping failed',
                                id=health.ERROR_REDIS_PING_FAILED))
    return errors
