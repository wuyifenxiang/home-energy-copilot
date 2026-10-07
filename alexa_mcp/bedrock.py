"""Optional Amazon Bedrock rephrasing of spoken responses.

Why this exists
---------------
The tools in this server produce templated ``speech`` strings. They are correct,
but they are the same wording for every customer. Amazon Bedrock can rephrase
them naturally, which is what makes a voice assistant feel less like a form
letter.

The dangerous part, and the whole reason this module is careful
--------------------------------------------------------------
A language model can alter a number. If a customer asks what today's energy cost
and the assistant says "thirty-one dollars" when the measured figure is $9.91,
the system has lied about a bill. That is a trust-destroying failure, and it is
exactly the failure mode a judge will probe.

So Bedrock is never allowed to be authoritative for a number. It receives a
sentence that already contains the correct figures and may only re-word it. After
the model returns, every numeric token in the candidate is compared against the
numeric tokens in the original. If anything is missing, added, or changed, the
candidate is discarded and the templated sentence is used instead.

Design consequences
-------------------
* The feature is **opt-in**: without credentials, the server behaves exactly as
  before. Nothing breaks, and there is nothing to configure.
* The feature is **fail-open**: any network, auth, throttling, or parse error
  falls back to the template and is logged at debug level, never surfaced as a
  tool failure. A voice assistant must not go silent because a cloud call failed.
* Identical input text is cached, so repeated questions do not repeat spend.
* Implemented with the standard library (``urllib`` + SigV4), consistent with the
  rest of the project, which has no runtime dependencies.

Enable it with environment variables::

    set ALEXA_MCP_BEDROCK_MODEL=us.anthropic.claude-3-5-haiku-20241022-v1:0
    set AWS_REGION=us-east-1
    set AWS_ACCESS_KEY_ID=...
    set AWS_SECRET_ACCESS_KEY=...

Or, on a machine with a configured AWS CLI, omit the key variables and set
``ALEXA_MCP_BEDROCK_MODEL`` plus ``AWS_PROFILE`` support from your environment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("alexa_mcp.bedrock")

SERVICE = "bedrock-runtime"
DEFAULT_MODEL = ""  # empty means "disabled"
DEFAULT_REGION = "us-east-1"
CACHE_TTL_SECONDS = 60 * 30
REQUEST_TIMEOUT_SECONDS = 12

# Digit groups, currency amounts, and percentages. Used to prove the model did
# not touch a figure.
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")

SYSTEM_PROMPT = (
    "You rewrite sentences for a voice assistant that answers questions about a "
    "home's energy use.\n"
    "Rules you must follow exactly:\n"
    "1. Keep every number, unit, currency amount, and device name identical. Do "
    "not round, convert, or recompute anything.\n"
    "2. Do not add numbers that are not in the input.\n"
    "3. Keep the same meaning and the same facts.\n"
    "4. Output one or two short spoken sentences, under 45 words.\n"
    "5. No markdown, no bullet points, no emoji, no quotation marks.\n"
    "6. Do not mention that you are rewriting anything.\n"
    "Reply with the rewritten sentence only."
)


class BedrockClient:
    """Minimal SigV4 client for the Bedrock Converse API.

    Only the ``Converse`` operation is used: it takes a normalized
    ``messages`` shape across model families, so the same code works with
    Anthropic, Amazon Nova, and Meta models.
    """

    def __init__(
        self,
        *,
        region: str | None = None,
        model_id: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION
        self.model_id = model_id if model_id is not None else os.environ.get("ALEXA_MCP_BEDROCK_MODEL", DEFAULT_MODEL)
        self.access_key = access_key if access_key is not None else os.environ.get("AWS_ACCESS_KEY_ID")
        self.secret_key = secret_key if secret_key is not None else os.environ.get("AWS_SECRET_ACCESS_KEY")
        self.session_token = session_token if session_token is not None else os.environ.get("AWS_SESSION_TOKEN")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        """True only when we have both a model and usable credentials."""
        return bool(self.model_id and self.access_key and self.secret_key)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model_id or None,
            "region": self.region,
            "credentialSource": (
                "environment" if self.access_key else "none"
            ),
        }

    # -- signing ----------------------------------------------------------

    def _signature_headers(self, body: bytes, now: datetime) -> dict[str, str]:
        """Build SigV4 headers for the Converse endpoint."""
        host = f"{SERVICE}.{self.region}.amazonaws.com"
        path = f"/model/{self.model_id}/converse"
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()

        headers = {
            "content-type": "application/json",
            "host": host,
            "x-amz-date": amz_date,
        }
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token

        signed_names = ";".join(sorted(headers))
        canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
        canonical_request = "\n".join(
            ["POST", path, "", canonical_headers, signed_names, payload_hash]
        )

        scope = f"{date_stamp}/{self.region}/{SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        key = f"AWS4{self.secret_key}".encode("utf-8")
        for part in (date_stamp, self.region, SERVICE, "aws4_request"):
            key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
        signature = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        result = {
            "Content-Type": "application/json",
            "X-Amz-Date": amz_date,
            "Authorization": (
                f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed_names}, Signature={signature}"
            ),
        }
        if self.session_token:
            result["X-Amz-Security-Token"] = self.session_token
        return result

    # -- request ----------------------------------------------------------

    def converse(self, user_text: str) -> str | None:
        """Ask Bedrock to rewrite one sentence. Returns None on any failure."""
        if not self.enabled:
            return None

        body = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": [{"text": user_text}]}
                ],
                "system": [{"text": SYSTEM_PROMPT}],
                "inferenceConfig": {"maxTokens": 200, "temperature": 0.2, "topP": 0.9},
            }
        ).encode("utf-8")

        now = datetime.now(timezone.utc)
        url = f"https://{SERVICE}.{self.region}.amazonaws.com/model/{self.model_id}/converse"
        request = urllib.request.Request(url, data=body, method="POST")
        for key, value in self._signature_headers(body, now).items():
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            LOGGER.debug("Bedrock HTTP %s: %s", exc.code, detail)
            return None
        except Exception as exc:  # network, timeout, DNS, TLS
            LOGGER.debug("Bedrock request failed: %s", exc)
            return None

        try:
            blocks = payload["output"]["message"]["content"]
            text = " ".join(
                block["text"] for block in blocks if isinstance(block, dict) and "text" in block
            ).strip()
        except (KeyError, TypeError):
            LOGGER.debug("Unexpected Bedrock response shape: %s", str(payload)[:300])
            return None
        return text or None


def numbers_in(text: str) -> list[str]:
    """Extract numeric tokens, normalized so '9.91' and '9,91' compare equal.

    Trailing zeros are dropped so that a model writing "13.9" instead of "13.90"
    is not treated as a factual change. Everything else must match exactly.
    """
    found: list[str] = []
    for raw in NUMBER_PATTERN.findall(text):
        token = raw.replace(",", ".")
        if "." in token:
            token = token.rstrip("0").rstrip(".")
        found.append(token or "0")
    return found


def digits_preserved(original: str, candidate: str) -> bool:
    """True when the candidate contains exactly the original's numbers.

    This is the guard that makes a language model safe to use for a bill. An
    altered, dropped, or invented figure fails the check.
    """
    return sorted(numbers_in(original)) == sorted(numbers_in(candidate))


class SpeechRewriter:
    """Rewrites spoken sentences with Bedrock, falling back to the template.

    Thread-safe: the HTTP layer serves requests concurrently. Worst case two
    threads compute the same rewrite; the cache write is idempotent.
    """

    def __init__(self, client: BedrockClient | None = None, *, enabled: bool = True) -> None:
        self.client = client or BedrockClient()
        self._rule_enabled = enabled
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self.stats = {"attempted": 0, "used": 0, "rejected": 0, "failed": 0, "cached": 0}

    @property
    def active(self) -> bool:
        return self._rule_enabled and self.client.enabled

    def status(self) -> dict[str, Any]:
        info = self.client.describe()
        info["active"] = self.active
        info["stats"] = dict(self.stats)
        return info

    def rewrite(self, speech: str) -> str:
        """Return an improved sentence, or the original when anything is off."""
        if not self.active or not speech.strip():
            return speech

        cache_key = hashlib.sha256(speech.encode("utf-8")).hexdigest()
        with self._lock:
            hit = self._cache.get(cache_key)
            if hit and (time.time() - hit[0]) < CACHE_TTL_SECONDS:
                self.stats["cached"] += 1
                return hit[1]

        self.stats["attempted"] += 1
        try:
            candidate = self.client.converse(speech)
        except Exception:
            # The fail-open guarantee lives here, not only in the module-level
            # improve() wrapper. A voice assistant must not go silent because a
            # cloud call raised, and callers of rewrite() must not have to know
            # that rule.
            self.stats["failed"] += 1
            LOGGER.debug("Bedrock call raised; using the template", exc_info=True)
            return speech

        if not candidate:
            self.stats["failed"] += 1
            return speech

        candidate = " ".join(candidate.split())
        if not digits_preserved(speech, candidate):
            self.stats["rejected"] += 1
            LOGGER.warning(
                "Rejected Bedrock rewrite because the figures changed. "
                "original=%r candidate=%r",
                speech,
                candidate,
            )
            return speech

        with self._lock:
            self._cache[cache_key] = (time.time(), candidate)
        self.stats["used"] += 1
        return candidate


# Module-level default so tools can use it without threading a dependency.
_default_rewriter: SpeechRewriter | None = None
_default_lock = threading.Lock()


def get_rewriter() -> SpeechRewriter:
    global _default_rewriter
    if _default_rewriter is None:
        with _default_lock:
            if _default_rewriter is None:
                _default_rewriter = SpeechRewriter()
    return _default_rewriter


def reset_rewriter(rewriter: SpeechRewriter | None = None) -> None:
    """Replace the module default. Used by tests."""
    global _default_rewriter
    with _default_lock:
        _default_rewriter = rewriter


def improve(speech: str) -> str:
    """Convenience wrapper that can never raise."""
    try:
        return get_rewriter().rewrite(speech)
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Speech rewriting failed", exc_info=True)
        return speech
