"""Streamable HTTP transport + MCP lifecycle for the Alexa+ add-on server.

Design constraints taken directly from the MCP specification revision
2025-11-25 (``/specification/2025-11-25/basic/transports`` and
``/specification/2025-11-25/basic/lifecycle``):

* One HTTP endpoint path serves both POST and GET.
* POST bodies are a single JSON-RPC request, notification, or response.
  * A notification or response that we accept is answered ``202 Accepted``
    with an empty body.
  * A request is answered either ``application/json`` (one object) or
    ``text/event-stream``.
* Clients MUST send ``Accept: application/json, text/event-stream``; we reject
  anything that cannot accept both, so a misconfigured client fails loudly.
* The ``Origin`` header MUST be validated; an invalid Origin MUST receive
  ``403 Forbidden`` to block DNS-rebinding attacks.
* The server binds to ``127.0.0.1`` by default rather than ``0.0.0.0``.
* Sessions are created during ``initialize`` and carried in the
  ``Mcp-Session-Id`` header.  Requests for an expired session get ``404`` so the
  client knows to re-initialize.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from . import jsonrpc
from .registry import ToolError, ToolRegistry

PROTOCOL_VERSION = "2025-11-25"

# Newest first.  The server answers with its own preferred revision; a client
# that asked for something else can decide whether it wants to continue.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_ENDPOINT_PATH = "/mcp"

SESSION_TTL_SECONDS = 30 * 60
SSE_KEEPALIVE_SECONDS = 15.0

LOGGER = logging.getLogger("alexa_mcp")


class Session:
    """State negotiated during ``initialize`` for one client connection."""

    def __init__(self, session_id: str, protocol_version: str) -> None:
        self.id = session_id
        self.protocol_version = protocol_version
        self.client_info: dict[str, Any] = {}
        self.client_capabilities: dict[str, Any] = {}
        self.created_at = time.monotonic()
        self.last_seen = self.created_at
        self.initialized = False

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.last_seen) > SESSION_TTL_SECONDS


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, protocol_version: str) -> Session:
        session = Session(secrets.token_urlsafe(24), protocol_version)
        with self._lock:
            self._purge_locked()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._purge_locked()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def count(self) -> int:
        with self._lock:
            self._purge_locked()
            return len(self._sessions)

    def _purge_locked(self) -> None:
        for key in [key for key, value in self._sessions.items() if value.expired]:
            del self._sessions[key]


class McpApplication:
    """Protocol logic independent of HTTP so it can be unit tested directly."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        name: str = "alexa-plus-addon",
        title: str = "Alexa+ Add-on MCP Server",
        version: str = "0.1.0",
        instructions: str | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = SessionStore()
        self.server_info = {
            "name": name,
            "title": title,
            "version": version,
        }
        self.instructions = instructions
        self._started_at = time.time()

    # -- capabilities -----------------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        return {
            "tools": {"listChanged": False},
            "logging": {},
        }

    # -- dispatch ---------------------------------------------------------

    def handle_message(
        self,
        message: Any,
        session: Session | None,
    ) -> tuple[Session | None, dict[str, Any] | None]:
        """Handle one decoded JSON-RPC message.

        Returns ``(session, response)``.  ``response`` is ``None`` when the
        message was a notification and therefore must not be answered.
        """

        if not isinstance(message, dict):
            return session, jsonrpc.error_response(
                None, jsonrpc.INVALID_REQUEST, "Message must be a JSON object."
            )

        if jsonrpc.is_response(message):
            # A response to a server-initiated request.  We accept and ignore it.
            LOGGER.debug("Ignoring client response: %s", message.get("id"))
            return session, None

        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if not isinstance(method, str):
            return session, jsonrpc.error_response(
                request_id, jsonrpc.INVALID_REQUEST, "Missing or invalid 'method'."
            )

        if not isinstance(params, dict):
            return session, jsonrpc.error_response(
                request_id,
                jsonrpc.INVALID_PARAMS,
                "'params' must be an object when present.",
            )

        try:
            result, session = self._dispatch(method, params, session)
        except jsonrpc.JsonRpcError as exc:
            if jsonrpc.is_notification(message):
                LOGGER.warning("Notification %s failed: %s", method, exc.message)
                return session, None
            return session, jsonrpc.error_response(
                request_id, exc.code, exc.message, exc.data
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.exception("Unhandled error in %s", method)
            if jsonrpc.is_notification(message):
                return session, None
            return session, jsonrpc.error_response(
                request_id, jsonrpc.INTERNAL_ERROR, "Internal server error."
            )

        if jsonrpc.is_notification(message):
            return session, None
        return session, jsonrpc.success_response(request_id, result)

    def _dispatch(
        self,
        method: str,
        params: dict[str, Any],
        session: Session | None,
    ) -> tuple[Any, Session | None]:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}, session
        if method == "notifications/initialized":
            if session is not None:
                session.initialized = True
            return {}, session
        if method == "notifications/cancelled":
            return {}, session

        if method.startswith("notifications/"):
            LOGGER.debug("Ignoring notification: %s", method)
            return {}, session

        if session is None:
            raise jsonrpc.JsonRpcError(
                jsonrpc.INVALID_REQUEST,
                "Missing MCP session. Send 'initialize' first and reuse the "
                "Mcp-Session-Id header.",
            )

        if method == "tools/list":
            return {"tools": self.registry.listing()}, session
        if method == "tools/call":
            return self._call_tool(params), session
        if method == "resources/list":
            return {"resources": []}, session
        if method == "prompts/list":
            return {"prompts": []}, session
        if method == "logging/setLevel":
            return {}, session

        raise jsonrpc.JsonRpcError(
            jsonrpc.METHOD_NOT_FOUND, f"Method not found: {method}"
        )

    def _initialize(self, params: dict[str, Any]) -> tuple[dict[str, Any], Session]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise jsonrpc.JsonRpcError(
                jsonrpc.INVALID_PARAMS, "'protocolVersion' is required."
            )

        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION

        session = self.sessions.create(negotiated)
        client_info = params.get("clientInfo")
        if isinstance(client_info, dict):
            session.client_info = client_info
        client_capabilities = params.get("capabilities")
        if isinstance(client_capabilities, dict):
            session.client_capabilities = client_capabilities

        LOGGER.info(
            "initialize: client=%s requested=%s negotiated=%s",
            session.client_info.get("name", "unknown"),
            requested,
            negotiated,
        )

        result: dict[str, Any] = {
            "protocolVersion": negotiated,
            "capabilities": self.capabilities(),
            "serverInfo": dict(self.server_info),
        }
        if self.instructions:
            result["instructions"] = self.instructions
        return result, session

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise jsonrpc.JsonRpcError(
                jsonrpc.INVALID_PARAMS, "'name' is required for tools/call."
            )
        arguments = params.get("arguments")

        try:
            output = self.registry.call(name, arguments)
        except ToolError as exc:
            # Model-visible failure: the assistant can read this and retry.
            payload: dict[str, Any] = {"message": str(exc)}
            if exc.args[1:]:
                payload["details"] = exc.args[1]
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"{name} could not run: {exc}\n"
                        "Ask the customer for the missing or corrected detail, "
                        "then try again.",
                    }
                ],
                "structuredContent": payload,
                "isError": True,
            }

        return _tool_result(output)


def _tool_result(output: Any) -> dict[str, Any]:
    """Normalize a tool return value into a ``CallToolResult``.

    A handler may return:
      * a plain string -- becomes the spoken/displayed text,
      * a dict with ``speech``/``display``/``data`` -- the conversational shape,
      * any JSON value -- serialized into the text content.
    """
    if isinstance(output, str):
        return {"content": [{"type": "text", "text": output}]}

    if isinstance(output, dict) and ("speech" in output or "display" in output):
        speech = str(output.get("speech") or output.get("display") or "")
        display = str(output.get("display") or speech)
        data = output.get("data")
        content: list[dict[str, Any]] = [{"type": "text", "text": display}]
        if display != speech:
            content.append({"type": "text", "text": speech})
        result: dict[str, Any] = {"content": content}
        if isinstance(data, dict):
            result["structuredContent"] = data
        return result

    return {
        "content": [
            {"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=2)}
        ]
    }


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class McpHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AlexaPlusAddon/0.1"
    app: McpApplication
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    allowed_origins: tuple[str, ...] = ()

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        LOGGER.debug("%s - %s", self.address_string(), fmt % args)

    def _send(
        self,
        status: int,
        body: bytes = b"",
        content_type: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> None:
        body = jsonrpc.dumps(payload).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra_headers)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            # Non-browser clients (the Alexa+ service, curl, MCP inspectors) do
            # not send Origin.  DNS rebinding is a browser attack, so absent
            # Origin is acceptable; a present but unexpected Origin is not.
            return True
        if origin in self.allowed_origins:
            return True
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1"}

    def _reject_origin(self) -> None:
        LOGGER.warning("Rejected Origin header: %s", self.headers.get("Origin"))
        self._send_json(
            403,
            jsonrpc.error_response(
                None,
                jsonrpc.INVALID_REQUEST,
                "Origin header is not allowed by this MCP server.",
            ),
        )

    def _accepts_both(self) -> bool:
        accept = (self.headers.get("Accept") or "").lower()
        return "application/json" in accept and "text/event-stream" in accept

    def _session(self) -> tuple[Session | None, str | None]:
        header = self.headers.get("Mcp-Session-Id")
        if not header:
            return None, None
        session = self.app.sessions.get(header)
        if session is None:
            self._send_json(
                404,
                jsonrpc.error_response(
                    None,
                    jsonrpc.INVALID_REQUEST,
                    "Session not found or expired. Re-run initialize to start a "
                    "new session.",
                ),
            )
            return None, header
        return session, header

    # -- verbs ------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != self.endpoint_path:
            self._send(404, b"Not Found", "text/plain; charset=utf-8")
            return

        if not self._origin_allowed():
            self._reject_origin()
            return

        if not self._accepts_both():
            self._send_json(
                406,
                jsonrpc.error_response(
                    None,
                    jsonrpc.INVALID_REQUEST,
                    "Accept header must list both application/json and "
                    "text/event-stream.",
                ),
            )
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0

        raw = self.rfile.read(length) if length else b""
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(
                400,
                jsonrpc.error_response(
                    None, jsonrpc.PARSE_ERROR, f"Invalid JSON: {exc}"
                ),
            )
            return

        session: Session | None = None
        is_initialize = isinstance(message, dict) and message.get("method") == "initialize"
        if not is_initialize:
            session, _ = self._session()
            if session is None and self.headers.get("Mcp-Session-Id"):
                return  # _session already answered with 404
            if session is None and jsonrpc.is_request(message):
                # A request that is not 'initialize' cannot be served without a
                # session.  Answer at the HTTP layer so the client does not have
                # to parse a body to discover that.
                self._send_json(
                    400,
                    jsonrpc.error_response(
                        message.get("id"),
                        jsonrpc.INVALID_REQUEST,
                        "Missing MCP session. Send 'initialize' first and reuse "
                        "the Mcp-Session-Id header.",
                    ),
                )
                return

        session, response = self.app.handle_message(message, session)

        extra_headers: dict[str, str] = {}
        if is_initialize and session is not None:
            extra_headers["Mcp-Session-Id"] = session.id

        if response is None:
            self._send(202, b"", None, extra_headers)
            return

        # A notification or response never produces a body; only requests do.
        status = 200 if jsonrpc.is_request(message) else 202
        accept = (self.headers.get("Accept") or "").lower()
        wants_sse = "text/event-stream" in accept and "application/json" not in accept
        if wants_sse and status == 200:
            self._stream_single_response(response, extra_headers)
        else:
            self._send_json(status, response, extra_headers)

    def _stream_single_response(
        self,
        response: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Answer one request over a short SSE stream, then close it."""
        event_id = uuid.uuid4().hex
        headers = {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        headers.update(extra_headers or {})
        self.send_response(200)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

        # Prime the client with an id-bearing empty event so it can resume.
        self._write_sse({"event": "message", "id": event_id, "data": ""})
        self._write_sse({"event": "message", "data": jsonrpc.dumps(response)})

    def _write_sse(self, payload: dict[str, str]) -> None:
        chunk = ""
        if "event" in payload:
            chunk += f"event: {payload['event']}\n"
        if "id" in payload:
            chunk += f"id: {payload['id']}\n"
        for line in (payload.get("data") or "").split("\n"):
            chunk += f"data: {line}\n"
        chunk += "\n"
        self.wfile.write(chunk.encode("utf-8"))
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path != self.endpoint_path:
            if urlparse(self.path).path == "/healthz":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "protocolVersion": PROTOCOL_VERSION,
                        "tools": self.app.registry.names(),
                        "sessions": self.app.sessions.count(),
                    },
                )
                return
            self._send(404, b"Not Found", "text/plain; charset=utf-8")
            return

        if not self._origin_allowed():
            self._reject_origin()
            return

        if not self._accepts_both():
            self._send_json(
                406,
                jsonrpc.error_response(
                    None,
                    jsonrpc.INVALID_REQUEST,
                    "Accept header must list both application/json and "
                    "text/event-stream.",
                ),
            )
            return

        session, _ = self._session()
        if session is None:
            if not self.headers.get("Mcp-Session-Id"):
                self._send_json(
                    400,
                    jsonrpc.error_response(
                        None,
                        jsonrpc.INVALID_REQUEST,
                        "GET requires an Mcp-Session-Id header.",
                    ),
                )
            return

        # A standalone SSE stream used for server-initiated notifications and
        # for client polling.  We keep it open with periodic keep-alives.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self._write_sse({"event": "message", "id": uuid.uuid4().hex, "data": ""})
            while True:
                time.sleep(SSE_KEEPALIVE_SECONDS)
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                session.touch()
        except (BrokenPipeError, ConnectionResetError, OSError):
            LOGGER.debug("SSE stream closed by client")

    def do_DELETE(self) -> None:  # noqa: N802
        if urlparse(self.path).path != self.endpoint_path:
            self._send(404, b"Not Found", "text/plain; charset=utf-8")
            return
        if not self._origin_allowed():
            self._reject_origin()
            return
        session_id = self.headers.get("Mcp-Session-Id")
        if not session_id:
            self._send_json(
                400,
                jsonrpc.error_response(
                    None, jsonrpc.INVALID_REQUEST, "Mcp-Session-Id header is required."
                ),
            )
            return
        if self.app.sessions.drop(session_id):
            self._send(204)
        else:
            self._send(404, b"Session not found", "text/plain; charset=utf-8")


def create_server(
    registry: ToolRegistry,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    endpoint_path: str = DEFAULT_ENDPOINT_PATH,
    allowed_origins: tuple[str, ...] = (),
    name: str = "alexa-plus-addon",
    title: str = "Alexa+ Add-on MCP Server",
    version: str = "0.1.0",
    instructions: str | None = None,
    log_level: int = logging.INFO,
) -> tuple[ThreadingHTTPServer, McpApplication]:
    """Build (but do not start) the MCP HTTP server."""

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    app = McpApplication(
        registry,
        name=name,
        title=title,
        version=version,
        instructions=instructions,
    )

    handler = type(
        "BoundMcpHttpHandler",
        (McpHttpHandler,),
        {
            "app": app,
            "endpoint_path": endpoint_path,
            "allowed_origins": tuple(allowed_origins),
        },
    )

    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd, app
