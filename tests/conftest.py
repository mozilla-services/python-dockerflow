# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import pytest

import dockerflow.checks.registry


@pytest.fixture()
def version_content():
    """
    as documented on https://github.com/mozilla-services/Dockerflow/blob/main/docs/version_object.md
    """
    return {
        "source": "https://github.com/mozilla-services/python-dockerflow",
        "version": "release tag or string for humans",
        "commit": "<git hash>",
        "build": "uri to CI build job",
    }


@pytest.fixture(autouse=True)
def _clear_checks():
    yield
    dockerflow.checks.registry.clear_checks()
