# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
During the rendering of the ``/__heartbeat__`` Django view two signals are
being sent to hook into the result of the checks:

.. data:: dockerflow.django.signals.heartbeat_passed

   The signal that is sent when the heartbeat checks pass successfully.

.. data:: dockerflow.django.signals.heartbeat_failed

   The signal that is sent when the heartbeat checks raise either a
   warning or worse (error, critical)

Both signals receive an additional ``level`` parameter that indicates the
maximum check level that failed during the rendering.

E.g. to hook into those signals to send data to statsd, do this:

.. code-block:: python

    from django.dispatch import receiver
    from dockerflow.django.signals import heartbeat_passed, heartbeat_failed
    from statsd.defaults.django import statsd

    @receiver(heartbeat_passed)
    def heartbeat_passed_handler(sender, level, **kwargs):
        statsd.incr('heartbeat.pass')

    @receiver(heartbeat_failed)
    def heartbeat_failed_handler(sender, level, **kwargs):
        statsd.incr('heartbeat.fail')
"""
from django.dispatch import Signal

heartbeat_passed = Signal(providing_args=['level'])
heartbeat_failed = Signal(providing_args=['level'])
