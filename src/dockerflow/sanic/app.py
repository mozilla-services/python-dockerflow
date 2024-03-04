# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import time
import urllib
import warnings
from inspect import isawaitable

from sanic import response

from dockerflow import checks
from dockerflow.logging import get_or_generate_request_id, request_id_context

from .. import version
from .checks import check_redis_connected


def extract_request_id(request):
    """Extract request ID from request."""
    rid = get_or_generate_request_id(
        request.headers,
        header_name=request.app.config.get("DOCKERFLOW_REQUEST_ID_HEADER_NAME", None),
    )
    request_id_context.set(rid)
    request.ctx.id = rid  # For retro-compatibility and tests.


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
        **kwargs,
    ):
        # The Dockerflow specific logger to be used by internals of this
        # extension.
        self.logger = logging.getLogger("dockerflow.sanic")
        self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logging.INFO)

        # The request summary logger to be used by this extension
        # without pre-configuration. See docs for how to set it up.
        self.summary_logger = logging.getLogger("request.summary")

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
            checks.register_partial(check_redis_connected, redis)

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
        app.middleware("request")(extract_request_id)
        app.middleware("request")(self._request_middleware)
        app.middleware("response")(self._response_middleware)
        app.exception(Exception)(self._exception_handler)

    def _request_middleware(self, request):
        """
        The request middleware.
        """
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
        self.summary_logger.error(str(exception), extra=extra, exc_info=exception)
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

        if request.app.config.get("DOCKERFLOW_SUMMARY_LOG_QUERYSTRING", False):
            out["querystring"] = urllib.parse.unquote(request.query_string)

        # the rid value to the current request ID
        out["rid"] = request_id_context.get()

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

    async def _heartbeat_view(self, request):
        """
        Runs all the registered checks and returns a JSON response with either
        a status code of 200 or 500 depending on the results of the checks.

        Any check that returns a warning or worse (error, critical) will
        return a 500 response.
        """
        FAILED_STATUS_CODE = int(
            request.app.config.get("DOCKERFLOW_HEARTBEAT_FAILED_STATUS_CODE", "500")
        )

        check_results = await checks.run_checks_async(
            checks.get_checks().items(),
            silenced_check_ids=self.silenced_checks,
        )

        payload = {
            "status": checks.level_to_text(check_results.level),
            "checks": check_results.statuses,
            "details": check_results.details,
        }

        if check_results.level < checks.ERROR:
            status_code = 200
        else:
            status_code = FAILED_STATUS_CODE

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

    @property
    def checks(self):
        """
        Backwards compatibility alias.
        """
        message = (
            "`dockerflow.checks` is deprecated, use `checks.get_checks()` instead."
        )
        warnings.warn(message, DeprecationWarning)
        return checks.get_checks()

    def init_check(self, check, obj):
        """
        Backwards compatibility method.
        """
        message = "`dockerflow.init_check()` is deprecated, use `checks.register_partial()` instead."
        warnings.warn(message, DeprecationWarning)
        return checks.register_partial(check, obj)

    def check(self, func=None, name=None):
        """
        Backwards compatibility method.
        """
        message = "`dockerflow.check()` is deprecated, use `checks.register()` instead."
        warnings.warn(message, DeprecationWarning)
        return checks.register(func, name)
