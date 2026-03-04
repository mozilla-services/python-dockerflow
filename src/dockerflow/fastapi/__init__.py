from fastapi import APIRouter
from fastapi.routing import APIRoute

from .views import error, heartbeat, lbheartbeat, version

router = APIRouter(
    tags=["Dockerflow"],
    routes=[
        APIRoute("/__lbheartbeat__", endpoint=lbheartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__heartbeat__", endpoint=heartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__version__", endpoint=version, methods=["GET"]),
        APIRoute("/__error__", endpoint=error, methods=["GET"]),
    ],
)
"""This router adds the Dockerflow views."""
