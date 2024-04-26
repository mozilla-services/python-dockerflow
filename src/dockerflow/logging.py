# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from __future__ import absolute_import

import json
import logging
import socket
import sys
import traceback
import uuid
import warnings
from contextvars import ContextVar
from typing import ClassVar, Optional


class MozlogHandler(logging.StreamHandler):
    def __init__(self, stream=None, name="Dockerflow"):
        if stream is None:
            stream = sys.stdout
        super().__init__(stream=stream)
        self.logger_name = name
        self.setFormatter(MozlogFormatter())

    def emit(self, record):
        record.logger_name = self.logger_name
        super().emit(record)


class SafeJSONEncoder(json.JSONEncoder):
    def default(self, o):
        return repr(o)


class MozlogFormatter(logging.Formatter):
    """Log formatter that outputs json structured according to the Mozlog schema.

    This log formatter outputs JSON format messages that are compatible with
    Mozilla's standard heka-based log aggregation infrastructure.

    .. seealso::

        - https://wiki.mozilla.org/Firefox/Services/Logging

    Adapted from:
    https://github.com/mozilla-services/mozservices/blob/master/mozsvc/util.py#L106
    """

    LOGGING_FORMAT_VERSION = "2.0"

    # Map from Python logging to Syslog severity levels
    SYSLOG_LEVEL_MAP: ClassVar = {
        50: 2,  # CRITICAL
        40: 3,  # ERROR
        30: 4,  # WARNING
        20: 6,  # INFO
        10: 7,  # DEBUG
    }

    # Syslog level to use when/if python level isn't found in map
    DEFAULT_SYSLOG_LEVEL = 7

    EXCLUDED_LOGRECORD_ATTRS: ClassVar = set(
        (
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "logger_name",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        )
    )

    def __init__(self, fmt=None, datefmt=None, style="%", logger_name="Dockerflow"):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.logger_name = logger_name
        self.hostname = socket.gethostname()

    def is_value_jsonlike(self, value):
        """
        Return True if the value looks like JSON. Use only on strings.
        """
        return value.startswith("{") and value.endswith("}")

    def convert_record(self, record):
        """
        Convert a Python LogRecord attribute into a dict that follows MozLog
        application logging standard.

        * from - https://docs.python.org/3/library/logging.html#logrecord-attributes
        * to - https://wiki.mozilla.org/Firefox/Services/Logging
        """
        out = {
            "Timestamp": int(record.created * 1e9),
            "Type": record.name,
            "Logger": getattr(record, "logger_name", self.logger_name),
            "Hostname": self.hostname,
            "EnvVersion": self.LOGGING_FORMAT_VERSION,
            "Severity": self.SYSLOG_LEVEL_MAP.get(
                record.levelno, self.DEFAULT_SYSLOG_LEVEL
            ),
            "Pid": record.process,
        }

        # Include any custom attributes set on the record.
        # These would usually be collected metrics data.
        fields = {}
        for key, value in record.__dict__.items():
            if key not in self.EXCLUDED_LOGRECORD_ATTRS:
                fields[key] = value

        # Only include the 'msg' key if it has useful content
        # and is not already a JSON blob.
        message = record.getMessage()
        if message and not self.is_value_jsonlike(message):
            fields["msg"] = message

        # If there is an error, format it for nice output.
        if record.exc_info:
            fields["error"] = repr(record.exc_info[1])
            fields["traceback"] = safer_format_traceback(*record.exc_info)

        out["Fields"] = fields
        return out

    def format(self, record):
        """
        Format a Python LogRecord into a JSON string following MozLog
        application logging standard.
        """
        out = self.convert_record(record)
        return json.dumps(out, cls=SafeJSONEncoder)


class JsonLogFormatter(MozlogFormatter):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "JsonLogFormatter has been deprecated. Use MozlogFormatter instead",
            DeprecationWarning,
        )
        super().__init__(*args, **kwargs)


def safer_format_traceback(exc_typ, exc_val, exc_tb):
    """Format an exception traceback into safer string.
    We don't want to let users write arbitrary data into our logfiles,
    which could happen if they e.g. managed to trigger a ValueError with
    a carefully-crafted payload.  This function formats the traceback
    using "%r" for the actual exception data, which passes it through repr()
    so that any special chars are safely escaped.
    """
    lines = ["Uncaught exception:\n"]
    lines.extend(traceback.format_tb(exc_tb))
    lines.append("%r\n" % (exc_typ,))
    lines.append("%r\n" % (exc_val,))
    return "".join(lines)


request_id_context: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_or_generate_request_id(headers: dict, header_name: Optional[str] = None) -> str:
    """
    Read the request ID from the headers, and generate one if missing.
    """
    header_name = header_name or "x-request-id"
    rid = headers.get(header_name, "")
    if not rid:
        rid = str(uuid.uuid4())
    return rid


class RequestIdLogFilter(logging.Filter):
    """Logging filter to attach request IDs to log records"""

    def filter(self, record: "logging.LogRecord") -> bool:
        """
        Attach the request ID to the log record.
        """
        record.rid = request_id_context.get(None)
        return True
