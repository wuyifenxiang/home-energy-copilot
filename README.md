# Home Energy Copilot — an Alexa+ MCP add-on

A **self-hosted Model Context Protocol server** that lets Alexa+ answer real questions
about a home's energy use and then *act* on them: what is running right now, what this
week cost, what is being wasted, and what to change first.

Built for **Build, Ship, Shape: Amazon Developer Hackathon 2026 — Alexa+ track**
(primary track) with the **AWS Builder** and **Open Source** mini-challenges layered on.

| | |
|---|---|
| Protocol revision | `2025-11-25` |
| Transport | Streamable HTTP (single endpoint, `POST` + `GET`) |
| Runtime dependencies | **none** — Python 3.11+ standard library only |
| Tools exposed | 7 |
| Verification | `python tests/smoke_test.py` → 57 checks, 0 failures |
| Also verified | `python tests/test_bedrock.py` → 37 checks, 0 failures, no AWS needed |
| Optional AWS | Amazon Bedrock rephrasing, behind a figure-preservation guard |
| License | MIT |

---

## Why this exists

Voice assistants are good at *reporting* and bad at *reasoning over your own data*. A
customer can ask a smart speaker to turn a device off, but not "why is my bill high, and
what should I change first?" — because that requires reading history, ranking causes, and
proposing an action in one turn.

This server does that, and it is deliberately shaped for a spoken interface:

* **Every tool maps to something a person would actually say out loud.** No
  `query_energy_samples_v2` style APIs.
* **Inputs are flat and enumerated**, so the model cannot hallucinate a malformed call.
* **Results separate what is spoken from what is shown.** `speech` is short and free of
  markup; `display` is readable on a screen; `data` carries follow-up context.
* **Anything that changes the home is two-phase**: propose → confirm. The assistant cannot
  silently rewire a house.
* **Failures are model-recoverable.** Bad arguments return a tool execution error with the
  permitted values, so the assistant fixes itself mid-conversation instead of dead-ending.

## Architecture

```
        Alexa+ service
              │  MCP over Streamable HTTP (POST + GET /mcp)
              ▼
   ┌──────────────────────────────────────────┐
   │  server.py   transport + lifecycle       │
   │    · initialize / session negotiation    │
   │    · Origin validation, HTTP 403         │
   │    · Mcp-Session-Id, HTTP 404 on expiry  │
   │    · SSE response path + polling stream  │
   ├──────────────────────────────────────────┤
   │  registry.py  tool contracts             │
   │    · JSON Schema 2020-12 validation      │
   │    · protocol error vs execution error   │
   ├──────────────────────────────────────────┤
   │  tools.py     the 7 voice-first tools    │
   ├──────────────────────────────────────────┤
   │  store.py     SQLite: devices, hourly    │
   │               samples, automations       │
   └──────────────────────────────────────────┘
```

Nothing in `server.py` or `registry.py` is specific to energy. Swapping `tools.py` and
`store.py` re-targets the whole server at another domain, which is why the protocol layer
is kept apart from the domain layer.

## Quick start

No installation, no virtualenv, no network access required.

```bash
git clone <your-repo-url>
cd home-energy-copilot

# Show the tool surface without starting anything
python -m alexa_mcp --describe

# Start the MCP endpoint on http://127.0.0.1:8765/mcp
python -m alexa_mcp
```

On Windows, use `py` instead of `python` if that is how Python is registered.

The server prints its endpoint, protocol revision, and tool list on startup. State lives in
`data/home.db` (SQLite) and is seeded with a realistic demo home on first run.

### Verify it actually works

```bash
python tests/smoke_test.py
```

This starts the real HTTP server on an ephemeral port and drives it with a
dependency-free MCP client — the same `initialize` → `notifications/initialized` →
`tools/list` → `tools/call` sequence a real client performs. It asserts the happy path
**and** the failure modes the specification calls out:

```
57 passed, 0 failed
```

```bash
python tests/test_bedrock.py
```

```
37 passed, 0 failed
```

This one covers the Amazon Bedrock integration and, more importantly, the guard that
stops it from misreporting a figure. **It needs no AWS account and makes no network
calls** — a stub model is asked to alter, round, and invent numbers, and each attempt
must be rejected.

### See what a conversation looks like

```bash
python scripts/demo_transcript.py
```

This prints, for each turn, the spoken request, the tool that was called, the text Alexa+
would say, the on-screen rendering, and the structured payload. The savings turn is
*chained*: it feeds the action id that `recommend_energy_actions` actually returned into
`apply_energy_plan`, so the script cannot drift out of sync with the tool surface.

## Amazon Bedrock (optional)

Spoken responses can be rephrased by Amazon Bedrock so they do not sound like a form
letter. This is entirely optional: **without credentials the server behaves exactly as
described above**, using the built-in templates.

```bash
export ALEXA_MCP_BEDROCK_MODEL="<model id from the Bedrock console>"
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
python -m alexa_mcp
```

The startup log always states which mode is active, so "Bedrock is working" can never be
confused with "Bedrock silently fell back to templates":

```
INFO alexa_mcp: Amazon Bedrock rewriting: ON (<model-id> in us-east-1)
INFO alexa_mcp: Amazon Bedrock rewriting: off (templates in use; set ... to enable)
```

### Bedrock is never allowed to be the source of a number

This is the design constraint that makes a language model safe to put in front of a
utility bill. Bedrock receives a sentence that **already contains the correct figures**
and may only re-word it. After the model replies, every numeric token in its output is
compared against the original; if anything was rounded, dropped, altered, or invented,
the reply is **discarded** and the template is used instead.

So a hallucination cannot become a wrong bill. It can only become a clumsier sentence.

`tests/test_bedrock.py` proves this offline by driving the rewriter with a stub model that
tries to change `USD 9.91` into `USD 40`, round it to `USD 10`, drop it entirely, and
invent an extra percentage. Every attempt is rejected.

Other properties, all tested:

* **Fail-open.** A network error, timeout, throttling response, or malformed payload falls
  back to the template and is logged at debug level. A cloud failure never surfaces as a
  tool failure, because a voice assistant must not go silent.
* **Cached.** Identical input text is not sent twice, so a repeated question does not
  repeat spend.
* **Zero dependencies.** The Converse API is called over `urllib` with SigV4 signing in
  the standard library, consistent with the rest of the project.
* **Verifiable.** Set `ALEXA_MCP_EXPOSE_STATUS=1` to add a read-only
  `get_integration_status` tool that reports whether Bedrock is live and how many rewrites
  were rejected. It makes no generation call, so checking costs nothing.

See [docs/AWS_DEPLOYMENT.md](docs/AWS_DEPLOYMENT.md) for account setup, including a
billing-safety checklist to do *before* creating any AWS resource.

## The tools

| Tool | Kind | What it answers |
|---|---|---|
| `get_home_status` | read | "What is running right now?" |
| `get_energy_report` | read | "How much did we use today / this week?" |
| `find_energy_waste` | read | "Are we wasting power?" |
| `recommend_energy_actions` | read | "How do I lower my bill?" |
| `list_automations` | read | "What automations do I have?" |
| `set_device_state` | write | "Turn off the living room AC." |
| `apply_energy_plan` | write | "Yes, do it." (propose → confirm) |

Read-only tools carry `annotations.readOnlyHint: true` so a client can reason about
safety before invoking them.

### Two-phase writes

`apply_energy_plan` will not change anything unless `confirm` is explicitly `true`. The
first call is a preview that states exactly what would change and how much it would save:

```
CUSTOMER : How can I lower my bill?
ALEXA    : I have 1 suggestion worth about USD 13.88 a month.
           Top one: put oven on an off-peak schedule. Should I set it up?

CUSTOMER : Tell me what that would do.
-> apply_energy_plan({"action_ids": ["schedule-oven"]})
ALEXA    : This would change 1 thing and save about USD 13.88 a month. Shall I go ahead?

CUSTOMER : Go ahead.
-> apply_energy_plan({"action_ids": ["schedule-oven"], "confirm": true})
ALEXA    : Done. I applied 1 change, saving roughly USD 13.88 a month.
```

The figure is identical in all three turns because both tools call one shared
`measured_daily_kwh` / `saving_estimate` calculation. **Savings are derived from 14 days of
stored hourly samples, not from a constant someone typed in** — and the smoke test asserts
that consistency.

## Configuration

| Flag | Default | Purpose |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. The spec recommends localhost for local servers. |
| `--port` | `8765` | TCP port. |
| `--path` | `/mcp` | MCP endpoint path. |
| `--db` | `data/home.db` | SQLite file, or `:memory:`. |
| `--allowed-origin` | *(none)* | Extra exact `Origin` values to accept. Repeatable. |
| `--describe` | | Print the tool surface and exit. |
| `--no-seed` | | Start with an empty database. |
| `--log-level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

| Environment variable | Default | Purpose |
|---|---|---|
| `ALEXA_MCP_PEAK_WINDOW` | `17:00-21:00` | Peak-tariff window as `HH:MM-HH:MM`. Set it to `00:00-00:00` to force the whole day into peak so the load-shifting tools can be demonstrated at any hour. |

`GET /healthz` returns status, protocol revision, tool names, and session count — useful as
a container health check.

## Transport conformance

Implemented directly against the specification rather than by assumption:

* One endpoint path serving both `POST` and `GET`.
* `Accept` must list **both** `application/json` and `text/event-stream`; anything else is
  rejected with `406` so a misconfigured client fails loudly instead of silently.
* `Origin` is validated on every connection. A present-but-unexpected `Origin` gets
  **`403 Forbidden`**, which is what blocks DNS-rebinding attacks.
* Sessions are issued as `Mcp-Session-Id` during `initialize`. An unknown or expired
  session gets **`404`** so the client knows to re-initialize.
* A JSON-RPC *request* without a session gets **`400`**; a *notification* is accepted with
  **`202 Accepted`** and no body.
* Requests answered over SSE begin with an event-id-bearing empty event so the client can
  resume, and `GET` serves a keep-alive stream for server-initiated notifications.
* Invalid tool input returns a **tool execution error** (`isError: true` inside a successful
  result), never a protocol error, so the model can self-correct.

## Deploying

The server is a single standard-library process, so any container host works.

```bash
docker build -t home-energy-copilot .
docker run -p 8765:8765 -v "$PWD/data:/app/data" home-energy-copilot
```

For the AWS Builder mini-challenge the intended production shape is:

* **Amazon ECS Fargate** (or App Runner) fronted by an **ALB with TLS**, running this image.
* **Amazon Bedrock** for the natural-language summarisation step, so the spoken response is
  phrased for the individual customer rather than a fixed template.
* **AgentCore** for managed agent runtime and session memory across conversations.
* **CloudWatch** for the tool-level metrics that feed the friction log.

The MCP server stays authoritative for the numbers; the model only rewrites the phrasing.
That keeps a hallucination from becoming a wrong bill.

## Security notes

* Binds to `127.0.0.1` by default; the CLI warns if you bind wider.
* `Origin` validation is enforced, not optional.
* The demo home is synthetic. `data/` is gitignored so no real household data is committed.
* Before exposing this beyond localhost, put authentication in front of the endpoint — the
  specification recommends it for all remote connections.

## Roadmap

- [ ] Deploy to Fargate behind an ALB with a TLS listener.
- [ ] Bedrock-backed response phrasing for the `speech` field.
- [ ] Real device integrations behind the existing `set_device_state` contract.
- [ ] Tariff-aware scheduling instead of a fixed two-window peak model.
- [ ] Per-customer tariff ingestion, so cost figures are region-correct.

## License

MIT — see [LICENSE](LICENSE).

Built for the Amazon Developer Hackathon 2026. Alexa, Fire TV, Ring and Bee are trademarks
of Amazon.com, Inc. or its affiliates. This project is not affiliated with or endorsed by
Amazon.
