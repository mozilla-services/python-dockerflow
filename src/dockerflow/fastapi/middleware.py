from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict

from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    ASGISendEvent,
    HTTPScope,
)

from ..logging import JsonLogFormatter


class MozlogRequestSummaryLogger:
    def __init__(
        self,
        app: ASGI3Application,
        logger: logging.Logger | None = None,
    ) -> None:
        self.app = app
        if logger is None:
            self.logger = logging.getLogger("request.summary")
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)
            handler.setFormatter(JsonLogFormatter)
            self.logger.addHandler(handler)
        else:
            self.logger = logger

    async def __call__(
        self, scope: HTTPScope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        info = dict(request_headers={}, response={})

        async def inner_send(message: ASGISendEvent) -> None:
            if message["type"] == "http.response.start":
                info["response"] = message

            await send(message)

        try:
            info["start_time"] = time.time()
            await self.app(scope, receive, inner_send)
        except Exception as exc:
            info["response"]["status"] = 500
            raise exc
        finally:
            info["end_time"] = time.time()
            self._log(scope, info)

    def _log(self, scope: HTTPScope, info) -> None:
        self.logger.info("", extra=self._format(scope, info))

    def _format(self, scope: HTTPScope, info) -> Dict[str, Any]:
        for name, value in scope["headers"]:
            header_key = name.decode("latin1").lower()
            header_val = value.decode("latin1")
            info["request_headers"][header_key] = header_val

        request_duration_ms = (info["end_time"] - info["start_time"]) * 1000.0
        return {
            "agent": info["request_headers"].get("user-agent", ""),
            "path": scope["path"],
            "method": scope["method"],
            "code": info["response"]["status"],
            "lang": info["request_headers"].get("accept-language"),
            "t": int(request_duration_ms),
        }
