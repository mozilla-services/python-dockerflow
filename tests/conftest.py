# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import pytest


@pytest.fixture
def reset_checks():
    from django.core.checks.registry import registry
    registry.registered_checks = []
    registry.deployment_checks = []


def create_app():
    from dockerflow.flask import Dockerflow
    from flask import Flask

    app = Flask('dockerflow')
    Dockerflow(app)
    return app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def dockerflow(app):
    return app.extensions['dockerflow']
