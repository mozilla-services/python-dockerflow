# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils.module_loading import import_string

from .. import health


def level_to_text(level):
    statuses = {
        0: 'ok',
        checks.messages.DEBUG: 'debug',
        checks.messages.INFO: 'info',
        checks.messages.WARNING: 'warning',
        checks.messages.ERROR: 'error',
        checks.messages.CRITICAL: 'critical',
    }
    return statuses.get(level, 'unknown')


def check_database_connected(app_configs, **kwargs):
    """
    A Django check to see if connecting to the configured default
    database backend succeeds.
    """
    errors = []

    try:
        connection.ensure_connection()
    except OperationalError as e:
        msg = 'Could not connect to database: {!s}'.format(e)
        errors.append(checks.Error(msg,
                                   id=health.ERROR_CANNOT_CONNECT_DATABASE))
    except ImproperlyConfigured as e:
        msg = 'Datbase misconfigured: "{!s}"'.format(e)
        errors.append(checks.Error(msg,
                                   id=health.ERROR_MISCONFIGURED_DATABASE))
    else:
        if not connection.is_usable():
            errors.append(checks.Error('Database connection is not usable',
                                       id=health.ERROR_UNUSABLE_DATABASE))

    return errors


def check_migrations_applied(app_configs, **kwargs):
    """
    A Django check to see if all migrations have been applied correctly.
    """
    from django.db.migrations.loader import MigrationLoader
    errors = []

    # Load migrations from disk/DB
    try:
        loader = MigrationLoader(connection, ignore_no_migrations=True)
    except (ImproperlyConfigured, ProgrammingError, OperationalError):
        msg = "Can't connect to database to check migrations"
        return [checks.Info(msg, id=health.INFO_CANT_CHECK_MIGRATIONS)]

    if app_configs:
        app_labels = [app.label for app in app_configs]
    else:
        app_labels = loader.migrated_apps

    for node, migration in loader.graph.nodes.items():
        if migration.app_label not in app_labels:
            continue
        if node not in loader.applied_migrations:
            msg = 'Unapplied migration {}'.format(migration)
            # NB: This *must* be a Warning, not an Error, because Errors
            # prevent migrations from being run.
            errors.append(checks.Warning(msg,
                                         id=health.WARNING_UNAPPLIED_MIGRATION))

    return errors


def check_redis_connected(app_configs, **kwargs):
    """
    A Django check to connect to the default redis connection
    using ``django_redis.get_redis_connection`` and see if Redis
    responds to a ``PING`` command.
    """
    import redis
    from django_redis import get_redis_connection
    errors = []

    try:
        connection = get_redis_connection('default')
    except redis.ConnectionError as e:
        msg = 'Could not connect to redis: {!s}'.format(e)
        errors.append(checks.Error(msg, id=health.ERROR_CANNOT_CONNECT_REDIS))
    except NotImplementedError as e:
        msg = 'Redis client not available: {!s}'.format(e)
        errors.append(checks.Error(msg, id=health.ERROR_MISSING_REDIS_CLIENT))
    except ImproperlyConfigured as e:
        msg = 'Redis misconfigured: "{!s}"'.format(e)
        errors.append(checks.Error(msg, id=health.ERROR_MISCONFIGURED_REDIS))
    else:
        result = connection.ping()
        if not result:
            msg = 'Redis ping failed'
            errors.append(checks.Error(msg, id=health.ERROR_REDIS_PING_FAILED))
    return errors


def register():
    check_paths = getattr(settings, 'DOCKERFLOW_CHECKS', [
        'dockerflow.django.checks.check_database_connected',
        'dockerflow.django.checks.check_migrations_applied',
        # 'dockerflow.django.checks.check_redis_connected',
    ])
    for check_path in check_paths:
        check = import_string(check_path)
        checks.register(check)
