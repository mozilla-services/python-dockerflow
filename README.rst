Python Dockerflow
=================

This package implements a few helpers and tools for Mozilla's
`Dockerflow pattern <https://github.com/mozilla-services/Dockerflow>`_.

.. image:: https://travis-ci.org/mozilla-services/python-dockerflow.svg?branch=master
   :alt: Build Status
   :target: https://travis-ci.org/mozilla-services/python-dockerflow

.. image:: https://codecov.io/github/mozilla-services/python-dockerflow/coverage.svg?branch=master
   :alt: Codecov
   :target: https://codecov.io/github/mozilla-services/python-dockerflow?branch=master

Installation
------------

Please install the package using your favorite package installer::

    pip install dockerflow

Configuration
-------------

This package implements various tools to implement the Dockerflow
requirements:

- Provide views for health monitoring:

  - ``/__version__`` - Serves a ``version.json`` file

  - ``/__heartbeat__`` - Run Django checks as configured
    in the ``DOCKERFLOW_CHECKS`` setting

  - ``/__lbheartbeat__`` - Retuns a HTTP 200 response


TODO
----

- Port mozilla-cloud-services-logger to ``dockerflow.logging`` and
  ``dockerflow.django.middleware``
  `mozilla-cloud-services-logger <https://github.com/mozilla/mozilla-cloud-services-logger>`_

- Document how to log to stdout and stderr

- Document how to use `Whitenoise <https://whitenoise.readthedocs.io/>`_ to
  serve static content

- Ship ``Dockerfile`` files for Python 2 and 3

- Document how to use ``python-decouple`` or ``django-configurations`` to read
  environment variables for configuration values


Changelog
---------

2016.11.0 (unreleased)
^^^^^^^^^^^^^^^^^^^^^^

- Added initial implementation for Django health checks based on Normandy
  and ATMO code. Many thanks to Mike Cooper for inspiration and majority of
  implementation.
