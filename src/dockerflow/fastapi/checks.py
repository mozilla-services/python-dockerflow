from dataclasses import dataclass
import functools
import logging
from typing import Dict, List, Tuple

from ..checks import level_to_text

logger = logging.getLogger(__name__)


@dataclass
class CheckDetail:
    status: str
    level: int
    messages: Dict[int, str]


registered_checks = dict()


def check(func, name=None):
    if name is None:
        name = func.__name__

    logger.debug("Registered Dockerflow check %s", name)

    @functools.wraps(func)
    def decorated_function(*args, **kwargs):
        logger.debug("Called Dockerflow check %s", name)
        return func(*args, **kwargs)

    registered_checks[name] = decorated_function
    return decorated_function


def _heartbeat_check_detail(check):
    errors = check()
    level = max([0] + [e.level for e in errors])
    return CheckDetail(
        status=level_to_text(level), level=level, messages={e.id: e.msg for e in errors}
    )


def run_checks():
    check_details: List[Tuple[str, CheckDetail]] = []
    for name, check in registered_checks.items():
        detail = _heartbeat_check_detail(check)
        check_details.append((name, detail))
    return check_details
