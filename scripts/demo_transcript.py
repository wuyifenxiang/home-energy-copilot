"""Print a realistic conversation transcript against the MCP tools.

This renders exactly what the Alexa+ service would receive for each turn: the
spoken text, the on-screen text, and the structured payload.  It is the fastest
way to sanity-check wording before recording the demo video.

The savings turn is *chained*: it takes the action id that
``recommend_energy_actions`` actually returned and feeds it to
``apply_energy_plan``, so the transcript can never drift out of sync with the
tool surface the way a hard-coded script would.

    python scripts/demo_transcript.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alexa_mcp.store import Database, seed_demo_home  # noqa: E402
from alexa_mcp.tools import build_registry  # noqa: E402

WIDTH = 78


def rule(char: str = "=") -> None:
    print(char * WIDTH)


def render(registry, spoken_request: str, tool_name: str, arguments: dict) -> dict:
    print(f"\nCUSTOMER : {spoken_request}")
    print(f"-> tool   : {tool_name}({json.dumps(arguments, ensure_ascii=False)})")
    result = registry.call(tool_name, arguments)
    speech = result.get("speech", "")
    display = result.get("display", "")
    print(f"ALEXA    : {speech}")
    if display and display != speech:
        print("   screen:")
        for line in display.splitlines():
            print(f"     {line}")
    if isinstance(result.get("data"), dict):
        preview = json.dumps(result["data"], ensure_ascii=False)
        print(f"   data  : {preview[:190]}{'...' if len(preview) > 190 else ''}")
    print("-" * WIDTH)
    return result


def main() -> int:
    db = Database(":memory:")
    seed_demo_home(db)
    registry = build_registry(db)

    rule()
    print(f"Alexa+ add-on demo transcript   |   {len(registry)} tools registered")
    rule()

    try:
        render(registry, "What is running in my house right now?", "get_home_status", {})
        render(
            registry,
            "How much energy did we use today?",
            "get_energy_report",
            {"period": "today", "group_by": "device"},
        )
        render(registry, "Are we wasting power?", "find_energy_waste", {"max_findings": 3})

        plan = render(
            registry,
            "How can I lower my bill?",
            "recommend_energy_actions",
            {"goal": "lower_bill", "max_actions": 3},
        )
        actions = plan.get("data", {}).get("actions", [])
        if not actions:
            print("\n(no recommendations were produced, so the apply turn is skipped)")
        else:
            chosen = actions[0]["actionId"]
            title = actions[0]["title"]
            # Two-phase: preview exactly what would change, then confirm.
            render(
                registry,
                f"Tell me what '{title}' would do.",
                "apply_energy_plan",
                {"action_ids": [chosen]},
            )
            render(
                registry,
                "Go ahead.",
                "apply_energy_plan",
                {"action_ids": [chosen], "confirm": True},
            )

        render(
            registry,
            "Turn off the living room AC.",
            "set_device_state",
            {"device": "living room ac", "state": "off"},
        )
        render(registry, "What automations do I have?", "list_automations", {})
    except Exception as exc:  # noqa: BLE001
        print(f"\n!! FAILED: {type(exc).__name__}: {exc}")
        return 1

    rule()
    print("Every turn above is a single tools/call over the MCP endpoint.")
    rule()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

