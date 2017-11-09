import functools
import os
import logging
import time
import uuid
from collections import OrderedDict

from flask import (current_app, g, got_request_exception, jsonify,
                   make_response, request, request_finished)
try:
    from flask_login import current_user
except ImportError:
    has_flask_login = False
else:
    has_flask_login = True


from ..version import get_version
from . import checks
from .signals import heartbeat_passed, heartbeat_failed

# the dockerflow.flask.app logger
logger = logging.getLogger('dockerflow.flask')
logger.addHandler(logging.NullHandler())


class Dockerflow(object):
    check_statuses = {
        0: 'ok',
        checks.DEBUG: 'debug',
        checks.INFO: 'info',
        checks.WARNING: 'warning',
        checks.ERROR: 'error',
        checks.CRITICAL: 'critical',
    }

    def __init__(self, app=None, *args, **kwargs):
        self.checks = OrderedDict()
        self.summary_logger = logging.getLogger('request.summary')
        self.version_callback = get_version
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.version_path = app.config.get(
            'DOCKERFLOW_VERSION_PATH',
            os.path.dirname(app.root_path)
        )

        app.add_url_rule('/__version__', 'version', self.version)
        app.add_url_rule('/__heartbeat__', 'heartbeat', self.heartbeat)
        app.add_url_rule('/__lbheartbeat__', 'lbheartbeat', self.lbheartbeat)

        app.before_request(self.before_request)
        request_finished.connect(self.after_request, app)
        got_request_exception.connect(self.after_exception, app)

        if 'dockerflow' not in app.extensions:
            app.extensions['dockerflow'] = {}
        app.extensions['dockerflow'] = self

    def before_request(self, *args, **kwargs):
        """
        The before_request callback.
        """
        g._request_id = str(uuid.uuid4())
        g._start_timestamp = time.time()

    def after_request(self, *args, **kwargs):
        """
        The signal handler for the request_finished signal.
        """
        extra = self.summary_extra()
        self.summary_logger.info('', extra=extra)

    def after_exception(self, sender, exception, **extra):
        """
        The signal handler for the got_request_exception signal.
        """
        extra = self.summary_extra()
        extra['errno'] = 500
        self.summary_logger.error(str(exception), extra=extra)

    def user_id(self):
        """
        Return the ID of the current request's user
        """
        # This needs flask-login to be installed
        if not has_flask_login:
            return None

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
        except NotImplementedError:
            # but fail gracefully if the get_id wasn't implemented
            return

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
        out['uid'] = self.user_id() or ''

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

    def version(self):
        """
        View that returns the contents of version.json or a 404.
        """
        version_json = self.version_callback(self.version_path)
        if version_json is None:
            return 'version.json not found', 404
        else:
            return jsonify(version_json)

    def lbheartbeat(self):
        """
        Let the load balancer know the application is running and available
        must return 200 (not 204) for ELB
        http://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
        """
        return '', 200

    def heartbeat(self):
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
            errors = check()

            level = max([0] + [e.level for e in errors])
            detail = {
                'status': checks.level_to_text(level),
                'level': level,
                'messages': {e.id: e.msg for e in errors},
            }

            statuses[name] = detail['status']
            level = max(level, detail['level'])
            if detail['level'] > 0:
                details[name] = detail

        if level < checks.messages.WARNING:
            status_code = 200
            heartbeat_passed.send(self, level=level)
        else:
            status_code = 500
            heartbeat_failed.send(self, level=level)

        payload = {
            'status': checks.level_to_text(level),
            'checks': statuses,
            'details': details,
        }
        return make_response(jsonify(payload), status_code)

    def version_callback(self, func):
        """
        A decorator to optionally register a new Dockerflow version callback
        and use that instead of the default of
        :func:`dockerflow.version.get_version`.

        The callback will be passed the value of the
        ``DOCKERFLOW_VERSION_PATH`` config variable, which defaults to the
        parent directory of the Flask app's root path.
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
        self.version_callback = func

    def check(self, func=None, name=None):
        """
        A decorator to register a new Dockerflow check to be run
        when the /__heartbeat__ endpoint is called, e.g.::

        @dockerflow.check
        def storage_reachable():
            return acme.storage.ping()

        or using a custom name::

        @dockerflow.check(name='acme-storage-check)
        def storage_reachable():
            return acme.storage.ping()

        """
        if func is None:
            return functools.partial(self.check, name=name)

        if name is None:
            name = func.__name__

        logger.debug('Registered Dockerflow check %s', name)

        @functools.wraps(func)
        def decorated_function(*args, **kwargs):
            logger.debug('Called Dockerflow check %s', name)
            return func(*args, **kwargs)

        self.checks[name] = decorated_function
        return decorated_function
