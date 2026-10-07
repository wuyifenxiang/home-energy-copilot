"""Tool registry.

Alexa+ tools are model-controlled: the assistant discovers them through
``tools/list`` and invokes them through ``tools/call``.  A tool therefore has to
carry two contracts at once:

1.  A machine contract -- ``inputSchema`` (JSON Schema 2020-12) and an optional
    ``outputSchema``.
2.  A conversation contract -- wording that stays short, pronounceable, and
    unambiguous when it is spoken back to a person.

Both live on the same :class:`Tool` object so they cannot drift apart.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping


class ToolError(Exception):
    """A recoverable, model-visible failure.

    MCP distinguishes protocol errors from tool execution errors.  Invalid tool
    input MUST come back as a tool execution error (``isError: true`` inside a
    successful JSON-RPC result) so the model can read the message and correct
    itself.  Raising this class produces exactly that.
    """


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    title: str | None = None
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_listing(self) -> dict[str, Any]:
        """The wire representation used by ``tools/list``."""
        listing: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.title:
            listing["title"] = self.title
        if self.output_schema:
            listing["outputSchema"] = self.output_schema
        if self.annotations:
            listing["annotations"] = self.annotations
        return listing


class ToolRegistry:
    """Holds the tools this server exposes and validates their arguments."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterable[Tool]:
        return iter(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools)

    def tool(
        self,
        name: str,
        *,
        description: str,
        input_schema: dict[str, Any] | None = None,
        title: str | None = None,
        output_schema: dict[str, Any] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator that registers a function as an MCP tool."""

        if not _is_valid_tool_name(name):
            raise ValueError(
                f"tool name {name!r} must be 1-128 characters of [A-Za-z0-9_.-]"
            )

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ValueError(f"duplicate tool name: {name}")
            schema = input_schema if input_schema is not None else _schema_from_signature(func)
            self._tools[name] = Tool(
                name=name,
                description=description,
                input_schema=schema,
                handler=func,
                title=title,
                output_schema=output_schema,
                annotations=annotations or {},
            )
            return func

        return decorator

    def listing(self) -> list[dict[str, Any]]:
        return [tool.to_listing() for tool in self._tools.values()]

    def call(self, name: str, arguments: Mapping[str, Any] | None) -> Any:
        """Invoke a tool by name.

        Raises:
            JsonRpcError: for an unknown tool name (a protocol level problem).
            ToolError: for bad arguments or a business rule failure.
        """
        from .jsonrpc import METHOD_NOT_FOUND, JsonRpcError

        tool = self._tools.get(name)
        if tool is None:
            raise JsonRpcError(
                METHOD_NOT_FOUND,
                f"Unknown tool: {name}",
                {"availableTools": self.names()},
            )

        args = dict(arguments or {})
        if not isinstance(arguments, (dict, type(None))):
            raise ToolError(
                "Tool arguments must be a JSON object.",
                {"received": type(arguments).__name__},
            )

        _validate_against_schema(args, tool.input_schema, path="arguments")
        return tool.handler(**args)


def _is_valid_tool_name(name: str) -> bool:
    if not 1 <= len(name) <= 128:
        return False
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    )
    return all(char in allowed for char in name)


def _schema_from_signature(func: Callable[..., Any]) -> dict[str, Any]:
    """Derive a permissive object schema when the author did not supply one."""
    signature = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in signature.parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        properties[param.name] = {"type": "string"}
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _validate_against_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
) -> None:
    """Validate the subset of JSON Schema 2020-12 that our tool schemas use.

    Only the keywords we actually author are enforced: type, properties,
    required, additionalProperties, enum, const, items, minimum, maximum,
    minLength, maxLength, pattern, oneOf, anyOf.

    Validation failures raise :class:`ToolError`, never a protocol error.
    """

    if "const" in schema and value != schema["const"]:
        raise ToolError(f"{path} must equal {schema['const']!r}.")

    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(repr(item) for item in schema["enum"])
        raise ToolError(f"{path} must be one of: {allowed}.")

    for combinator in ("oneOf", "anyOf"):
        if combinator in schema:
            options = schema[combinator]
            failures: list[str] = []
            for option in options:
                try:
                    _validate_against_schema(value, option, path=path)
                except ToolError as exc:
                    failures.append(str(exc))
                else:
                    return
            raise ToolError(
                f"{path} did not match any permitted shape.",
                {"attempts": failures},
            )

    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        raise ToolError(
            f"{path} must be of type {expected}, got {_type_name(value)}."
        )

    if isinstance(value, dict):
        _validate_object(value, schema, path=path)
    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_against_schema(item, item_schema, path=f"{path}[{index}]")
    elif isinstance(value, str):
        _validate_string(value, schema, path=path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolError(f"{path} must be >= {schema['minimum']}.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolError(f"{path} must be <= {schema['maximum']}.")


def _validate_object(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    path: str,
) -> None:
    properties = schema.get("properties") or {}
    for name in schema.get("required", []):
        if name not in value:
            raise ToolError(f"{path}.{name} is required.")

    additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            _validate_against_schema(item, properties[key], path=f"{path}.{key}")
        elif additional is False:
            raise ToolError(
                f"{path}.{key} is not a supported field.",
                {"supportedFields": sorted(properties)},
            )
        elif isinstance(additional, Mapping):
            _validate_against_schema(item, additional, path=f"{path}.{key}")


def _validate_string(value: str, schema: Mapping[str, Any], *, path: str) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        raise ToolError(
            f"{path} must be at least {schema['minLength']} characters.",
        )
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        raise ToolError(
            f"{path} must be at most {schema['maxLength']} characters.",
        )
    if "pattern" in schema:
        import re

        if re.fullmatch(schema["pattern"], value) is None:
            raise ToolError(
                f"{path} must match the pattern {schema['pattern']}.",
            )


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
