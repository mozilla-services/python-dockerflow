import datetime
import logging
import re
import uuid

try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:  # pragma: no cover
    MiddlewareMixin = object

from . import views


class DockerflowMiddleware(MiddlewareMixin):
    """

    Emit a request.summary type log entry for every request.
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
        request._logging_start_dt = datetime.datetime.utcnow()
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
            out['uid'] = (request.user.is_authenticated() and
                          request.user.pk or '')
        if hasattr(request, '_id'):
            out['rid'] = request._id
        if hasattr(request, '_logging_start_dt'):
            td = datetime.datetime.utcnow() - request._logging_start_dt
            out['t'] = int(td.total_seconds() * 1000)  # in ms

        return out

    def process_response(self, request, response):
        extra = self._build_extra_meta(request)
        self.summary_logger.info('', extra=extra)
        return response

    def process_exception(self, request, exception):
        extra = self._build_extra_meta(request)
        extra['errno'] = 500
        self.summary_logger.error(str(exception), extra=extra)
        return None
