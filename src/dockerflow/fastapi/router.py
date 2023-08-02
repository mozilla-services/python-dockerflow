from fastapi import Request, Response
from fastapi.routing import APIRouter


dockerflow_router = APIRouter(tags=["Dockerflow"])


@dockerflow_router.get("/__lbheartbeat__")
@dockerflow_router.head("/__lbheartbeat__")
def lbheartbeat():
    return {"status": "ok"}
