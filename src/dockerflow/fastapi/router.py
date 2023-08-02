import os

from fastapi import Request, Response
from fastapi.routing import APIRouter


from ..version import get_version
dockerflow_router = APIRouter(tags=["Dockerflow"])


@dockerflow_router.get("/__lbheartbeat__")
@dockerflow_router.head("/__lbheartbeat__")
def lbheartbeat():
    return {"status": "ok"}


@dockerflow_router.get("/__version__")
def version(request: Request):
    if getattr(request.app.state, "APP_DIR", None):
        root = request.app.state.APP_DIR
    elif os.getenv("APP_DIR"):
        root = os.getenv("APP_DIR")
    else:
        root = "/app"
    return get_version(root)
