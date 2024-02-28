from logging import Filter, LogRecord

from asgi_correlation_id import correlation_id
from fastapi import APIRouter
from fastapi.routing import APIRoute

from .views import heartbeat, lbheartbeat, version

router = APIRouter(
    tags=["Dockerflow"],
    routes=[
        APIRoute("/__lbheartbeat__", endpoint=lbheartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__heartbeat__", endpoint=heartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__version__", endpoint=version, methods=["GET"]),
    ],
)
"""This router adds the Dockerflow views."""


class RequestIdLogFilter(Filter):
    """Logging filter to attach request IDs to log records"""

    def filter(self, record: "LogRecord") -> bool:
        """
        Attach the request ID to the log record.
        """
        record.rid = correlation_id.get(None)
        return True
