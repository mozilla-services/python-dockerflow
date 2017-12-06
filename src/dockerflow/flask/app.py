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


from .. import version
from . import checks
from .signals import heartbeat_passed, heartbeat_failed


class HeartbeatFailure(InternalServerError):
    pass


class Dockerflow(object):

    def __init__(self, app=None, db=None, redis=None, migrate=None,
                 silenced_checks=None, version_path=None, *args, **kwargs):
        self.blueprint = Blueprint('dockerflow', 'dockerflow.flask.app')
        self.logger = logging.getLogger('dockerflow.flask')
        self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logging.INFO)
        self.checks = OrderedDict()
        self.summary_logger = logging.getLogger('request.summary')
        self.silenced_checks = silenced_checks or []
        self.version_path = version_path
        self._version_callback = version.get_version
        if app:
            self.init_app(app)
        if db:
            self.init_extension(checks.check_database_connected, db)
        if redis:
            self.init_extension(checks.check_redis_connected, redis)
        # if migrate:
        #     self.init_migrate(migrate)

    def init_extension(self, check, obj):
        self.logger.info('Adding extension check %s' % check.__name__)
        check = functools.wraps(check)(functools.partial(check, obj))
        self.check(func=check)

    def init_app(self, app):
        if self.version_path is None:
            self.version_path = os.path.dirname(app.root_path)

        for view in (
            ('/__version__', 'version', self.version),
            ('/__heartbeat__', 'heartbeat', self.heartbeat),
            ('/__lbheartbeat__', 'lbheartbeat', self.lbheartbeat),
        ):
            self.blueprint.add_url_rule(*view)
        self.blueprint.before_app_request(self.before_request)
        self.blueprint.after_app_request(self.after_request)
        self.blueprint.app_errorhandler(HeartbeatFailure)(self.heartbeat_exception_handler)
        app.register_blueprint(self.blueprint)
        got_request_exception.connect(self.got_request_exception, sender=app)

        if not hasattr(app, 'extensions'):  # pragma: nocover
            app.extensions = {}
        app.extensions['dockerflow'] = self

    def heartbeat_exception_handler(self, error):
        """
        An exception handler to act as a middleman to return
        a heartbeat view response with a 500 error code.
        """
        return error.get_response()

    def before_request(self):
        """
        The before_request callback.
        """
        g._request_id = str(uuid.uuid4())
        g._start_timestamp = time.time()

    def after_request(self, response):
        """
        The signal handler for the request_finished signal.
        """
        extra = self.summary_extra()
        self.summary_logger.info('', extra=extra)
        return response

    def got_request_exception(self, sender, exception, **extra):
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
        return current_user.get_id()

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

    def version(self):
        """
        View that returns the contents of version.json or a 404.
        """
        version_json = self._version_callback(self.version_path)
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

    def heartbeat_check_detail(self, check):
        errors = list(filter(lambda e: e.id not in self.silenced_checks, check()))
        level = max([0] + [e.level for e in errors])

        return {
            'status': checks.level_to_text(level),
            'level': level,
            'messages': {e.id: e.msg for e in errors},
        }

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
            detail = self.heartbeat_check_detail(check)
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

        self.logger.info('Registered Dockerflow check %s', name)

        @functools.wraps(func)
        def decorated_function(*args, **kwargs):
            self.logger.info('Called Dockerflow check %s', name)
            return func(*args, **kwargs)

        self.checks[name] = decorated_function
        return decorated_function
