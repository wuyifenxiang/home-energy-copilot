# Friction Log — Amazon Developer Hackathon 2026, Alexa+ track

**Project:** Home Energy Copilot (self-hosted Alexa+ MCP add-on)
**Track:** Alexa+ (primary) · AWS Builder (mini) · Open Source (mini)
**Protocol revision targeted:** MCP `2025-11-25`
**Logged by:** `<YOUR GITHUB USERNAME>`
**Window:** 2026-10-05 → `<SUBMISSION DATE>`

## How to read this

Every entry below was hit while building this submission. Each one records the exact
command or request, the raw output, what the documentation led us to expect, and what
would have removed the friction. Entries are graded by how much time they cost.

Priorities: **P0** blocked work · **P1** cost significant time · **P2** confusing but
worked around.

| # | Area | Priority | One-line summary |
|---|---|---|---|
| 1 | Docs site | P1 | Alexa+ MCP docs return an empty body to non-browser clients |
| 2 | Docs site | P1 | Rendered docs omit the normative text that decides implementation |
| 3 | Docs coverage | P1 | No single page states the required protocol revision + transport matrix |
| 4 | Discovery | P1 | Devpost page is JS-rendered; rules unreachable without a browser |
| 5 | Discovery | P2 | Third-party listings disagree on prize pool and submission requirements |
| 6 | Environment | P1 | `pip` stalls against PyPI, forcing a dependency-free implementation |
| 7 | Ecosystem | P2 | No official dependency-free client, so conformance had to be self-verified |
| 8 | Spec UX | P2 | The distinction between protocol and tool-execution errors is easy to miss |
| 9 | Spec UX | P2 | "Negotiate down" behaviour when protocol versions differ is underspecified |

---

## 1. Alexa+ MCP documentation returns an empty body to non-browser clients — P1

**What we did**

```bash
curl -sS -D - -o /dev/null https://developer.amazon.com/zh/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
```

**What we got**

```
HTTP/2 202
content-type: text/html; charset=utf-8
content-length: 0
```

HTTP **202 Accepted** with a **zero-length body**. Not 200, not 404. A naive client treats
202 as success and then parses nothing, producing an empty document rather than an error.

**What we expected**

Either the HTML document, or a status code that clearly indicates the content is not
available to this client (for example a redirect to a JS-rendered route, or 403).

**Why it cost time**

Every automated attempt to read the official MCP toolkit quickstart silently produced zero
content. The failure mode is indistinguishable from a correct-but-empty page, so it is easy
to conclude the page simply has no content rather than that it was withheld.

**What would help**

Return a real status code, or serve a minimal no-JS fallback document containing the code
samples and the normative requirements.

---

## 2. Rendered docs omit the normative text that decides implementation — P1

**What we did**

Fetched the pages that *do* render, for example the English quickstart:

```bash
curl -sS https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
```

**What we got**

A complete navigation tree — Get Started, MCP toolkit, Category SDK, Testing, Payments,
Certify — and then the body stops. Repeated for `mcp-toolkit-overview.html` and
`mcp-toolkit-test-add-ons.html`: same result, navigation only.

**What we expected**

The quickstart body: endpoint conventions, whether authentication is mandatory for a
preview add-on, and how to register the endpoint with Alexa+.

**Why it cost time**

The navigation tree does confirm which pages exist (`Local Inspector`, `Test Your MCP
Add-ons`, `Test in the Web Simulator`, `Certify and Publish`), but none of the pages that
decide how to implement the server are readable without a browser session. Implementation
therefore had to be driven from the MCP specification itself.

**What would help**

Server-side rendering for documentation bodies, or a machine-readable index (OpenAPI or
JSON) of the same content.

---

## 3. No single page states the required protocol revision and transport matrix — P1

**What we did**

Searched for the authoritative statement of what an Alexa+ MCP add-on must implement.

**What we found**

The hackathon listing says: *"Build a self-hosted MCP server (spec 2025-11-25 or later,
Streamable HTTP)"*. The MCP project's own page for that revision then documents **two**
transports (stdio and Streamable HTTP) and several optional capabilities, with no
indication of which subset Alexa+ actually requires — for example whether `GET` must be
supported, whether SSE responses are required or optional, whether authentication must be
implemented for a preview add-on, and whether `resources`/`prompts` must be answered.

**Why it cost time**

We implemented the conservative superset: `POST` and `GET` on one endpoint, both `200
application/json` and `text/event-stream` response paths, session management, and `401`-free
local operation with a documented path to authentication. That is more work than the
minimum, and we still cannot state with certainty which parts are required.

**What we expected**

A single "Alexa+ MCP add-on conformance" page listing required versus optional protocol
surface.

**What would help**

A normative checklist, plus a conformance test suite that a submission can run.

---

## 4. Devpost rules page is unreachable without a browser — P1

**What we did**

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://amazonappdev2026.devpost.com/rules
```

**What we got**

```
202
```

Same zero-body pattern as entry 1.

**Why it cost time**

Eligibility and the exact list of required submission artefacts could not be verified from
the authoritative source. We had to reconstruct requirements from the Amazon Developer
community announcement and third-party listings, which is exactly the situation the rules
page exists to prevent.

**What would help**

A static copy of the rules at a stable URL, or an `?format=json` variant.

---

## 5. Third-party listings disagree on prize pool and submission details — P2

**What we did**

Cross-checked the same event across the official community announcement and three
third-party listings.

**What we found**

| Source | Total value | Submission list |
|---|---|---|
| Official community announcement | not stated numerically | working demo, code repo, product feedback |
| Listing A | `$138,000` cash + AWS credits | demo, repo, **<3 minute video**, product feedback, track details |
| Listing B | `$190,000` value of cash and AWS credits | demo, repo, product feedback |

Both figures may be reconcilable (cash versus total value including credits), and the
discrepancy costs nothing to resolve if you read the rules page — but the rules page is not
machine-readable (entry 4), so a participant automating their submission gets two different
numbers and two different checklists. The video length requirement in particular is a hard
constraint that appears in only one source.

**What would help**

Publish the prize breakdown and the submission checklist in the same machine-readable form
as the rest of the event data.

---

## 6. `pip` stalls against PyPI, forcing a dependency-free implementation — P1

**What we did**

```bash
python -m pip download fastmcp --no-deps -d "$TEMP/pypiprobe"
```

**What we got**

No output, no error, no exit — still running after 120 seconds and killed manually. No
progress lines, no retry notices, no timeout.

**What we expected**

Either the wheel, or a resolvable error such as a DNS failure or a connection timeout
within the default retry budget.

**How we resolved it**

We took the official `mcp` Python SDK off the table entirely and implemented the protocol
against the specification using only the standard library. The result runs with zero
third-party dependencies and no network access.

That turned out to be a genuine advantage for a hackathon submission — `python tests/smoke_test.py`
works on a fresh machine with no install step — but it was a forced architectural decision
made by an opaque hang, not by choice.

**What would help**

Fail loudly. A silent multi-minute stall is the worst possible outcome, because the correct
response (stop waiting, change approach) is invisible.

---

## 7. No official conformance client, so correctness had to be self-verified — P2

**What we did**

Looked for a way to prove the server conforms, short of a live Alexa+ device.

**What we found**

The docs reference a **Local Inspector** and a **Web Simulator**, but both pages are behind
the rendering problem in entry 2, so what they validate could not be confirmed.

**How we resolved it**

We wrote a dependency-free MCP client (`alexa_mcp/client.py`) and an end-to-end test
(`tests/smoke_test.py`) that boots the real HTTP server on an ephemeral port and performs the
full client sequence, asserting both the happy path and the specified failure modes. Passing
57 checks is our evidence that the transport works.

**Residual risk, stated plainly**

Self-verification cannot prove compatibility with the real Alexa+ service. Assertions about
its behaviour are limited to what the specification mandates.

**What would help**

A published conformance suite, and a static page describing exactly what the Local Inspector
and Web Simulator check.

---

## 8. Protocol errors versus tool execution errors is easy to miss — P2

**What we did**

First implementation returned `-32602 Invalid params` when a tool argument was missing.

**What we found**

The `2025-11-25` changelog clarifies that **input validation errors must be returned as tool
execution errors, not protocol errors**, so the model can read the message and self-correct
(SEP-1303). A `-32602` response gives the model nothing actionable and ends the turn.

**How we resolved it**

Invalid tool arguments now return a successful JSON-RPC result containing `isError: true`,
a human-readable explanation, and the permitted values — for example `{"supportedPeriods":
["today","yesterday","week","month"]}`. The smoke test asserts this distinction explicitly.

**What would help**

This is a genuinely important behavioural requirement that lives in a changelog line and a
spec section. It deserves prominence in the quickstart, because the difference is invisible
to a server that only tests its happy path.

---

## 9. Version "negotiation" semantics are underspecified — P2

**What we did**

Sent `initialize` with a protocol version the server does not implement.

**What we found**

The specification says the server responds with a version *it* supports, and that the client
decides whether to proceed — but it does not say what a server should do when it supports
several revisions, nor whether a mismatch is a fatal error. We chose: preferred revision
`2025-11-25`, accepted `2025-06-18` and `2025-03-26`, echo the client's version when it is
supported and otherwise answer with `2025-11-25`.

**Why it matters**

A client cannot distinguish "we agreed on your version" from "the server downgraded you and
hopes you notice" without comparing the response against its own request. Our smoke test
asserts the downgrade path, but this is our interpretation, not a specified behaviour.

**What would help**

State explicitly whether the server may answer with a version the client did not request, and
whether a client must abort on mismatch.

---

## What went well

To keep this log honest rather than merely critical:

* The MCP `2025-11-25` specification site is genuinely good — the transports page states the
  `403`-on-bad-`Origin` and `Accept`-header requirements unambiguously, which is why those
  paths are correct here.
* The changelog is a well-organised index of behavioural changes. Entry 8 came from reading
  it, and it changed the design.
* Listing the four tracks and their priority categories together in the announcement made
  track selection fast.
* The friction log bonus itself is a good idea: the entries above are the ones we would
  actually want an engineering team to read.

## Summary for the Alexa+ team

| Theme | Entries | Suggested owner |
|---|---|---|
| Docs served empty to non-browser clients | 1, 4 | Docs platform |
| Normative content missing from rendered pages | 2, 3 | Alexa+ docs |
| Requirements only stated in prose listings | 5 | Devpost / event ops |
| Developer tooling fails silently | 6 | Environment |
| Missing conformance tooling | 7 | Alexa+ developer experience |
| Behavioural rules buried in changelogs | 8, 9 | MCP spec editors |

If only one thing is fixed: **stop returning `202` with an empty body from documentation
URLs.** It converts a clear failure into an invisible one, and it caused three of the nine
entries above.
