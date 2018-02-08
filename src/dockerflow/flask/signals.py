# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from flask.signals import Namespace

dockerflow_signals = Namespace()

heartbeat_passed = dockerflow_signals.signal('heartbeat-passed')
heartbeat_failed = dockerflow_signals.signal('heartbeat-failed')
