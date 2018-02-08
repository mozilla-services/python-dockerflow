# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
During the rendering of the ``/__heartbeat__`` Flask view two signals are
being sent to hook into the result of the checks:

.. data:: dockerflow.flask.signals.heartbeat_passed

   The signal that is sent when the heartbeat checks pass successfully.

.. data:: dockerflow.flask.signals.heartbeat_failed

   The signal that is sent when the heartbeat checks raise either a
   warning or worse (error, critical)

Both signals receive an additional ``level`` parameter that indicates the
maximum check level that failed during the rendering.

E.g. to hook into those signals to send data to statsd, do this:

.. code-block:: python

    from dockerflow.flask.signals import heartbeat_passed, heartbeat_failed
    from myproject.stats import statsd

    @heartbeat_passed.connect_via(app)
    def heartbeat_passed_handler(sender, level, **extra):
        statsd.incr('heartbeat.pass')

    @heartbeat_failed.connect_via(app)
    def heartbeat_failed_handler(sender, level, **extra):
        statsd.incr('heartbeat.fail')

"""
from flask.signals import Namespace

dockerflow_signals = Namespace()

heartbeat_passed = dockerflow_signals.signal('heartbeat-passed')
heartbeat_failed = dockerflow_signals.signal('heartbeat-failed')
