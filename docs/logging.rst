.. _logging:

Logging
=======

python-dockerflow provides a :class:`~dockerflow.logging.JsonLogFormatter`
Python logging formatter that produces messages following the JSON schema
for a common application logging format defined by the illustrious
Mozilla Cloud Services group.

.. seealso::

    For more information see the :doc:`API documentation <api/logging>` for the
    ``dockerflow.logging`` module.

Configuration
-------------

There a different ways to configure Python logging, please refer to the
:mod:`logging` documentation to learn more.

The following examples should be considered excerpts and won't be enough
for your application to work. They only illustrate how to use the
JSON logging formatter for a specific logger.

Dictionary based
````````````````

A simple example configuration for a ``myproject`` logger could look like
this::

    import logging.config

    cfg = {
        'version': 1,
        'formatters': {
            'json': {
                '()': 'dockerflow.logging.JsonLogFormatter',
                'logger_name': 'myproject'
            }
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'json'
            },
        },
        'loggers': {
            'myproject': {
                'handlers': ['console'],
                'level': 'DEBUG',
            },
        }
    }

    logging.config.dictConfig(cfg)
    logger = logging.getLogger('myproject')
    logger.info('I am logging in mozlog format now! woo hoo!')

In this example, we set up a logger for ``myproject`` (you'd replace that with
your project name) which has a single handler named ``console`` which uses the
``mozlog`` formatter to output log event data to stdout.

ConfigParser ini file based
```````````````````````````

Consider an ``ini`` file with the following content that does the same
thing as the dictionary based configuratio above:

.. code-block:: ini
   :caption: logging.ini

    [loggers]
    keys = root, myproject

    [handlers]
    keys = console

    [formatters]
    keys = json

    [logger_root]
    level = INFO
    handlers = console

    [logger_myproject]
    level = DEBUG
    handlers = console
    qualname = myproject

    [handler_console]
    class = StreamHandler
    level = DEBUG
    args = (sys.stdout,)
    formatter = json

    [formatter_json]
    class = dockerflow.logging.JsonLogFormatter

Then load the ini file using the :mod:`logging` module function
:func:`logging.config.fileConfig`:

.. code-block:: python
   :caption: myproject.py

    logging.config.fileConfig('logging.ini')
    logger = logging.getLogger('myproject')
    logger.info('I am logging in mozlog format now! woo hoo!')
