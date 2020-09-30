# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import functools
import logging
import time
import uuid
from collections import OrderedDict
from inspect import isawaitable

from sanic import response

from .. import version
from . import checks


class Dockerflow(object):
    """
    The Dockerflow Sanic extension. Set it up like this:

    .. code-block:: python
       :caption: ``myproject.py``

       from sanic import Sanic
       from dockerflow.sanic import Dockerflow

       app = Sanic(__name__)
       dockerflow = Dockerflow(app)

    Or if you use the Sanic application factory pattern, in
    an own module set up Dockerflow first:

    .. code-block:: python
       :caption: ``myproject/deployment.py``

       from dockerflow.sanic import Dockerflow

       dockerflow = Dockerflow()

    and then import and initialize it with the Sanic application
    object when you create the application:

    .. code-block:: python
       :caption: ``myproject/app.py``

       def create_app(config_filename):
           app = Sanic(__name__)
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

    :param app: The Sanic app that this Dockerflow extension should be
                initialized with.
    :type app: ~sanic.Sanic or None

    :param redis: A SanicRedis instance to be used by the built-in Dockerflow
                  check for the sanic_redis connection.
    :param silenced_checks: Dockerflow check IDs to ignore when running
                            through the list of configured checks.
    :type silenced_checks: list

    :param version_path: The filesystem path where the ``version.json`` can
                         be found. Defaults to ``.``.
    """

    def __init__(
        self,
        app=None,
        redis=None,
        silenced_checks=None,
        version_path=".",
        *args,
        **kwargs
    ):

        # The Dockerflow specific logger to be used by internals of this
        # extension.
        self.logger = logging.getLogger("dockerflow.sanic")
        self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logging.INFO)

        # The request summary logger to be used by this extension
        # without pre-configuration. See docs for how to set it up.
        self.summary_logger = logging.getLogger("request.summary")

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
        if redis is not None:
            self.init_check(checks.check_redis_connected, redis)

    def init_check(self, check, obj):
        """
        Adds a given check callback with the provided object to the list
        of checks. Useful for built-ins but also advanced custom checks.
        """
        self.logger.info("Adding extension check %s" % check.__name__)
        partial = functools.wraps(check)(functools.partial(check, obj))
        self.check(func=partial)

    def init_app(self, app):
        """
        Add the Dockerflow views and middleware to app.
        """
        for uri, name, handler in (
            ("/__version__", "version", self._version_view),
            ("/__heartbeat__", "heartbeat", self._heartbeat_view),
            ("/__lbheartbeat__", "lbheartbeat", self._lbheartbeat_view),
        ):
            app.add_route(handler, uri, name="dockerflow." + name)
        app.middleware("request")(self._request_middleware)
        app.middleware("response")(self._response_middleware)
        app.exception(Exception)(self._exception_handler)

    def _request_middleware(self, request):
        """
        The request middleware.
        """
        request.ctx.id = str(uuid.uuid4())
        request.ctx.start_timestamp = time.time()

    def _response_middleware(self, request, response):
        """
        The response middleware.
        """
        if not getattr(request.ctx, "logged", False):
            extra = self.summary_extra(request)
            self.summary_logger.info("", extra=extra)

    def _exception_handler(self, request, exception):
        """
        The exception handler.
        """
        extra = self.summary_extra(request)
        extra["errno"] = 500
        self.summary_logger.error(str(exception), extra=extra)
        request.ctx.logged = True

    def summary_extra(self, request):
        """
        Build the extra data for the summary logger.
        """
        out = {
            "errno": 0,
            "agent": request.headers.get("User-Agent", ""),
            "lang": request.headers.get("Accept-Language", ""),
            "method": request.method,
            "path": request.path,
            "uid": "",
        }

        # the rid value to the current request ID
        try:
            out["rid"] = request.ctx.id
        except AttributeError:
            pass

        # and the t value to the time it took to render
        try:
            # Duration of request, in milliseconds.
            out["t"] = int(1000 * (time.time() - request.ctx.start_timestamp))
        except AttributeError:
            pass

        return out

    async def _version_view(self, request):
        """
        View that returns the contents of version.json or a 404.
        """
        version_json = self._version_callback(self.version_path)
        if isawaitable(version_json):
            version_json = await version_json
        if version_json is None:
            return response.raw(b"version.json not found", 404)
        else:
            return response.json(version_json)

    async def _lbheartbeat_view(self, request):
        """
        Lets the load balancer know the application is running and available.
        Must return 200 (not 204) for ELB
        http://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
        """
        return response.raw(b"", 200)

    async def _heartbeat_check_detail(self, check):
        result = check()
        if isawaitable(result):
            result = await result
        errors = [e for e in result if e.id not in self.silenced_checks]
        level = max([0] + [e.level for e in errors])

        return {
            "status": checks.level_to_text(level),
            "level": level,
            "messages": {e.id: e.msg for e in errors},
        }

    async def _heartbeat_view(self, request):
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
            detail = await self._heartbeat_check_detail(check)
            statuses[name] = detail["status"]
            level = max(level, detail["level"])
            if detail["level"] > 0:
                details[name] = detail

        payload = {
            "status": checks.level_to_text(level),
            "checks": statuses,
            "details": details,
        }

        if level < checks.ERROR:
            status_code = 200
        else:
            status_code = 500

        return response.json(payload, status_code)

    def version_callback(self, func):
        """
        A decorator to optionally register a new Dockerflow version callback
        and use that instead of the default of
        :func:`dockerflow.version.get_version`.

        The callback will be passed the value of the
        ``version_path`` parameter to the Dockerflow extension object,
        which defaults to the parent directory of the Sanic app's root path.

        The callback should return a dictionary with the
        version information as defined in the Dockerflow spec,
        or None if no version information could be loaded.

        E.g.::

            import aiofiles

            app = Sanic(__name__)
            dockerflow = Dockerflow(app)

            @dockerflow.version_callback
            async def my_version(root):
                path = os.path.join(root, 'acme_version.json')
                async with aiofiles.open(path, mode='r') as f:
                    raw = await f.read()
                return json.loads(raw)

        """
        self._version_callback = func

    def check(self, func=None, name=None):
        """
        A decorator to register a new Dockerflow check to be run
        when the /__heartbeat__ endpoint is called., e.g.::

            from dockerflow.sanic import checks

            @dockerflow.check
            async def storage_reachable():
                try:
                    acme.storage.ping()
                except SlowConnectionException as exc:
                    return [checks.Warning(exc.msg, id='acme.health.0002')]
                except StorageException as exc:
                    return [checks.Error(exc.msg, id='acme.health.0001')]

        also works without async::

            @dockerflow.check
            def storage_reachable():
                # ...

        or using a custom name::

            @dockerflow.check(name='acme-storage-check')
            async def storage_reachable():
                # ...

        """
        if func is None:
            return functools.partial(self.check, name=name)

        if name is None:
            name = func.__name__

        self.logger.info("Registered Dockerflow check %s", name)

        @functools.wraps(func)
        def decorated_function(*args, **kwargs):
            self.logger.info("Called Dockerflow check %s", name)
            return func(*args, **kwargs)

        self.checks[name] = decorated_function
        return decorated_function
