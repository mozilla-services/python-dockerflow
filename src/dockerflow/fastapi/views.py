import os

from fastapi import Request, Response

from dockerflow import checks

from ..version import get_version


def lbheartbeat():
    return {"status": "ok"}


def heartbeat(response: Response):
    check_results = checks.run_checks(
        checks.get_checks().items(),
    )

    payload = {
        "status": checks.level_to_text(check_results.level),
        "checks": check_results.statuses,
        "details": check_results.details,
    }

    if check_results.level < checks.ERROR:
        response.status_code = 200
    else:
        response.status_code = 500

    return payload


def version(request: Request):
    if getattr(request.app.state, "APP_DIR", None):
        root = request.app.state.APP_DIR
    elif os.getenv("APP_DIR"):
        root = os.getenv("APP_DIR")
    else:
        root = "/app"
    return get_version(root)
