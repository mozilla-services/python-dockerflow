import logging
import re
import time
import uuid

from django import VERSION
try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:  # pragma: no cover
    MiddlewareMixin = object

from . import views

# Computed once, reused in every request
_less_than_django_1_10 = VERSION < (1, 10)


def is_authenticated(user):  # pragma: no cover
    """Check if the user is authenticated but do it in a way that
    it doesnt' cause a DeprecationWarning in Django >=1.10"""
    if _less_than_django_1_10:
        # Prior to Django 1.10, user.is_authenticated was a method
        return user.is_authenticated()
    return user.is_authenticated


class DockerflowMiddleware(MiddlewareMixin):
    """
    Emits a request.summary type log entry for every request.
    https://github.com/mozilla-services/Dockerflow/blob/master/docs/mozlog.md
    """
    viewpatterns = [
        (re.compile(r'/__version__$'), views.version),
        (re.compile(r'/__heartbeat__$'), views.heartbeat),
        (re.compile(r'/__lbheartbeat__$'), views.lbheartbeat),
    ]

    def __init__(self, *args, **kwargs):
        super(DockerflowMiddleware, self).__init__(*args, **kwargs)
        self.summary_logger = logging.getLogger('request.summary')

    def process_request(self, request):
        for pattern, view in self.viewpatterns:
            if pattern.match(request.path_info):
                return view(request)

        request._id = str(uuid.uuid4())
        request._start_timestamp = time.time()
        return None

    def _build_extra_meta(self, request):
        out = {
            'errno': 0,
            'agent': request.META.get('HTTP_USER_AGENT', ''),
            'lang': request.META.get('HTTP_ACCEPT_LANGUAGE', ''),
            'method': request.method,
            'path': request.path,
        }

        # HACK: It's possible some other middleware has replaced the request we
        # modified earlier, so be sure to check for existence of these
        # attributes before trying to use them.
        if hasattr(request, 'user'):
            out['uid'] = (
                is_authenticated(request.user) and request.user.pk or ''
            )
        if hasattr(request, '_id'):
            out['rid'] = request._id
        if hasattr(request, '_start_timestamp'):
            # Duration of request, in milliseconds.
            out['t'] = int(1000 * (time.time() - request._start_timestamp))

        return out

    def process_response(self, request, response):
        if not getattr(request, '_has_exception', False):
            extra = self._build_extra_meta(request)
            self.summary_logger.info('', extra=extra)
        return response

    def process_exception(self, request, exception):
        extra = self._build_extra_meta(request)
        extra['errno'] = 500
        self.summary_logger.error(str(exception), extra=extra)
        request._has_exception = True
        return None
