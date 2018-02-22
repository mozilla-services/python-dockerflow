# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import logging
import logging.config
import os
import textwrap

import jsonschema

from dockerflow.logging import JsonLogFormatter

logger_name = 'tests'
formatter = JsonLogFormatter(logger_name=logger_name)


def assert_records(records):
    assert len(records) == 1
    details = json.loads(formatter.format(records[0]))
    jsonschema.validate(details, JSON_LOGGING_SCHEMA)
    return details


def test_initialization_from_ini(caplog, tmpdir):
    ini_content = textwrap.dedent("""
    [loggers]
    keys = root

    [handlers]
    keys = console

    [formatters]
    keys = json

    [logger_root]
    level = INFO
    handlers = console

    [handler_console]
    class = StreamHandler
    level = DEBUG
    args = (sys.stderr,)
    formatter = json

    [formatter_json]
    class = dockerflow.logging.JsonLogFormatter
    """)
    ini_file = tmpdir.join('logging.ini')
    ini_file.write(ini_content)
    logging.config.fileConfig(str(ini_file))
    logging.info('I am logging in mozlog format now! woo hoo!')
    logger = logging.getLogger()
    assert len(logger.handlers) > 0
    assert logger.handlers[0].formatter.logger_name == 'Dockerflow'


def test_basic_operation(caplog):
    """Ensure log formatter contains all the expected fields and values"""
    message_text = 'simple test'
    caplog.set_level(logging.DEBUG)
    logging.debug(message_text)
    details = assert_records(caplog.records)

    assert 'Timestamp' in details
    assert 'Hostname' in details
    assert details['Severity'] == 7
    assert details['Type'] == 'root'
    assert details['Pid'] == os.getpid()
    assert details['Logger'] == logger_name
    assert details['EnvVersion'] == formatter.LOGGING_FORMAT_VERSION
    assert details['Fields']['msg'] == message_text


def test_custom_paramters(caplog):
    """Ensure log formatter can handle custom parameters"""
    logger = logging.getLogger('tests.test_logging')
    logger.warning('custom test %s', 'one', extra={'more': 'stuff'})
    details = assert_records(caplog.records)

    assert details['Type'] == 'tests.test_logging'
    assert details['Severity'] == 4
    assert details['Fields']['msg'] == 'custom test one'
    assert details['Fields']['more'] == 'stuff'


def test_non_json_serializable_parameters_are_converted(caplog):
    """Ensure log formatter doesn't fail with non json-serializable params."""
    foo = object()
    foo_repr = repr(foo)
    logger = logging.getLogger('tests.test_logging')
    logger.warning('custom test %s', 'hello', extra={'foo': foo})
    details = assert_records(caplog.records)

    assert details['Type'] == 'tests.test_logging'
    assert details['Severity'] == 4
    assert details['Fields']['msg'] == 'custom test hello'
    assert details['Fields']['foo'] == foo_repr


def test_logging_error_tracebacks(caplog):
    """Ensure log formatter includes exception traceback information"""
    try:
        raise ValueError('\n')
    except Exception:
        logging.exception('there was an error')
    details = assert_records(caplog.records)

    assert details['Severity'] == 3
    assert details['Fields']['msg'] == 'there was an error'
    assert details['Fields']['error'] == "ValueError('\\n',)"
    assert details['Fields']['traceback'].startswith('Uncaught exception:')
    assert 'ValueError' in details['Fields']['traceback']


def test_ignore_json_message(caplog):
    """Ensure log formatter ignores messages that are JSON already"""
    try:
        raise ValueError('\n')
    except Exception:
        logging.exception(json.dumps({'spam': 'eggs'}))
    details = assert_records(caplog.records)
    assert 'msg' not in details['Fields']


# https://mana.mozilla.org/wiki/pages/viewpage.action?pageId=42895640
JSON_LOGGING_SCHEMA = json.loads("""
{
    "type":"object",
    "required":["Timestamp"],
    "properties":{
        "Timestamp":{
            "type":"integer",
            "minimum":0
        },
        "Type":{
            "type":"string"
        },
        "Logger":{
            "type":"string"
        },
        "Hostname":{
            "type":"string",
            "format":"hostname"
        },
        "EnvVersion":{
            "type":"string",
            "pattern":"^\\d+(?:\\.\\d+){0,2}$"
        },
        "Severity":{
            "type":"integer",
            "minimum":0,
            "maximum":7
        },
        "Pid":{
            "type":"integer",
            "minimum":0
        },
        "Fields":{
            "type":"object",
            "minProperties":1,
            "additionalProperties":{
                "anyOf": [
                    { "$ref": "#/definitions/field_value"},
                    { "$ref": "#/definitions/field_array"},
                    { "$ref": "#/definitions/field_object"}
                ]
            }
        }
    },
    "definitions":{
        "field_value":{
            "type":["string", "number", "boolean"]
        },
        "field_array":{
            "type":"array",
            "minItems": 1,
            "oneOf": [
                    {"items": {"type":"string"}},
                    {"items": {"type":"number"}},
                    {"items": {"type":"boolean"}}
            ]
        },
        "field_object":{
            "type":"object",
            "required":["value"],
            "properties":{
                "value":{
                    "oneOf": [
                        { "$ref": "#/definitions/field_value" },
                        { "$ref": "#/definitions/field_array" }
                    ]
                },
                "representation":{"type":"string"}
            }
        }
    }
}
""".replace("\\", "\\\\"))  # HACK: Fix escaping for easy copy/paste
