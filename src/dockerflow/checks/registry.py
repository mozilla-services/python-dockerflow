# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import functools
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .messages import CheckMessage, level_to_text

logger = logging.getLogger(__name__)

CheckFn = Callable[..., List[CheckMessage]]

_REGISTERED_CHECKS = {}


def _iscoroutinefunction_or_partial(obj):
    """
    Determine if the provided object is a coroutine function or a partial function
    that wraps a coroutine function.

    This function should be removed when we drop support for Python 3.7, as this is
    handled directly by `inspect.iscoroutinefunction` in Python 3.8.
    """
    while isinstance(obj, functools.partial):
        obj = obj.func
    return inspect.iscoroutinefunction(obj)


def register(func=None, name=None):
    """
    Register a check callback to be executed from
    the heartbeat endpoint.
    """
    if func is None:
        return functools.partial(register, name=name)

    if name is None:
        name = func.__name__

    logger.debug("Register Dockerflow check %s", name)

    if _iscoroutinefunction_or_partial(func):

        @functools.wraps(func)
        async def decorated_function_asyc(*args, **kwargs):
            logger.debug("Called Dockerflow check %s", name)
            return await func(*args, **kwargs)

        _REGISTERED_CHECKS[name] = decorated_function_asyc
        return decorated_function_asyc

    @functools.wraps(func)
    def decorated_function(*args, **kwargs):
        logger.debug("Called Dockerflow check %s", name)
        return func(*args, **kwargs)

    _REGISTERED_CHECKS[name] = decorated_function
    return decorated_function


def register_partial(func, *args, name=None):
    """
    Registers a given check callback that will be called with the provided
    arguments using `functools.partial()`. For example:

    .. code-block:: python

        dockerflow.register_partial(check_redis_connected, redis)

    """
    if name is None:
        name = func.__name__

    logger.debug("Register Dockerflow check %s with partially applied arguments" % name)
    partial = functools.wraps(func)(functools.partial(func, *args))
    return register(func=partial, name=name)


def get_checks():
    return _REGISTERED_CHECKS


def clear_checks():
    global _REGISTERED_CHECKS
    _REGISTERED_CHECKS = dict()


@dataclass
class ChecksResults:
    """
    Represents the results of running checks.

    This data class holds the results of running a collection of checks. It includes
    details about each check's outcome, their statuses, and the overall result level.

    :param details: A dictionary containing detailed information about each check's
        outcome, with check names as keys and dictionaries of details as values.
    :type details: Dict[str, Dict[str, Any]]

    :param statuses: A dictionary containing the status of each check, with check names
        as keys and statuses as values (e.g., 'pass', 'fail', 'warning').
    :type statuses: Dict[str, str]

    :param level: An integer representing the overall result level of the checks
    :type level: int
    """

    details: Dict[str, Dict[str, Any]]
    statuses: Dict[str, str]
    level: int


async def _run_check_async(check):
    name, check_fn = check
    if _iscoroutinefunction_or_partial(check_fn):
        errors = await check_fn()
    else:
        loop = asyncio.get_event_loop()
        errors = await loop.run_in_executor(None, check_fn)

    return (name, errors)


async def run_checks_async(
    checks: Iterable[Tuple[str, CheckFn]],
    silenced_check_ids: Optional[Iterable[str]] = None,
) -> ChecksResults:
    """
    Run checks concurrently and return the results.

    Executes a collection of checks concurrently, supporting both synchronous and
    asynchronous checks. The results include the outcome of each check and can be
    further processed.

    :param checks: An iterable of tuples where each tuple contains a check name and a
        check function.
    :type checks: Iterable[Tuple[str, CheckFn]]

    :param silenced_check_ids: A list of check IDs that should be omitted from the
        results.
    :type silenced_check_ids: List[str]

    :return: An instance of ChecksResults containing detailed information about each
        check's outcome, their statuses, and the overall result level.
    :rtype: ChecksResults
    """
    if silenced_check_ids is None:
        silenced_check_ids = []

    tasks = (_run_check_async(check) for check in checks)
    results = await asyncio.gather(*tasks)
    return _build_results_payload(results, silenced_check_ids)


def run_checks(
    checks: Iterable[Tuple[str, CheckFn]],
    silenced_check_ids: Optional[Iterable[str]] = None,
) -> ChecksResults:
    """
    Run checks synchronously and return the results.

    Executes a collection of checks and returns the results. The results include the
    outcome of each check and can be further processed.

    :param checks: An iterable of tuples where each tuple contains a check name and a
        check function.
    :type checks: Iterable[Tuple[str, CheckFn]]

    :param silenced_check_ids: A list of check IDs that should be omitted from the
        results.
    :type silenced_check_ids: List[str]

    :return: An instance of ChecksResults containing detailed information about each
        check's outcome, their statuses, and the overall result level.
    :rtype: ChecksResults
    """
    if silenced_check_ids is None:
        silenced_check_ids = []
    results = [(name, check()) for name, check in checks]
    return _build_results_payload(results, silenced_check_ids)


def _build_results_payload(
    checks_results: Iterable[Tuple[str, Iterable[CheckMessage]]],
    silenced_check_ids,
):
    details = {}
    statuses = {}
    max_level = 0

    for name, errors in checks_results:
        # Log check results with appropriate level.
        for error in errors:
            logger.log(error.level, "%s: %s", error.id, error.msg)

        errors = [e for e in errors if e.id not in silenced_check_ids]
        level = max([0] + [e.level for e in errors])

        detail = {
            "status": level_to_text(level),
            "level": level,
            "messages": {e.id: e.msg for e in errors},
        }
        statuses[name] = level_to_text(level)
        max_level = max(max_level, level)
        if level > 0:
            details[name] = detail

    return ChecksResults(statuses=statuses, details=details, level=max_level)
