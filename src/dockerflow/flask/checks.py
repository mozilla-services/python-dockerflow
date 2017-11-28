"""
This is a minor port of the Django checks system messages.
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
    A port of the Django check system message (``django.core.checks.messages``)
    to be used with custom checks.
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
    level = DEBUG


class Info(CheckMessage):
    level = INFO


class Warning(CheckMessage):
    level = WARNING


class Error(CheckMessage):
    level = ERROR


class Critical(CheckMessage):
    level = CRITICAL


def check_database_connected(db):
    """
    A Django check to see if connecting to the configured default
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
        msg = 'Datbase misconfigured: "{!s}"'.format(e)
        errors.append(Error(msg, id=health.ERROR_SQLALCHEMY_EXCEPTION))
    return errors


def check_redis_connected(client):
    """
    A Django check to connect to the default redis connection
    using ``django_redis.get_redis_connection`` and see if Redis
    responds to a ``PING`` command.
    """
    import redis
    errors = []

    try:
        connection = client.connection_pool.make_connection()
    except redis.ConnectionError as e:
        msg = 'Could not connect to redis: {!s}'.format(e)
        errors.append(Error(msg, id=health.ERROR_CANNOT_CONNECT_REDIS))
    except redis.RedisError as e:
        errors.append(Error('Redis error: "{!s}"'.format(e),
                            id=health.ERROR_REDIS_EXCEPTION))
    else:
        result = connection.ping()
        if not result:
            errors.append(Error('Redis ping failed',
                                id=health.ERROR_REDIS_PING_FAILED))
    return errors
