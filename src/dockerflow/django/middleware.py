import logging
import re
import time
import typing
import urllib

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from dockerflow.logging import get_or_generate_request_id, request_id_context

from . import views


def extract_request_id(request):
    """Extract request ID from request."""
    rid = get_or_generate_request_id(
        request.headers,
        header_name=getattr(settings, "DOCKERFLOW_REQUEST_ID_HEADER_NAME", None),
    )
    request_id_context.set(rid)
    request._id = rid  # Used in tests.


class DockerflowMiddleware(MiddlewareMixin):
    """
    Emits a request.summary type log entry for every request.
    https://github.com/mozilla-services/Dockerflow/blob/main/docs/mozlog.md
    """

    viewpatterns: typing.ClassVar = [
        (re.compile(r"/__version__/?$"), views.version),
        (re.compile(r"/__heartbeat__/?$"), views.heartbeat),
        (re.compile(r"/__lbheartbeat__/?$"), views.lbheartbeat),
    ]

    def __init__(self, get_response=None, *args, **kwargs):
        super(DockerflowMiddleware, self).__init__(
            get_response=get_response, *args, **kwargs
        )
        self.summary_logger = logging.getLogger("request.summary")

    def process_request(self, request):
        for pattern, view in self.viewpatterns:
            if pattern.match(request.path_info):
                return view(request)

        extract_request_id(request)

        request._start_timestamp = time.time()
        return None

    def _build_extra_meta(self, request):
        out = {
            "errno": 0,
            "agent": request.META.get("HTTP_USER_AGENT", ""),
            "lang": request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            "method": request.method,
            "path": request.path,
        }

        if getattr(settings, "DOCKERFLOW_SUMMARY_LOG_QUERYSTRING", False):
            out["querystring"] = urllib.parse.unquote(
                request.META.get("QUERY_STRING", "")
            )

        # HACK: It's possible some other middleware has replaced the request we
        # modified earlier, so be sure to check for existence of these
        # attributes before trying to use them.
        if hasattr(request, "user"):
            out["uid"] = request.user.is_authenticated and request.user.pk or ""
        out["rid"] = request_id_context.get()
        if hasattr(request, "_start_timestamp"):
            # Duration of request, in milliseconds.
            out["t"] = int(1000 * (time.time() - request._start_timestamp))

        return out

    def process_response(self, request, response):
        if not getattr(request, "_has_exception", False):
            extra = self._build_extra_meta(request)
            self.summary_logger.info("", extra=extra)
        return response

    def process_exception(self, request, exception):
        extra = self._build_extra_meta(request)
        extra["errno"] = 500
        self.summary_logger.error(str(exception), extra=extra)
        request._has_exception = True
        return None
