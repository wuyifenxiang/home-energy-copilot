# Devpost submission copy

Paste-ready text for the three free-text Devpost fields. Trim to fit the character limits;
the opening paragraph is written to survive truncation.

---

## Project name

**Home Energy Copilot — an Alexa+ MCP add-on**

Tagline (170 characters):

> A self-hosted MCP server that lets Alexa+ explain your home's energy use and then fix it — propose, confirm, done.

---

## Inspiration

Smart speakers can turn a light off. They cannot tell you *why* your bill is high, *what* is
causing it, and *what to change first* — because answering that needs history, ranking, and
an action in a single turn.

We had 14 days of hourly energy samples sitting in a home automation database and no way to
talk to them. Alexa+ add-ons are a natural fit for exactly this: a conversation is a better
interface than a dashboard when the answer is "your water heater, and you should shift it
after 22:00."

## What it does

Home Energy Copilot is a **self-hosted MCP server** that exposes seven voice-first tools to
Alexa+:

**Read-only — it explains:**
- `get_home_status` — "What is running right now?" (6 of 12 devices, 8,360 W, and which
  flexible load could wait)
- `get_energy_report` — "How much did we use today?" broken down by device or room, with
  cost and a budget comparison
- `find_energy_waste` — "Are we wasting power?" ranking flexible loads running during peak
  tariff hours
- `recommend_energy_actions` — "How do I lower my bill?" returning a ranked plan with
  **measured** monthly savings per action
- `list_automations` — which routines exist and which are switched off

**State-changing — it acts, in two phases:**
- `set_device_state` — "Turn off the living room AC" (resolves room names and device names
  the way a person says them, and reports honestly when nothing changed)
- `apply_energy_plan` — previews the exact changes first, and only acts when the model passes
  `confirm: true`

A real exchange:

> **Customer:** How can I lower my bill?
> **Alexa+:** I have 1 suggestion worth about USD 13.88 a month. Top one: put oven on an
> off-peak schedule. Should I set it up?
> **Customer:** Go ahead.
> **Alexa+:** Done. I applied 1 change, saving roughly USD 13.88 a month.

## How we built it

**Protocol layer.** We implemented MCP revision `2025-11-25` over **Streamable HTTP** —
one endpoint serving both `POST` and `GET` — directly against the specification, in the
Python standard library. No SDK, no third-party package, no install step:

```
$ python tests/smoke_test.py
57 passed, 0 failed
```

We did not do this because it was easier. `pip` hung indefinitely against PyPI with no error
and no timeout (friction log entry 6), so the official SDK was unavailable. Keeping the
dependency out turned out to be a feature: the repo runs on a fresh machine with `python -m
alexa_mcp` and nothing else.

Implementing the transport ourselves meant getting the details right rather than approximately
right:
- `Origin` is validated on every connection; an unexpected `Origin` gets **403**, which is
  what blocks DNS rebinding
- `Accept` must list both `application/json` and `text/event-stream`, or the request is
  rejected with **406** so clients fail loudly instead of silently
- Sessions are issued as `Mcp-Session-Id`; unknown sessions get **404** so the client
  re-initializes
- Invalid tool arguments return a **tool execution error** (`isError: true`), never a
  protocol error, so the model can read the permitted values and correct itself mid-turn

**Domain layer.** SQLite stores devices, rooms, automations, and 14 days of hourly energy
samples. The savings engine derives every figure from those samples rather than from a
constant, and `recommend_energy_actions` and `apply_energy_plan` share one calculation — so
the number the customer hears is the same number the preview quotes and the same number the
confirmation reports. The smoke test asserts that equality.

**Voice-first design.** We treated the spoken response as the primary output, not the JSON.
Each tool returns `speech` (short, markup-free, pronounceable), `display` (readable on a
screen), and `data` (for follow-up turns), and every tool answers a question a person would
actually say out loud. Money is never spoken with more than two decimals.

**Realistic simulation.** Our first seed data claimed the home used 231 kWh a day, because
we modelled every device at nameplate watts for 24 hours straight. We rewrote it with
per-device duty cycles and household routines — the oven only during meal windows, cooling
in the afternoon and evening, nothing at 3am — landing at a believable 32 kWh/day.

**Chained demo.** `scripts/demo_transcript.py` feeds the action id that
`recommend_energy_actions` actually returned into `apply_energy_plan`, so the transcript
cannot drift out of sync with the tool surface the way a hard-coded script would.

## Challenges we ran into

**1. The official docs returned nothing.** Every `curl` against the Alexa+ MCP toolkit
quickstart returned **HTTP 202 with a zero-length body** — success code, empty content. The
English pages rendered navigation and stopped before the body. We built the server from the
MCP specification instead, and wrote up all nine findings in `friction-log/FRICTION_LOG.md`.

**2. No conformance client exists.** We could not confirm what the Local Inspector and Web
Simulator validate, so we wrote our own client and a 57-check end-to-end suite that boots the
real server on an ephemeral port and exercises the full `initialize` → `notifications/initialized`
→ `tools/list` → `tools/call` sequence, including the specified failure modes.

**3. One number, three places.** Our preview quoted USD 3.50/month while the recommendation
that produced it said USD 13.88/month. A customer hearing both would be right to distrust
both. Fixed by extracting one `saving_estimate` function used by every path.

**4. Peak-hour tools that do nothing off-peak.** `find_energy_waste` returned zero findings
whenever a demo was recorded outside 17:00–21:00. We added `ALEXA_MCP_PEAK_WINDOW`, so a demo
can deterministically exercise the load-shifting path at any hour.

**5. Honest failure is a feature.** An early version of `set_device_state` reported success
when the device was already in the requested state. It now reports "was already off" and
`changed: false`. A voice assistant that claims to have done something it did not is worse
than one that admits it did nothing.

## Accomplishments we're proud of

- **57/57 end-to-end checks pass** against a real HTTP server, covering both the happy path
  and the security and session failure modes the specification calls out.
- **Zero runtime dependencies**, so the submission runs anywhere Python 3.11+ exists.
- **Measured savings, not invented ones** — and identical across recommendation, preview, and
  confirmation.
- **Every write is two-phase.** The assistant cannot silently rewire a house.
- **A friction log with reproducible evidence**, including the raw `202` with
  `content-length: 0` that started it.

## What we learned

- Returning a success status with an empty body is worse than returning an error. It converts
  a clear failure into an invisible one, and it cost us three separate investigations.
- The distinction between protocol errors and tool execution errors is the difference between
  a conversation that recovers and one that dead-ends. We only found it by reading the
  changelog.
- Voice output needs different constraints from text output. The first version of our status
  response ran to four sentences; it is now under 240 characters, because a person cannot
  skim a spoken answer.
- If two code paths can report the same number, they will eventually disagree. Share the
  calculation.

## What's next

- Deploy to **ECS Fargate behind an ALB with TLS** and register the endpoint with Alexa+ in
  the Web Simulator.
- Use **Amazon Bedrock** to phrase `speech` per customer, with the MCP server staying
  authoritative for every number so a hallucination cannot become a wrong bill.
- **AgentCore** for session memory across conversations.
- Real device integrations behind the existing `set_device_state` contract.
- Tariff-aware scheduling to replace the fixed two-window peak model.

## Built with

`python` · `sqlite` · `mcp` (protocol revision 2025-11-25) · `streamable-http` ·
`server-sent-events` · `json-schema-2020-12` · `docker` · `alexa-plus`

---

## Built with tags

```
python, sqlite, mcp, model-context-protocol, streamable-http, server-sent-events,
json-schema, alexa, alexa-plus, aws, docker, smart-home, energy-monitoring
```

---

## Links to include on the submission

| Field | Value |
|---|---|
| GitHub repository | `<YOUR REPO URL>` |
| Demo video (under 3 minutes) | `<YOUR VIDEO URL>` |
| Open source contribution URL | `<YOUR PR OR FORK URL>` |
| GitHub username | `<YOUR GITHUB USERNAME>` |

---

## Track and mini-challenge selection

| Field | Selection |
|---|---|
| Primary track | **Alexa+** |
| Mini challenge | **AWS Builder** |
| Mini challenge | **Open Source** |
| Friction log | `friction-log/FRICTION_LOG.md` (submitted for the +10% bonus) |
| Protocol revision | `2025-11-25` |
| Transport | Streamable HTTP |

## Judge quick-verify (30 seconds)

```bash
git clone <YOUR REPO URL> && cd home-energy-copilot
python -m alexa_mcp --describe      # 7 tools, no install needed
python tests/smoke_test.py          # 57 passed, 0 failed
python scripts/demo_transcript.py   # the full conversation, turn by turn
```
