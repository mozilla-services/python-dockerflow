# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django.conf import settings
from django.core import checks
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.utils.module_loading import import_string

from .checks import level_to_text
from .signals import heartbeat_failed, heartbeat_passed


version_callback = getattr(
    settings,
    'DOCKERFLOW_VERSION_CALLBACK',
    'dockerflow.version.get_version',
)


def version(request):
    """
    Returns the contents of version.json or a 404.
    """
    version_json = import_string(version_callback)(settings.BASE_DIR)
    if version_json is None:
        return HttpResponseNotFound('version.json not found')
    else:
        return JsonResponse(version_json)


def lbheartbeat(request):
    """
    Let the load balancer know the application is running and available
    must return 200 (not 204) for ELB
    http://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
    """
    return HttpResponse()


def heartbeat(request):
    """
    Runs all the Django checks and returns a JsonResponse with either
    a status code of 200 or 500 depending on the results of the checks.

    Any check that returns a warning or worse (error, critical) will
    return a 500 response.
    """
    all_checks = checks.registry.registry.get_checks(
        include_deployment_checks=not settings.DEBUG,
    )

    details = {}
    statuses = {}
    level = 0

    for check in all_checks:
        detail = heartbeat_check_detail(check)
        statuses[check.__name__] = detail['status']
        level = max(level, detail['level'])
        if detail['level'] > 0:
            details[check.__name__] = detail

    if level < checks.messages.WARNING:
        status_code = 200
        heartbeat_passed.send(sender=heartbeat, level=level)
    else:
        status_code = 500
        heartbeat_failed.send(sender=heartbeat, level=level)

    payload = {
        'status': level_to_text(level),
        'checks': statuses,
        'details': details,
    }
    return JsonResponse(payload, status=status_code)


def heartbeat_check_detail(check):
    errors = check(app_configs=None)
    errors = list(filter(lambda e: e.id not in settings.SILENCED_SYSTEM_CHECKS, errors))
    level = max([0] + [e.level for e in errors])

    return {
        'status': level_to_text(level),
        'level': level,
        'messages': {e.id: e.msg for e in errors},
    }
