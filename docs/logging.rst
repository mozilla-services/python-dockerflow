.. _logging:

Logging
=======

python-dockerflow provides a :py:class:`dockerflow.logging.JsonLogFormatter` Python
logging formatter that produces messages following the JSON schema for a common
application logging format defined by the illustrious Mozilla Cloud Services
group.


Configuration
-------------

Example configuration::

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
            'myservice': {
                'handlers': ['console'],
                'level': 'DEBUG',
            },
        }
    }

    logging.config.dictConfig(cfg)

    logging.info('I am logging in mozlog format now! woo hoo!')


In this example, we set up a logger for ``myproject`` (you'd replace that with
your service name) which has a single handler named ``console`` which uses the
``mozlog`` formatter to output log event data to stdout.

API
---

.. autoclass:: dockerflow.logging.JsonLogFormatter
