"""Minimal JSON-RPC 2.0 helpers used by the MCP transport.

The MCP spec encodes every message as JSON-RPC 2.0.  We keep the helpers here
deliberately small so the transport layer stays readable.
"""

from __future__ import annotations

import json
from typing import Any

# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# MCP defines the range -32000..-32099 for implementation defined server errors.
RESOURCE_NOT_FOUND = -32002


class JsonRpcError(Exception):
    """An error that must be serialized as a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def dumps(message: Any) -> str:
    """Serialize without ASCII escaping so CJK text stays readable on the wire."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def is_request(message: Any) -> bool:
    """A JSON-RPC request has an id and a method."""
    return isinstance(message, dict) and "method" in message and "id" in message


def is_notification(message: Any) -> bool:
    """A JSON-RPC notification has a method but no id."""
    return isinstance(message, dict) and "method" in message and "id" not in message


def is_response(message: Any) -> bool:
    """A JSON-RPC response has an id and either result or error, but no method."""
    return (
        isinstance(message, dict)
        and "id" in message
        and "method" not in message
        and ("result" in message or "error" in message)
    )
