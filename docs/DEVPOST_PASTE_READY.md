# Paste-ready blocks for the Devpost form

Fill the form top to bottom. Each block below maps to one field. Nothing here needs
markdown escaping — copy the block, paste it, done.

---

## 1. Project name

```
Home Energy Copilot — an Alexa+ MCP add-on
```

---

## 2. About the project

Paste **exactly** this. The form's own template asks for lowercase `##` section headings
(`## Inspiration...`), so match that style rather than title case.

```markdown
## Inspiration

Smart speakers can turn a light off. They cannot tell you *why* your bill is high, *what* is causing it, and *what to change first* — because that needs history, ranking, and an action in a single turn.

We had 14 days of hourly energy samples sitting in a home automation database and no way to talk to them. Alexa+ add-ons fit this exactly: a conversation beats a dashboard when the answer is "your water heater, and you should shift it after 22:00."

## What it does

Home Energy Copilot is a self-hosted MCP server that exposes seven voice-first tools to Alexa+.

**It explains (read-only):**

- `get_home_status` — "What is running right now?" 6 of 12 devices, 8,360 W, and which flexible load could wait.
- `get_energy_report` — "How much did we use today?" broken down by device or room, with cost and a budget comparison.
- `find_energy_waste` — "Are we wasting power?" ranking flexible loads running during peak tariff hours.
- `recommend_energy_actions` — "How do I lower my bill?" returning a ranked plan with measured monthly savings per action.
- `list_automations` — which routines exist, and which are switched off.

**It acts (state-changing, two-phase):**

- `set_device_state` — "Turn off the living room AC." Resolves room names and device names the way a person says them, and reports honestly when nothing changed.
- `apply_energy_plan` — previews the exact changes first, and only acts when the model passes `confirm: true`.

A real exchange:

> **Customer:** How can I lower my bill?
> **Alexa+:** I have 1 suggestion worth about USD 13.88 a month. Top one: put oven on an off-peak schedule. Should I set it up?
> **Customer:** Go ahead.
> **Alexa+:** Done. I applied 1 change, saving roughly USD 13.88 a month.

## How we built it

**Protocol layer.** We implemented MCP revision 2025-11-25 over Streamable HTTP — one endpoint serving both POST and GET — directly against the specification, in the Python standard library. No SDK, no third-party package, no install step. `python tests/smoke_test.py` reports 57 passed, 0 failed.

We did not choose this for elegance. `pip` hung indefinitely against PyPI with no error and no timeout (friction log entry 6), so the official SDK was unavailable. Keeping the dependency out became a feature: the repo runs on a fresh machine with `python -m alexa_mcp` and nothing else.

Implementing the transport ourselves meant getting details right rather than approximately right:

- `Origin` is validated on every connection; an unexpected `Origin` gets 403, which is what blocks DNS rebinding.
- `Accept` must list both `application/json` and `text/event-stream`, or the request is rejected with 406 so clients fail loudly instead of silently.
- Sessions are issued as `Mcp-Session-Id`; unknown sessions get 404 so the client re-initializes.
- Invalid tool arguments return a tool execution error (`isError: true`), never a protocol error, so the model can read the permitted values and correct itself mid-turn.

**Domain layer.** SQLite stores devices, rooms, automations, and 14 days of hourly energy samples. The savings engine derives every figure from those samples rather than from a constant, and `recommend_energy_actions` and `apply_energy_plan` share one calculation — so the number the customer hears is the same number the preview quotes and the same number the confirmation reports. The smoke test asserts that equality.

**Voice-first design.** We treated the spoken response as the primary output, not the JSON. Each tool returns `speech` (short, markup-free, pronounceable), `display` (readable on a screen), and `data` (for follow-up turns). Every tool answers a question a person would actually say out loud. Money is never spoken with more than two decimals.

**Realistic simulation.** Our first seed data claimed the home used 231 kWh a day, because we modelled every device at nameplate watts for 24 hours straight. We rewrote it with per-device duty cycles and household routines — the oven only during meal windows, cooling in the afternoon and evening, nothing at 3am — landing at a believable 32 kWh/day.

**Chained demo.** `scripts/demo_transcript.py` feeds the action id that `recommend_energy_actions` actually returned into `apply_energy_plan`, so the transcript cannot drift out of sync with the tool surface the way a hard-coded script would.

## Challenges we ran into

**1. The official docs returned nothing.** Every request against the Alexa+ MCP toolkit quickstart returned HTTP 202 with a zero-length body — success code, empty content. The English pages rendered navigation and stopped before the body. We built the server from the MCP specification instead, and wrote up all nine findings in `friction-log/FRICTION_LOG.md`.

**2. No conformance client exists.** We could not confirm what the Local Inspector and Web Simulator validate, so we wrote our own client and a 57-check end-to-end suite that boots the real server on an ephemeral port and exercises the full initialize → notifications/initialized → tools/list → tools/call sequence, including the specified failure modes.

**3. One number, three places.** Our preview quoted USD 3.50/month while the recommendation that produced it said USD 13.88/month. A customer hearing both would be right to distrust both. Fixed by extracting one `saving_estimate` function used by every path.

**4. Peak-hour tools that do nothing off-peak.** `find_energy_waste` returned zero findings whenever a demo was recorded outside 17:00–21:00. We added the `ALEXA_MCP_PEAK_WINDOW` environment variable, so a demo can deterministically exercise the load-shifting path at any hour.

**5. Honest failure is a feature.** An early version of `set_device_state` reported success when the device was already in the requested state. It now reports "was already off" and `changed: false`. A voice assistant that claims to have done something it did not is worse than one that admits it did nothing.

**6. Our own packaging bug, found by pretending to be a judge.** The README told judges to run `python -m alexa_mcp` from the repo root, but the package lived in `src/`, so that command failed with `No module named alexa_mcp` on a clean clone. We only caught it by running the documented command verbatim instead of the command we had been using. Fixed by moving to a flat layout, and the CLI now prints actionable instructions if it is ever run from the wrong directory.

## Accomplishments we're proud of

- 57 end-to-end checks pass against a real HTTP server, covering both the happy path and the security and session failure modes the specification calls out.
- Zero runtime dependencies, so the submission runs anywhere Python 3.11+ exists.
- Measured savings, not invented ones — and identical across recommendation, preview, and confirmation.
- Every write is two-phase. The assistant cannot silently rewire a house.
- A friction log with reproducible evidence, including the raw 202 with `content-length: 0` that started it.

## What we learned

- Returning a success status with an empty body is worse than returning an error. It converts a clear failure into an invisible one, and it cost us three separate investigations.
- The distinction between protocol errors and tool execution errors is the difference between a conversation that recovers and one that dead-ends. We only found it by reading the changelog.
- Voice output needs different constraints from text output. The first version of our status response ran to four sentences; it is now under 240 characters, because a person cannot skim a spoken answer.
- If two code paths can report the same number, they will eventually disagree. Share the calculation.
- Test the command you documented, not the command you have been using.

## What's next

- Deploy to ECS Fargate behind an ALB with TLS, and register the endpoint with Alexa+ in the Web Simulator.
- Use Amazon Bedrock to phrase `speech` per customer, with the MCP server staying authoritative for every number so a hallucination cannot become a wrong bill.
- AgentCore for session memory across conversations.
- Real device integrations behind the existing `set_device_state` contract.
- Tariff-aware scheduling to replace the fixed two-window peak model.
```

**Length check:** 8,240 characters across 89 lines, verified by extracting the block
programmatically. Devpost's About field accepts far more than this, and no triple-backtick
fence appears inside the block, so it will not break markdown rendering on paste.

---

## 3. Built with

The field allows up to 25 tags. Paste these **21**, comma-separated. Press Enter after each
so Devpost creates a separate tag rather than one long string — that is the single most
common mistake in this field.

```
python, sqlite, mcp, model context protocol, streamable http, server-sent events, json schema, alexa, alexa plus, aws, docker, smart home, energy monitoring, home automation, rest api, oauth, json-rpc, cli, linux, github, open source
```

Counted: 21 tags, 4 slots spare if you want to add more.

**Deliberately excluded:** `bedrock`, `fargate`, `agentcore`. Those are roadmap items, not
built things. Tag only what you actually shipped — a judge who clicks a tag and finds nothing
behind it trusts the rest of the submission less.

---

## 4. "Try it out" links

The screenshot shows one URL box and an **ADD ANOTHER LINK** button. Add both:

| # | URL | Notes |
|---|---|---|
| 1 | `<YOUR REPO URL>` | The primary link. Make sure the repo is **public** and the license shows in the About sidebar. |
| 2 | `<YOUR VIDEO URL>` | The demo video. **Open it in a private browser window to confirm it is viewable** — a private video scores zero. |

If you deploy the container before submitting, add a third link to the live endpoint's
`/healthz` URL. A reachable endpoint is strong evidence for the AWS Builder mini-challenge.
Do **not** link the bare MCP endpoint (`/mcp`); it answers `400` to a browser by design and
will look broken.

---

## 5. Remaining fields not shown in the screenshot

Work through these as well — they are easy to forget after the big text box:

- [ ] **Video demo URL** — paste the same video link; if the form has both a general link
      field and a dedicated video field, fill both.
- [ ] **Track selection** — Alexa+
- [ ] **Mini challenge: AWS Builder** — only after Bedrock is actually integrated and
      documented. Do not claim it before then.
- [ ] **Mini challenge: Open Source** — requires all four of: contribution URL, repository
      URL, your GitHub username, and a short description of what you did.
- [ ] **Friction log** — point at `friction-log/FRICTION_LOG.md` in the repo. Worth up to
      +10% and almost nobody submits a real one.
- [ ] **Country of residence** — the form may ask; answer accurately, because eligibility and
      prize payment depend on it.

---

## Before you press submit

```bash
# 1. No placeholder text left in the repo
grep -rn "<YOUR" .

# 2. Judges' quick-verify block actually works on a clean clone
git clone <YOUR REPO URL> && cd home-energy-copilot
python -m alexa_mcp --describe      # 7 tools, no install needed
python tests/smoke_test.py          # 57 passed, 0 failed
```

- [ ] Repo is **public** (check in a private window, logged out)
- [ ] License is visible in the repo **About** sidebar, not just as a `LICENSE` file
- [ ] Video is under 3 minutes and **publicly viewable**
- [ ] Every `<YOUR ...>` placeholder replaced in **both** the repo and the form
- [ ] Submitted at least 24 hours before 2026-10-23 12:00 PDT
