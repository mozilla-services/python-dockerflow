# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import functools
import os
import logging
import time
import uuid
from collections import OrderedDict

from flask import (Blueprint, current_app, g, got_request_exception, jsonify,
                   make_response, request)
from werkzeug.exceptions import InternalServerError

try:
    from flask_login import current_user
except ImportError:  # pragma: nocover
    has_flask_login = False
else:
    has_flask_login = True

try:
    from sqlalchemy.exc import SQLAlchemyError as UserLoadingError
except ImportError:
    # Just in case sqlalchemy isn't even used
    class UserLoadingError(Exception):
        pass


from .. import version
from . import checks
from .signals import heartbeat_passed, heartbeat_failed


class HeartbeatFailure(InternalServerError):
    pass


class Dockerflow(object):
    """
    The Dockerflow Flask extension. Set it up like this:

    .. code-block:: python
       :caption: ``myproject.py``

       from flask import Flask
       from dockerflow.flask import Dockerflow

       app = Flask(__name__)
       dockerflow = Dockerflow(app)

    Or if you use the Flask application factory pattern, in
    an own module set up Dockerflow first:

    .. code-block:: python
       :caption: ``myproject/deployment.py``

       from dockerflow.flask import Dockerflow

       dockerflow = Dockerflow()

    and then import and initialize it with the Flask application
    object when you create the application:

    .. code-block:: python
       :caption: ``myproject/app.py``

       def create_app(config_filename):
           app = Flask(__name__)
           app.config.from_pyfile(config_filename)

           from myproject.deployment import dockerflow
           dockerflow.init_app(app)

           from myproject.views.admin import admin
           from myproject.views.frontend import frontend
           app.register_blueprint(admin)
           app.register_blueprint(frontend)

            return app

    See the parameters for a more detailed list of optional features when
    initializing the extension.

    :param app: The Flask app that this Dockerflow extension should be
                initialized with.
    :type root: ~flask.Flask or None

    :param db: A Flask-SQLAlchemy extension instance to be used by the
               built-in Dockerflow check for the database connection.
    :param redis: A Redis connection to be used by the built-in Dockerflow
                  check for the Redis connection.
    :param migrate: A Flask-Migrate extension instance to be used by the
                    built-in Dockerflow check for Alembic migrations.
    :param silenced_checks: Dockerflow check IDs to ignore when running
                            through the list of configured checks.
    :type silenced_checks: list

    :param version_path: The filesystem path where the ``version.json`` can
                         be found. Defaults to the parent directory of the
                         Flask app's root path.
    """

    def __init__(self, app=None, db=None, redis=None, migrate=None,
                 silenced_checks=None, version_path=None, *args, **kwargs):
        # The Flask blueprint to add the Dockerflow signal callbacks and views
        self._blueprint = Blueprint('dockerflow', 'dockerflow.flask.app')

        # The Dockerflow specific logger to be used by internals of this
        # extension.
        self.logger = logging.getLogger('dockerflow.flask')
        self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logging.INFO)

        # The request summary logger to be used by this extension
        # without pre-configuration. See docs for how to set it up.
        self.summary_logger = logging.getLogger('request.summary')

        # An ordered dictionary for storing custom Dockerflow checks in.
        self.checks = OrderedDict()

        # A list of IDs of custom Dockerflow checks to ignore in case they
        # show up.
        self.silenced_checks = silenced_checks or []

        # The path where to find the version JSON file. Defaults to the
        # parent directory of the app root path.
        self.version_path = version_path
        self._version_callback = version.get_version

        # Initialize the app if given.
        if app:
            self.init_app(app)
        # Initialize the built-in checks.
        if db:
            self.init_check(checks.check_database_connected, db)
        if redis:
            self.init_check(checks.check_redis_connected, redis)
        if migrate:
            self.init_check(checks.check_migrations_applied, migrate)

    def init_check(self, check, obj):
        """
        Adds a given check callback with the provided object to the list
        of checks. Useful for built-ins but also advanced custom checks.
        """
        self.logger.info('Adding extension check %s' % check.__name__)
        check = functools.wraps(check)(functools.partial(check, obj))
        self.check(func=check)

    def init_app(self, app):
        """
        Initializes the extension with the given app, registers the
        built-in views with an own blueprint and hooks up our signal
        callbacks.
        """
        # If no version path was provided in the init of the Dockerflow
        # class we'll use the parent directory of the app root path.
        if self.version_path is None:
            self.version_path = os.path.dirname(app.root_path)

        for view in (
            ('/__version__', 'version', self._version_view),
            ('/__heartbeat__', 'heartbeat', self._heartbeat_view),
            ('/__lbheartbeat__', 'lbheartbeat', self._lbheartbeat_view),
        ):
            self._blueprint.add_url_rule(*view)
        self._blueprint.before_app_request(self._before_request)
        self._blueprint.after_app_request(self._after_request)
        self._blueprint.app_errorhandler(HeartbeatFailure)(self._heartbeat_exception_handler)
        app.register_blueprint(self._blueprint)
        got_request_exception.connect(self._got_request_exception, sender=app)

        if not hasattr(app, 'extensions'):  # pragma: nocover
            app.extensions = {}
        app.extensions['dockerflow'] = self

    def _heartbeat_exception_handler(self, error):
        """
        An exception handler to act as a middleman to return
        a heartbeat view response with a 500 error code.
        """
        return error.get_response()

    def _before_request(self):
        """
        The before_request callback.
        """
        g._request_id = str(uuid.uuid4())
        g._start_timestamp = time.time()

    def _after_request(self, response):
        """
        The signal handler for the request_finished signal.
        """
        if not getattr(g, '_has_exception', False):
            extra = self.summary_extra()
            self.summary_logger.info('', extra=extra)
        return response

    def _got_request_exception(self, sender, exception, **extra):
        """
        The signal handler for the got_request_exception signal.
        """
        extra = self.summary_extra()
        extra['errno'] = 500
        self.summary_logger.error(str(exception), extra=extra)
        g._has_exception = True

    def user_id(self):
        """
        Return the ID of the current request's user
        """
        # This needs flask-login to be installed
        if not has_flask_login:
            return

        # and the actual login manager installed
        if not hasattr(current_app, 'login_manager'):
            return

        # fail if no current_user was attached to the request context
        try:
            is_authenticated = current_user.is_authenticated
        except AttributeError:
            return

        # because is_authenticated could be a callable, call it
        if callable(is_authenticated):
            is_authenticated = is_authenticated()

        # and fail if the user isn't authenticated
        if not is_authenticated:
            return

        # finally return the user id
        try:
            return current_user.get_id()
        except UserLoadingError:
            # but don't fail if for some reason getting the user id
            # created an exception to not accidently make exception
            # handling worse. If sqlalchemy is used that catches
            # all SQLAlchemyError exceptions.
            pass

    def summary_extra(self):
        """
        Build the extra data for the summary logger.
        """
        out = {
            'errno': 0,
            'agent': request.headers.get('User-Agent', ''),
            'lang': request.headers.get('Accept-Language', ''),
            'method': request.method,
            'path': request.path,
        }

        # set the uid value to the current user ID
        user_id = self.user_id()
        if user_id is None:
            user_id = ''
        out['uid'] = user_id

        # the rid value to the current request ID
        request_id = g.get('_request_id', None)
        if request_id is not None:
            out['rid'] = request_id

        # and the t value to the time it took to render
        start_timestamp = g.get('_start_timestamp', None)
        if start_timestamp is not None:
            # Duration of request, in milliseconds.
            out['t'] = int(1000 * (time.time() - start_timestamp))

        return out

    def _version_view(self):
        """
        View that returns the contents of version.json or a 404.
        """
        version_json = self._version_callback(self.version_path)
        if version_json is None:
            return 'version.json not found', 404
        else:
            return jsonify(version_json)

    def _lbheartbeat_view(self):
        """
        Lets the load balancer know the application is running and available.
        Must return 200 (not 204) for ELB
        http://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
        """
        return '', 200

    def _heartbeat_check_detail(self, check):
        errors = list(filter(lambda e: e.id not in self.silenced_checks, check()))
        level = max([0] + [e.level for e in errors])

        return {
            'status': checks.level_to_text(level),
            'level': level,
            'messages': {e.id: e.msg for e in errors},
        }

    def _heartbeat_view(self):
        """
        Runs all the registered checks and returns a JSON response with either
        a status code of 200 or 500 depending on the results of the checks.

        Any check that returns a warning or worse (error, critical) will
        return a 500 response.
        """
        details = {}
        statuses = {}
        level = 0

        for name, check in self.checks.items():
            detail = self._heartbeat_check_detail(check)
            statuses[name] = detail['status']
            level = max(level, detail['level'])
            if detail['level'] > 0:
                details[name] = detail

        payload = {
            'status': checks.level_to_text(level),
            'checks': statuses,
            'details': details,
        }

        def render(status_code):
            return make_response(jsonify(payload), status_code)

        if level < checks.WARNING:
            status_code = 200
            heartbeat_passed.send(self, level=level)
            return render(status_code)
        else:
            status_code = 500
            heartbeat_failed.send(self, level=level)
            raise HeartbeatFailure(response=render(status_code))

    def version_callback(self, func):
        """
        A decorator to optionally register a new Dockerflow version callback
        and use that instead of the default of
        :func:`dockerflow.version.get_version`.

        The callback will be passed the value of the
        ``version_path`` parameter to the Dockerflow extension object,
        which defaults to the parent directory of the Flask app's root path.

        The callback should return a dictionary with the
        version information as defined in the Dockerflow spec,
        or None if no version information could be loaded.

        E.g.::

            app = Flask(__name__)
            dockerflow = Dockerflow(app)

            @dockerflow.version_callback
            def my_version(root):
                return json.loads(os.path.join(root, 'acme_version.json'))

        """
        self._version_callback = func

    def check(self, func=None, name=None):
        """
        A decorator to register a new Dockerflow check to be run
        when the /__heartbeat__ endpoint is called., e.g.::

            from dockerflow.flask import checks

            @dockerflow.check
            def storage_reachable():
                try:
                    acme.storage.ping()
                except SlowConnectionException as exc:
                    return [checks.Warning(exc.msg, id='acme.health.0002')]
                except StorageException as exc:
                    return [checks.Error(exc.msg, id='acme.health.0001')]

        or using a custom name::

            @dockerflow.check(name='acme-storage-check)
            def storage_reachable():
                # ...

        """
        if func is None:
            return functools.partial(self.check, name=name)

        if name is None:
            name = func.__name__

        self.logger.info('Registered Dockerflow check %s', name)

        @functools.wraps(func)
        def decorated_function(*args, **kwargs):
            self.logger.info('Called Dockerflow check %s', name)
            return func(*args, **kwargs)

        self.checks[name] = decorated_function
        return decorated_function
