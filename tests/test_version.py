# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
from dockerflow.version import get_version


def test_get_version(tmpdir):
    content = {'spam': 'eggs'}
    version_json = tmpdir.join('version.json')
    version_json.write(json.dumps(content))

    version = get_version(str(tmpdir))
    assert version == content


def test_no_version_json(tmpdir):
    version = get_version(str(tmpdir))
    assert version is None
