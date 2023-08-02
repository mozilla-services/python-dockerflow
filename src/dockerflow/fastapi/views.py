import os

from fastapi import Request, Response

from dockerflow import checks

from ..version import get_version
from .checks import run_heartbeat_checks


def lbheartbeat():
    return {"status": "ok"}


def heartbeat(response: Response):
    check_results = run_heartbeat_checks()
    details = {}
    statuses = {}
    level = 0

    for name, detail in check_results:
        statuses[name] = detail.status
        level = max(level, detail.level)
        if detail.level > 0:
            details[name] = detail

    if level < checks.ERROR:
        response.status_code = 200
    else:
        response.status_code = 500

    return {
        "status": checks.level_to_text(level),
        "checks": statuses,
        "details": details,
    }


def version(request: Request):
    if getattr(request.app.state, "APP_DIR", None):
        root = request.app.state.APP_DIR
    elif os.getenv("APP_DIR"):
        root = os.getenv("APP_DIR")
    else:
        root = "/app"
    return get_version(root)
