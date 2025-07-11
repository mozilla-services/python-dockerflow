# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os

from dockerflow.version import get_version


def test_get_version(tmpdir):
    content = {"spam": "eggs"}
    version_json = tmpdir.join("version.json")
    version_json.write(json.dumps(content))

    version = get_version(str(tmpdir))
    assert version == content


def test_no_version_json(tmpdir):
    version = get_version(str(tmpdir))
    assert version is None

def test_env_var_override(tmpdir, mocker):
    content = {"spam": "eggs"}
    mocker.patch.dict(os.environ, { "DOCKERFLOW_VERSION": "foo"})
    version_json = tmpdir.join("version.json")
    version_json.write(json.dumps(content))

    version = get_version(str(tmpdir))
    assert version == {
        "spam": "eggs",
        "version": "foo"
    }

def test_env_var_override_with_no_json(tmpdir, mocker):
    mocker.patch.dict(os.environ, { "DOCKERFLOW_VERSION": "foo"})
    version = get_version(str(tmpdir))
    assert version == {
        "version": "foo"
    }
