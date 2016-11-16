# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import json
import logging
import os

import jsonschema

from dockerflow.logging import JsonLogFormatter

logger_name = 'TestingTestPilot'
formatter = JsonLogFormatter(logger_name=logger_name)


def assert_records(records):
    assert len(records) == 1
    details = json.loads(formatter.format(records[0]))
    jsonschema.validate(details, JSON_LOGGING_SCHEMA)
    return details


def test_basic_operation(caplog):
    """Ensure log formatter contains all the expected fields and values"""
    message_text = 'simple test'
    logging.debug(message_text)
    details = assert_records(caplog.records)

    assert 'Timestamp' in details
    assert 'Hostname' in details
    assert details['Severity'] == 7
    assert details['Type'] == 'root'
    assert details['Pid'] == os.getpid()
    assert details['Logger'] == logger_name
    assert details['EnvVersion'] == formatter.LOGGING_FORMAT_VERSION
    assert details['Fields']['message'] == message_text


def test_custom_paramters(caplog):
    """Ensure log formatter can handle custom parameters"""
    logger = logging.getLogger('dockerflow.test.test_logging')
    logger.warning('custom test %s', 'one', extra={'more': 'stuff'})
    details = assert_records(caplog.records)

    assert details['Type'] == 'dockerflow.test.test_logging'
    assert details['Severity'] == 4
    assert details['Fields']['message'] == 'custom test one'
    assert details['Fields']['more'] == 'stuff'


def test_logging_error_tracebacks(caplog):
    """Ensure log formatter includes exception traceback information"""
    try:
        raise ValueError('\n')
    except Exception:
        logging.exception('there was an error')
    details = assert_records(caplog.records)

    assert details['Severity'] == 3
    assert details['Fields']['message'] == 'there was an error'
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
    assert 'message' not in details['Fields']


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
