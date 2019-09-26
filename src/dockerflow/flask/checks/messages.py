# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
This exposes dockerflow.checks.messages as dockerflow.flask.checks.messages
for backwards compatibility
"""
import warnings

from ...checks.messages import *  # noqa

warnings.warn(
    "dockerflow.flask.checks.messages has moved to dockerflow.checks.messages",
    PendingDeprecationWarning,
)
