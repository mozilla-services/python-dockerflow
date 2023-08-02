from fastapi import APIRouter
from fastapi.routing import APIRoute

from .checks import register_heartbeat_check  # noqa
from .views import heartbeat, lbheartbeat, version

router = APIRouter(
    tags=["Dockerflow"],
    routes=[
        APIRoute("/__lbheartbeat__", endpoint=lbheartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__heartbeat__", endpoint=heartbeat, methods=["GET", "HEAD"]),
        APIRoute("/__version__", endpoint=version, methods=["GET"]),
    ],
)
