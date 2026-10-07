"""A dependency-free MCP client used for the end-to-end smoke test.

It speaks the Streamable HTTP transport the way a real client does: initialize,
read the Mcp-Session-Id header, send notifications/initialized, then call tools.
This is the same sequence the Alexa+ service performs, so passing this test is
the minimum bar for "it actually works".
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

ACCEPT = "application/json, text/event-stream"


class McpClientError(RuntimeError):
    pass


class McpHttpClient:
    def __init__(self, url: str, *, client_name: str = "alexa-mcp-smoke-test") -> None:
        self.url = url
        self.client_name = client_name
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._next_id = 1

    # -- transport --------------------------------------------------------

    def _post(self, message: dict[str, Any], *, expect_response: bool = True) -> Any:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", ACCEPT)
        if self.session_id:
            request.add_header("Mcp-Session-Id", self.session_id)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self._capture_session(response.headers)
                status = response.status
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise McpClientError(f"HTTP {exc.code} from {self.url}: {detail}") from exc

        if status == 202 or not raw:
            if expect_response:
                raise McpClientError(f"Expected a response, got HTTP {status} with an empty body.")
            return None

        if "text/event-stream" in content_type:
            return _parse_sse(raw.decode("utf-8"))
        return json.loads(raw.decode("utf-8"))

    def _capture_session(self, headers: Any) -> None:
        session = headers.get("Mcp-Session-Id")
        if session:
            self.session_id = session

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
        }
        self._next_id += 1
        if params is not None:
            message["params"] = params
        payload = self._post(message)
        if "error" in payload:
            raise McpClientError(f"{method} failed: {payload['error']}")
        return payload["result"]

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._post(message, expect_response=False)

    # -- MCP surface ------------------------------------------------------

    def initialize(self, protocol_version: str = "2025-11-25") -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {"roots": {"listChanged": False}},
                "clientInfo": {"name": self.client_name, "version": "1.0.0"},
            },
        )
        self.protocol_version = result.get("protocolVersion")
        if not self.session_id:
            raise McpClientError("Server did not return an Mcp-Session-Id header.")
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def health(self) -> dict[str, Any]:
        with urllib.request.urlopen(self.url.rsplit("/", 1)[0] + "/healthz", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))


def _parse_sse(text: str) -> Any:
    """Return the JSON payload of the last ``data:`` line in an SSE body."""
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    for candidate in reversed(data_lines):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise McpClientError(f"No JSON payload found in SSE response: {text!r}")
