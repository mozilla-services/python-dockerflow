# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os

__all__ = ['get_version']


def get_version(root):
    """
    Load and return the contents of version.json.

    :param root: The root path that the ``version.json`` file will be opened
    :type root: str
    :returns: Content of ``version.json`` or None
    :rtype: dict or None
    """
    version_json = os.path.join(root, 'version.json')
    if os.path.exists(version_json):
        with open(version_json, 'r') as version_json_file:
            return json.load(version_json_file)
    return None
