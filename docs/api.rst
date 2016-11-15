API
===

This page shows the various code paths available in python-dockerflow.

Version
-------

.. automodule:: dockerflow.version
   :members:


Django
------

Checks
``````

The provided checks hook into Django's `system check framework`_ to enable
the :func:`heartbeat view <dockerflow.django.views.heartbeat>` to diagnose
the current health of the Django project.

.. automodule:: dockerflow.django.checks
   :members:

.. _`system check framework`: https://docs.djangoproject.com/en/stable/ref/checks/

Signals
```````

During the rendering of the ``/__heartbeat__`` view two signals are being sent
to hook into the result of the checks:

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

Views
`````

``dockerflow.django`` implements various views so the automatic application
monitoring can happen. They are mounted by including them in the root of a
URL configration:

.. code-block:: python

    urlpatterns = [
        url(r'^', include('dockerflow.django.urls', namespace='dockerflow')),
        # ...
    ]

.. automodule:: dockerflow.django.views
   :members:
