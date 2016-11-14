# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
from django.db import connection
from django.test.utils import CaptureQueriesContext

from dockerflow.django import checks
import pytest


# as documented on https://github.com/mozilla-services/Dockerflow/blob/master/docs/version_object.md
version_content = {
    'source': 'https://github.com/mozilla-services/python-dockerflow',
    'version': 'release tag or string for humans',
    'commit': '<git hash>',
    'build': 'uri to CI build job'
}


def test_version_exists(client, mocker):
    mocker.patch('dockerflow.version.get_version', return_value=version_content)
    response = client.get('/__version__')
    assert response.status_code == 200
    assert json.loads(response.content.decode()) == version_content


def test_version_missing(client, mocker):
    mocker.patch('dockerflow.version.get_version', return_value=None)
    response = client.get('/__version__')
    assert response.status_code == 404


@pytest.mark.django_db
def test_heartbeat(client, reset_checks, settings):
    response = client.get('/__heartbeat__')
    assert response.status_code == 200

    settings.DOCKERFLOW_CHECKS = [
        'tests.checks.warning',
        'tests.checks.error',
    ]
    checks.register()
    response = client.get('/__heartbeat__')
    assert response.status_code == 500


@pytest.mark.django_db
def test_lbheartbeat_makes_no_db_queries(client):
    queries = CaptureQueriesContext(connection)
    with queries:
        res = client.get('/__lbheartbeat__')
        assert res.status_code == 200
    assert len(queries) == 0


@pytest.mark.django_db
def test_redis_check(client, reset_checks, settings):
    settings.DOCKERFLOW_CHECKS = [
        'dockerflow.django.checks.check_redis_connected',
    ]
    checks.register()
    response = client.get('/__heartbeat__')
    assert response.status_code == 200
