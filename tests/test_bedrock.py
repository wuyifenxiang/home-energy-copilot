"""Unit tests for the Bedrock speech rewriter.

Run with:

    python tests/test_bedrock.py

These tests never call AWS. They use a stub client, which is the point: the
guard that protects a customer's bill figures must be provable offline.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alexa_mcp.bedrock import (  # noqa: E402
    BedrockClient,
    SpeechRewriter,
    digits_preserved,
    numbers_in,
)

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


class StubClient(BedrockClient):
    """A client that returns canned text instead of calling AWS."""

    def __init__(self, reply: str | None, *, model: str = "stub-model") -> None:
        super().__init__(region="us-east-1", model_id=model, access_key="AK", secret_key="SK")
        self.reply = reply
        self.calls = 0

    def converse(self, user_text: str) -> str | None:  # noqa: D102
        self.calls += 1
        return self.reply


class ExplodingClient(StubClient):
    def converse(self, user_text: str) -> str | None:  # noqa: D102
        raise RuntimeError("network exploded")


def main() -> int:
    section("Number extraction")
    check("finds a currency amount", numbers_in("Cost USD 9.91") == ["9.91"])
    check("normalizes comma decimals", numbers_in("9,91") == ["9.91"])
    check("drops trailing zeros", numbers_in("13.90") == ["13.9"])
    check("finds percentages and integers",
          numbers_in("46.7 percent of 231 kWh") == ["46.7", "231"])
    check("handles no numbers", numbers_in("nothing here") == [])
    check("keeps leading-zero values", numbers_in("0.18") == ["0.18"])

    section("Figure-preservation guard (the bill-safety check)")
    original = "So far today you used 31.98 kilowatt hours and spent USD 9.91."
    check("identical text passes", digits_preserved(original, original))
    check("pure rewording passes",
          digits_preserved(original, "Today your home has used 31.98 kilowatt hours, costing USD 9.91."))
    check("trailing-zero restyle passes",
          digits_preserved("saves 13.90 a month", "saves about 13.9 a month"))
    check("ALTERED amount is rejected", not digits_preserved(original, "you spent USD 91.9 today"))
    check("ROUNDED amount is rejected", not digits_preserved(original, "you spent USD 10 today"))
    check("DROPPED figure is rejected", not digits_preserved(original, "you used some power today"))
    check("INVENTED figure is rejected",
          not digits_preserved("you used 31.98 kWh", "you used 31.98 kWh, up 40 percent"))
    check("digit transposition is rejected",
          not digits_preserved("USD 13.88", "USD 13.68"))

    section("Rewriter behaviour")
    ok_client = StubClient("Your home has drawn 31.98 kilowatt hours today, costing USD 9.91.")
    rewriter = SpeechRewriter(ok_client)
    out = rewriter.rewrite(original)
    check("rewrites when figures are preserved", out != original)
    check("used the model text", "has drawn" in out)
    check("counts the success", rewriter.stats["used"] == 1)

    check("second identical call is served from cache", rewriter.rewrite(original) == out)
    check("cache did not call the model again", ok_client.calls == 1)
    check("cache hit counted", rewriter.stats["cached"] == 1)

    liar = SpeechRewriter(StubClient("You spent about USD 40 today."))
    out2 = liar.rewrite(original)
    check("a model that changes the amount is rejected", out2 == original)
    check("rejection counted", liar.stats["rejected"] == 1)

    silent = SpeechRewriter(StubClient(None))
    check("no model output falls back to the template", silent.rewrite(original) == original)
    check("failure counted", silent.stats["failed"] == 1)

    broken = SpeechRewriter(ExplodingClient("whatever"))
    try:
        result = broken.rewrite(original)
        check("a raising client never propagates", result == original)
    except Exception as exc:  # noqa: BLE001
        check("a raising client never propagates", False, f"raised {exc!r}")

    section("Disabled by default (no AWS account required)")
    unconfigured = BedrockClient(model_id="", access_key=None, secret_key=None)
    check("client is disabled without a model", not unconfigured.enabled)
    no_keys = BedrockClient(model_id="some-model", access_key=None, secret_key=None)
    check("client is disabled without credentials", not no_keys.enabled)
    passthrough = SpeechRewriter(no_keys)
    check("inactive rewriter returns the template unchanged",
          passthrough.rewrite(original) == original)
    check("inactive rewriter makes no calls", passthrough.stats["attempted"] == 0)

    forced_off = SpeechRewriter(ok_client, enabled=False)
    check("explicitly disabled rewriter is inert", forced_off.rewrite(original) == original)

    section("SigV4 signing shape")
    configured = BedrockClient(
        region="us-east-1", model_id="m", access_key="AKIDEXAMPLE", secret_key="SECRET"
    )
    check("enabled with model and keys", configured.enabled)
    from datetime import datetime, timezone

    headers = configured._signature_headers(b'{"a":1}', datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc))
    auth = headers.get("Authorization", "")
    check("Authorization uses the AWS4-HMAC-SHA256 scheme", auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261008/us-east-1/bedrock-runtime/aws4_request"))
    check("SignedHeaders lists host and x-amz-date",
          "host" in auth and "x-amz-date" in auth)
    check("signature is 64 hex characters", len(auth.rsplit("Signature=", 1)[-1]) == 64)
    check("x-amz-date header is set", headers.get("X-Amz-Date") == "20261008T120000Z")
    check("session token omitted when absent", "X-Amz-Security-Token" not in headers)

    with_token = BedrockClient(
        region="us-east-1", model_id="m", access_key="AK", secret_key="SK", session_token="TOK"
    )
    headers2 = with_token._signature_headers(b"{}", datetime(2026, 10, 8, tzinfo=timezone.utc))
    check("session token is forwarded when present",
          headers2.get("X-Amz-Security-Token") == "TOK")

    print("\n" + "=" * 64)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFailures:")
        for item in FAILED:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
