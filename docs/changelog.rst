Changelog
---------

Unreleased
^^^^^^^^^^

- Drop support for Python 2.7!

- Drop support for Django 1.11, 2.0 and 2.1!

- Move to GitHub Actions: https://github.com/mozilla-services/python-dockerflow/actions

2020.10.0 (2020-10-05)
^^^^^^^^^^^^^^^^^^^^^^

- Add support for Sanic 20.3.0 and up

- Add public ``flask.g.request_id`` when not set

2020.6.0 (2020-06-09)
^^^^^^^^^^^^^^^^^^^^^

- Set heartbeat fail level to checks.ERROR

2019.10.0 (2019-10-28)
^^^^^^^^^^^^^^^^^^^^^^

- Add Python 3.8 support.

- Fix a regression in the JSON logger parameter signature introduced in
  version 2018.2.1.

- Fixed some test harness issues, e.g. broken version contraint on the
  Django 2.2 tests.

- Speed up tests by only installing framework dependencies when needed.

2019.9.0 (2019-09-26)
^^^^^^^^^^^^^^^^^^^^^

- Make JsonLogFormatter easier to extend

- Blacken and isorted source code.

2019.6.0 (2019-06-25)
^^^^^^^^^^^^^^^^^^^^^

- Add support for Sanic 19.

- Add support for Python 3.7 and Django 2.1 and 2.2.

- Drop support for Python 3.4 and 3.5 and Django 1.8, 1.9, 1.10 and 2.0.

- Match Django urlpatterns with trailing slash.

- Use black for code formatting.

2019.5.0 (2019-05-13)
^^^^^^^^^^^^^^^^^^^^^

- Gracefully handle user loading to prevent accidental race condtions during
  exception handling when using the Flask Dockerflow extension.

2018.4.0 (2018-04-03)
^^^^^^^^^^^^^^^^^^^^^

- Fix backward-compatibility in the ``check_migrations_applied`` Flask check
  when an older version of Flask-Migrate is used.

2018.2.1 (2018-02-24)
^^^^^^^^^^^^^^^^^^^^^

- Fixes the instantiation of the JsonLogFormatter logging formatter
  on Python 3 when using the logging module's ability to be configured
  with ConfigParser ini files.

- Extend the documentation for custom checks and reorganized it a bit.

2018.2.0 (2018-02-20)
^^^^^^^^^^^^^^^^^^^^^

- Adds Flask support. See the documentation for more information.

- Extends the documentation about defining custom health checks.

- Refactored some of the health monitoring code that existed for
  the Django support.

- Fixed an embarrassing typo about the default logger name when
  using the ``JsonLogFormatter`` logging formatter, changed it
  ``TestPilot`` to ``Dockerflow``.

- Extends the testing matrix to include Django 2.0.

- Make sure the the combination of Python and Django versions
  match the official recommendation as defined at
  https://docs.djangoproject.com/en/2.0/faq/install/#what-python-version-can-i-use-with-django.

2017.11.0 (2017-11-16)
^^^^^^^^^^^^^^^^^^^^^^

- Fixed name of mozlog message field from "message" to "msg" as
  specified in https://wiki.mozilla.org/Firefox/Services/Logging.
  Thanks @leplatrem!

2017.5.0 (2017-05-31)
^^^^^^^^^^^^^^^^^^^^^

- Improve logging documentation, thanks @willkg.

- Speed up timestamp calculation, thanks @peterbe.

- Make user id calculation compatible with
  Django >= 1.10.

2017.4.0 (2017-04-09)
^^^^^^^^^^^^^^^^^^^^^

- Ensure log formatter doesn't fail with non json-serializable parameters. Thanks @diox!

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
