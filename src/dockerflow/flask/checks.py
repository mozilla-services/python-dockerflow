# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
This is a minor port of the Django checks system messages to be used
for Dockerflow checks of the dockerflow.flask Flask extension.
"""
from .. import health

# Levels
DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50
STATUSES = {
    0: 'ok',
    DEBUG: 'debug',
    INFO: 'info',
    WARNING: 'warning',
    ERROR: 'error',
    CRITICAL: 'critical',
}


def level_to_text(level):
    return STATUSES.get(level, 'unknown')


class CheckMessage(object):
    """
    A port of part of the :doc:`Django system checks <django:topics/checks>`
    and their :class:`~django.core.checks.CheckMessage` class in particular
    to be used with custom Dockerflow checks.

    Please use one of its subclasses in your custom checks:

    :class:`~dockerflow.flask.checks.Debug`,
    :class:`~dockerflow.flask.checks.Info`,
    :class:`~dockerflow.flask.checks.Warning`,
    :class:`~dockerflow.flask.checks.Error`,
    :class:`~dockerflow.flask.checks.Critical`
    """
    def __init__(self, msg, level=None, hint=None, obj=None, id=None):
        self.msg = msg
        if level:
            self.level = int(level)
        self.hint = hint
        self.obj = obj
        self.id = id

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            all(getattr(self, attr) == getattr(other, attr)
                for attr in ['level', 'msg', 'hint', 'obj', 'id'])
        )

    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        if self.obj is None:
            obj = "?"
        else:
            obj = self.obj
        id = "(%s) " % self.id if self.id else ""
        hint = "\n\tHINT: %s" % self.hint if self.hint else ''
        return "%s: %s%s%s" % (obj, id, self.msg, hint)

    def __repr__(self):
        return "<%s: level=%r, msg=%r, hint=%r, obj=%r, id=%r>" % \
            (self.__class__.__name__, self.level,
             self.msg, self.hint, self.obj, self.id)

    def is_serious(self, level=ERROR):
        return self.level >= level


class Debug(CheckMessage):
    """
    A :class:`~dockerflow.flask.checks.CheckMessage` subclass to represent
    a debugging check result.
    """
    level = DEBUG


class Info(CheckMessage):
    """
    A :class:`~dockerflow.flask.checks.CheckMessage` subclass to represent
    a info check result.
    """
    level = INFO


class Warning(CheckMessage):
    """
    A :class:`~dockerflow.flask.checks.CheckMessage` subclass to represent
    a warning check result.
    """
    level = WARNING


class Error(CheckMessage):
    """
    A :class:`~dockerflow.flask.checks.CheckMessage` subclass to represent
    an error check result.
    """
    level = ERROR


class Critical(CheckMessage):
    """
    A :class:`~dockerflow.flask.checks.CheckMessage` subclass to represent
    a critical check result.
    """
    level = CRITICAL


def check_database_connected(db):
    """
    A built-in check to see if connecting to the configured default
    database backend succeeds.
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
    """
    errors = []

    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError

    config = migrate.get_config()
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
