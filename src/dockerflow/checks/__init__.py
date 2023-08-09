# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Tuple

from .messages import (  # noqa
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    STATUSES,
    WARNING,
    CheckMessage,
    Critical,
    Debug,
    Error,
    Info,
    Warning,
    level_to_text,
)

CheckFn = Callable[..., List[CheckMessage]]


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


def iscoroutinefunction_or_partial(obj):
    """
    Determine if the provided object is a coroutine function or a partial function
    that wraps a coroutine function.

    This function checks whether the given object is a coroutine function or a partial
    function that wraps a coroutine function. This function should be removed when we
    drop support for Python 3.7, as this is handled directly by `inspect.iscoroutinefunction`
    in Python 3.8.

    :param obj: The object to be checked for being a coroutine function or partial.
    :type obj: object

    :return: True if the object is a coroutine function or a partial function wrapping
             a coroutine function, False otherwise.
    :rtype: bool
    """
    while isinstance(obj, functools.partial):
        obj = obj.func
    return inspect.iscoroutinefunction(obj)


async def _run_check_async(check):
    name, check_fn = check
    if iscoroutinefunction_or_partial(check_fn):
        errors = await check_fn()
    else:
        loop = asyncio.get_event_loop()
        errors = await loop.run_in_executor(None, check_fn)

    return (name, errors)


async def run_checks_async(
    checks: Iterable[Tuple[str, CheckFn]],
    silenced_check_ids=None,
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
    if not silenced_check_ids:
        silenced_check_ids = []

    tasks = (_run_check_async(check) for check in checks)
    results = await asyncio.gather(*tasks)
    return _build_results_payload(results, silenced_check_ids)


def run_checks(
    checks: Iterable[Tuple[str, CheckFn]],
    silenced_check_ids=None,
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
    if not silenced_check_ids:
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
