# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from django.core import checks


@checks.register
def error(app_configs, **kwargs):
    return [checks.Error('some error', id='tests.checks.E001')]


@checks.register
def warning(app_configs, **kwargs):
    return [checks.Warning('some warning', id='tests.checks.W001')]
