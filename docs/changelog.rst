Changelog
---------

2017.1.1 (2017-01-25)
^^^^^^^^^^^^^^^^^^^^^

- Fixed PyPI deploy via Travis (added whl files).

2017.1.0 (2017-01-25)
^^^^^^^^^^^^^^^^^^^^^

- Replaced custom URL patterns in the Django support with new
  DockerflowMiddleware that also takes care of the "request.summary"
  logging.

- Added Python 3.6 to test harness.

- Fixed Flake8 tests.

2016.11.0 (2016-11-18)
^^^^^^^^^^^^^^^^^^^^^^

- Added initial implementation for Django health checks based on Normandy
  and ATMO code. Many thanks to Mike Cooper for inspiration and majority of
  implementation.

- Added logging formatter and request.summary populating middleware,
  from the mozilla-cloud-services-logger project that was originally
  written by Les Orchard. Many thanks for the permission to re-use that
  code.

- Added documentation:

    https://python-dockerflow.readthedocs.io/

- Added Travis continous testing:

    https://travis-ci.org/mozilla-serviers/python-dockerflow
