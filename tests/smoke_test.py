"""End-to-end smoke test for the Alexa+ MCP server.

Starts the real HTTP server on an ephemeral port and drives it with the
dependency-free client in ``alexa_mcp.client``, asserting both the happy path and
the failure modes the MCP specification calls out (Origin validation, session
handling, tool execution errors).

Run it with::

    python tests/smoke_test.py

Exit code 0 means every check passed.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

# Allow the suite to run from anywhere (for example `python tests/smoke_test.py`)
# by putting the repository root on the path. The package itself is importable
# from the root with no installation, so `python -m alexa_mcp` also works.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alexa_mcp.client import ACCEPT, McpClientError, McpHttpClient  # noqa: E402
from alexa_mcp.server import PROTOCOL_VERSION, create_server  # noqa: E402
from alexa_mcp.store import Database, seed_demo_home  # noqa: E402
from alexa_mcp.tools import build_registry  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label} {detail}".strip())
        print(f"  FAIL  {label} {detail}".rstrip())


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    db = Database(":memory:")
    seed_demo_home(db)
    registry = build_registry(db)

    httpd, app = create_server(
        registry,
        host="127.0.0.1",
        port=0,
        log_level=40,
        instructions=(
            "Prefer get_home_status before recommending anything. Anything that "
            "changes the home must be proposed first."
        ),
    )
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/mcp"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"server listening on {url}")

    try:
        run_checks(url, registry)
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()

    print("\n" + "=" * 64)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFailures:")
        for item in FAILED:
            print(f"  - {item}")
        return 1
    return 0


def run_checks(url: str, registry) -> None:
    client = McpHttpClient(url)

    section("Handshake")
    result = client.initialize()
    check("initialize returns 2025-11-25", result["protocolVersion"] == PROTOCOL_VERSION,
          f"got {result.get('protocolVersion')}")
    check("server advertises tools capability", "tools" in result["capabilities"])
    check("serverInfo carries a name and version",
          bool(result["serverInfo"].get("name")) and bool(result["serverInfo"].get("version")))
    check("Mcp-Session-Id issued", bool(client.session_id))
    check("initialize result includes instructions", "instructions" in result)

    section("Tool discovery")
    tools = client.list_tools()
    names = {tool["name"] for tool in tools}
    check("tools/list returns the full surface", len(tools) == len(registry),
          f"{len(tools)} vs {len(registry)}")
    for expected in (
        "get_home_status",
        "get_energy_report",
        "find_energy_waste",
        "recommend_energy_actions",
        "apply_energy_plan",
        "set_device_state",
        "list_automations",
    ):
        check(f"tool present: {expected}", expected in names)
    check("every tool declares an object inputSchema",
          all(tool["inputSchema"].get("type") == "object" for tool in tools))
    check("every tool declares a description",
          all(len(tool.get("description", "")) > 20 for tool in tools))
    check("read-only tools are annotated as such",
          all(tool.get("annotations", {}).get("readOnlyHint") is True
              for tool in tools
              if tool["name"] in {"get_home_status", "get_energy_report",
                                  "find_energy_waste", "recommend_energy_actions",
                                  "list_automations"}))

    section("Read-only tools")
    status = client.call_tool("get_home_status")
    check("get_home_status succeeds", status.get("isError") is not True)
    check("get_home_status returns structured content",
          isinstance(status.get("structuredContent"), dict))
    check("get_home_status reports devices on",
          status["structuredContent"]["devicesOn"] > 0,
          json.dumps(status.get("structuredContent", {}))[:120])
    check("speech text is short and pronounceable",
          len(_speech_of(status)) < 240, f"{len(_speech_of(status))} chars")

    report = client.call_tool("get_energy_report", {"period": "today", "group_by": "device"})
    check("get_energy_report succeeds", report.get("isError") is not True)
    check("energy report has a non-zero total",
          report["structuredContent"]["totalKwh"] > 0,
          str(report["structuredContent"].get("totalKwh")))
    check("energy breakdown is sorted descending",
          [item["kwh"] for item in report["structuredContent"]["breakdown"]]
          == sorted((item["kwh"] for item in report["structuredContent"]["breakdown"]), reverse=True))

    waste = client.call_tool("find_energy_waste", {"max_findings": 3})
    check("find_energy_waste succeeds", waste.get("isError") is not True)
    check("waste findings respect max_findings",
          len(waste["structuredContent"]["findings"]) <= 3)

    plan = client.call_tool("recommend_energy_actions", {"goal": "lower_bill", "max_actions": 3})
    check("recommend_energy_actions succeeds", plan.get("isError") is not True)
    check("recommendations carry estimated savings",
          all(item["estimatedMonthlySaving"] > 0
              for item in plan["structuredContent"]["actions"]))
    check("recommendations require confirmation",
          plan["structuredContent"].get("requiresConfirmation") is True)

    automations = client.call_tool("list_automations")
    check("list_automations succeeds", automations.get("isError") is not True)
    check("automations include enabled count",
          automations["structuredContent"]["enabledCount"] > 0)

    section("State changes")
    before = client.call_tool("get_home_status")["structuredContent"]["devicesOn"]
    off = client.call_tool("set_device_state", {"device": "living room ac", "state": "off"})
    check("set_device_state resolves a spoken name", off.get("isError") is not True,
          json.dumps(off.get("structuredContent", {}))[:160])
    check("set_device_state reports the change", off["structuredContent"]["changed"] is True)
    after = client.call_tool("get_home_status")["structuredContent"]["devicesOn"]
    check("turning a device off reduces the on-count", after == before - 1, f"{before} -> {after}")

    idempotent = client.call_tool("set_device_state", {"device": "living room ac", "state": "off"})
    check("repeating the same command is a no-op",
          idempotent["structuredContent"]["changed"] is False)
    check("no-op still succeeds", idempotent.get("isError") is not True)

    preview = client.call_tool("apply_energy_plan", {"action_ids": ["shift-ac-living"]})
    check("apply_energy_plan preview does not act",
          preview["structuredContent"]["applied"] is False)
    check("preview tells the model to confirm",
          "confirm" in preview["structuredContent"]["nextStep"])
    applied = client.call_tool(
        "apply_energy_plan", {"action_ids": ["shift-ac-living"], "confirm": True}
    )
    check("apply_energy_plan with confirm acts",
          applied["structuredContent"]["applied"] is True)

    section("Error handling (tool execution errors, not protocol errors)")
    bad_period = client.call_tool("get_energy_report", {"period": "last century"})
    check("invalid enum returns isError, not a JSON-RPC error",
          bad_period.get("isError") is True)
    check("invalid enum text names the allowed values",
          "supportedPeriods" in json.dumps(bad_period.get("structuredContent", {}))
          or "period" in _speech_of(bad_period).lower())
    check("error content still has a text block",
          bad_period["content"][0]["type"] == "text")

    missing = client.call_tool("get_energy_report", {})
    check("missing required field is reported to the model", missing.get("isError") is True)

    unknown_device = client.call_tool("set_device_state", {"device": "flux capacitor", "state": "on"})
    check("unknown device lists the known ids",
          unknown_device.get("isError") is True
          and "knownDeviceIds" in json.dumps(unknown_device.get("structuredContent", {})))

    extra_field = client.call_tool("get_home_status", {"nonsense": 1})
    check("unsupported field is rejected", extra_field.get("isError") is True)
    check("unsupported field lists what is supported",
          "supportedFields" in json.dumps(extra_field.get("structuredContent", {})))

    try:
        client.call_tool("no_such_tool", {})
        check("unknown tool name is a JSON-RPC error", False, "no error raised")
    except McpClientError as exc:
        check("unknown tool name is a JSON-RPC error", "-32601" in str(exc))
        check("unknown tool error lists available tools", "availableTools" in str(exc))

    section("Transport conformance")
    check("wrong protocol version is negotiated down",
          McpHttpClient(url).initialize(protocol_version="1999-01-01")["protocolVersion"]
          == PROTOCOL_VERSION)

    check("bad Origin is rejected with 403", _expect_status(url, 403, origin="https://evil.example"))
    check("bad Origin beats a valid session (403 before 200)",
          _expect_status(url, 403, origin="https://evil.example", session=client.session_id,
                         body=json.dumps({"jsonrpc": "2.0", "id": 2,
                                          "method": "tools/list", "params": {}}).encode()))
    check("localhost Origin is allowed with a valid session",
          _expect_status(url, 200, origin="http://localhost:3000", session=client.session_id,
                         body=json.dumps({"jsonrpc": "2.0", "id": 3,
                                          "method": "tools/list", "params": {}}).encode()))
    check("missing Accept header is rejected",
          _expect_status(url, 406, accept="application/json"))
    check("malformed JSON body is a parse error",
          _expect_status(url, 400, body=b"{not json"))
    check("unknown session id is rejected with 404",
          _expect_status(url, 404, session="definitely-not-a-session"))
    check("tools/call without a session is rejected",
          _expect_status(url, 400, body=json.dumps(
              {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
               "params": {"name": "get_home_status", "arguments": {}}}
          ).encode(), session=None))
    check("GET without a session is rejected", _expect_status(url, 400, method="GET"))
    check("health endpoint reports the tool surface", _health_ok(url))


def _speech_of(result: dict) -> str:
    blocks = [block.get("text", "") for block in result.get("content", [])]
    return blocks[-1] if blocks else ""


def _expect_status(
    url: str,
    expected: int,
    *,
    origin: str | None = None,
    accept: str = ACCEPT,
    body: bytes | None = None,
    session: str | None = "",
    method: str = "POST",
) -> bool:
    if body is None and method == "POST":
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        ).encode()
    request = urllib.request.Request(url, data=body if method == "POST" else None, method=method)
    request.add_header("Accept", accept)
    if method == "POST":
        request.add_header("Content-Type", "application/json")
    if origin:
        request.add_header("Origin", origin)
    if session:
        request.add_header("Mcp-Session-Id", session)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == expected
    except urllib.error.HTTPError as exc:
        return exc.code == expected
    except Exception:
        return False


def _health_ok(url: str) -> bool:
    health_url = url.rsplit("/", 1)[0] + "/healthz"
    try:
        with urllib.request.urlopen(health_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("status") == "ok" and len(payload.get("tools", [])) >= 7
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
