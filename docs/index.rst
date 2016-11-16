.. include:: ../README.rst

Configuration
-------------

This package implements various tools to implement the Dockerflow
requirements:

- A Python logging formatter following the `mozlog`_ format.

- Tools to populate `request.summary`_.

.. _`mozlog`: https://github.com/mozilla-services/Dockerflow/blob/master/docs/mozlog.md
.. _`request.summary`: https://github.com/mozilla-services/Dockerflow/blob/master/docs/mozlog.md#application-request-summary-type-requestsummary

- Provides views for health monitoring:

  - ``/__version__`` - Serves a ``version.json`` file

  - ``/__heartbeat__`` - Run Django checks as configured
    in the ``DOCKERFLOW_CHECKS`` setting

  - ``/__lbheartbeat__`` - Retuns a HTTP 200 response

- Provides a generic way to fetch ``version.json`` files.

See the following framework/toolset specific configuration docs:

.. hlist::
   :columns: 4

   * :doc:`frameworks/django`

Contents:

.. toctree::
   :maxdepth: 2

   authors
   changelog
   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. toctree::
   :glob:
   :hidden:

   frameworks/*
