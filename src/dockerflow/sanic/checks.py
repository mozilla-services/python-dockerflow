# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
This module contains built-in checks for the Sanic integration.
"""
from .. import health
from ..checks import (  # noqa
    DEBUG, INFO, WARNING, ERROR, CRITICAL, STATUSES, level_to_text,
    CheckMessage, Debug, Info, Warning, Error, Critical,
)


async def check_redis_connected(redis):
    """
    A built-in check to connect to Redis using the given client and see
    if it responds to the ``PING`` command.

    It's automatically added to the list of Dockerflow checks if a
    :class:`~sanic_redis.SanicRedis` instance is passed
    to the :class:`~dockerflow.sanic.app.Dockerflow` class during
    instantiation, e.g.::

    An alternative approach to instantiating a Redis client directly
    would be using the `Sanic-Redis <https://github.com/strahe/sanic-redis>`_
    Sanic extension::

        from sanic import Sanic
        from sanic_redis import SanicRedis
        from dockerflow.sanic import Dockerflow

        app = Sanic(__name__)
        app.config['REDIS'] = {'address': 'redis://:password@localhost:6379/0'}
        dockerflow = Dockerflow(app, redis=SanicRedis(app))

    """
    import aioredis
    errors = []

    try:
        with await redis.conn as r:
            result = await r.ping()
    except aioredis.ConnectionClosedError as e:
        msg = 'Could not connect to redis: {!s}'.format(e)
        errors.append(Error(msg, id=health.ERROR_CANNOT_CONNECT_REDIS))
    except aioredis.RedisError as e:
        errors.append(Error('Redis error: "{!s}"'.format(e),
                                   id=health.ERROR_REDIS_EXCEPTION))
    else:
        if result != b'PONG':
            errors.append(Error('Redis ping failed',
                                       id=health.ERROR_REDIS_PING_FAILED))
    return errors
