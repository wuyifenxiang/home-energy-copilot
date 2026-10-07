"""Alexa+ MCP add-on server.

A self-hosted Model Context Protocol server for the Alexa+ track of the
Amazon Developer Hackathon 2026.

Protocol revision: 2025-11-25
Transport: Streamable HTTP (POST + GET on a single endpoint)
"""

from .server import create_server, PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from .registry import ToolRegistry, ToolError

__all__ = [
    "create_server",
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "ToolRegistry",
    "ToolError",
]

__version__ = "0.1.0"
