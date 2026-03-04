import logging
import os

from fastapi import Request, Response

from dockerflow import checks

from ..version import get_version

logger = logging.getLogger(__name__)


def lbheartbeat():
    return {"status": "ok"}


async def heartbeat(request: Request, response: Response):
    FAILED_STATUS_CODE = int(
        getattr(request.app.state, "DOCKERFLOW_HEARTBEAT_FAILED_STATUS_CODE", "500")
    )

    check_results = await checks.run_checks_async(
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
        response.status_code = FAILED_STATUS_CODE

    return payload


def version(request: Request):
    if getattr(request.app.state, "APP_DIR", None):
        root = request.app.state.APP_DIR
    elif os.getenv("APP_DIR"):
        root = os.getenv("APP_DIR")
    else:
        root = "/app"
    return get_version(root)


def error(request: Request):
    """
    A view that raises an exception, used to test error handling.
    """
    logger.error("The __error__ endpoint was called")
    raise Exception("This is a test exception from the /__error__ endpoint.")
