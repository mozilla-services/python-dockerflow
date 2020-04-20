Flask
=====

This documents the various Flask specific functionality but doesn't cover
internals of the extension.

Extension
---------

.. autoclass:: dockerflow.flask.app.Dockerflow
   :members:

.. autoclass:: dockerflow.flask.app.HeartbeatFailure
   :members:

.. _flask-checks:

Checks
------

.. autofunction:: dockerflow.flask.checks.check_database_connected

.. autofunction:: dockerflow.flask.checks.check_migrations_applied

.. autofunction:: dockerflow.flask.checks.check_redis_connected

Signals
-------

.. automodule:: dockerflow.flask.signals
   :members:
