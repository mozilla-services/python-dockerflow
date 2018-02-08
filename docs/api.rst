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

.. automodule:: dockerflow.django.signals

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

Flask
-----

This documents the various Flask specific functionality but doesn't cover
internals of the extension.

Extension
`````````

.. automodule:: dockerflow.flask.app
   :members:

Checks
``````

.. automodule:: dockerflow.flask.checks
   :members:

Signals
```````

.. automodule:: dockerflow.flask.signals
   :members:
