Development
===========


Setup
-----

**Requirements**

- `tox <https://tox.wiki>`_
- `Redis <https://redis.io/>`_


Run tests
---------

Run a local Redis:

::

    docker run redis -p 6379:6379

Run the test suite:

::

    tox -v

For a specific framework or version (see ``tox.ini`` for available environments):

::

    tox -e py311-fl22

Pass arguments to ``pytest`` using the ``--`` delimiter:

::

    tox -e py311-fl22 -- -x tests/flask/test_flask.py


Release
-------

1. Update the changelog in ``docs/changelog.rst``
2. Tag using `Calver <https://calver.org/>`_
3. Push tag to Github
4. Create release entry in repository

A Github Action will be triggered and publish the package to Pypi.
