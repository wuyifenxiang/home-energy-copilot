# Demo video script — under 3 minutes

Hard limit is **3 minutes**. This script runs **2:50** at a measured pace, which leaves
10 seconds of headroom. Do not plan to the limit; Devpost cuts nothing and judges notice.

## Rules for this recording

1. **Show the product working.** Judges score working demos, not slides. The terminal and
   the browser must be doing real things on camera.
2. **No fake speed.** Record real tool calls. If a turn takes two seconds, let it.
3. **One idea per shot.** Say one thing, show one thing.
4. **Record the voiceover separately** and lay it over the screen capture. Live narration
   while clicking always sounds rushed.
5. **Re-record the whole thing if a take is bad.** Splicing mid-sentence audio is audible.

## Pre-recording checklist

- [ ] `python tests/smoke_test.py` passes: **57 passed, 0 failed**
- [ ] Terminal font size at least 16pt, dark theme, window maximised
- [ ] `data/home.db` deleted so the demo home seeds identically on camera
- [ ] Peak window forced for the waste demo:
      `$env:ALEXA_MCP_PEAK_WINDOW="00:00-00:00"` (PowerShell) or
      `export ALEXA_MCP_PEAK_WINDOW="00:00-00:00"` (bash)
- [ ] `python -m alexa_mcp` already running in one terminal pane
- [ ] Notifications silenced; tabs closed; no personal data on screen
- [ ] 1920x1080 canvas, 30fps minimum, cursor highlighting on
- [ ] Audio levels checked; no room echo

---

## Shot list

### Shot 1 — The problem (0:00 – 0:14) · 14s

**On screen:** A smart speaker on a kitchen counter. Then cut to a monthly utility bill
graph with one bar spiking.

**Voiceover:**
> "Your smart speaker can turn off a light. Ask it *why* your power bill jumped and you get
> nothing — because the answer needs your history, a ranking, and an action, all in one
> turn. That is what we built."

**Why:** Establishes the gap in 14 seconds. Judges decide in the first 20 seconds whether
this is a real problem.

---

### Shot 2 — What it is (0:14 – 0:26) · 12s

**On screen:** Cut to the terminal. Show the server starting, with the endpoint line and the
7 tool names visible.

**Type on screen (large, as a title card over the terminal):**
> Home Energy Copilot — a self-hosted MCP server for Alexa+
> Protocol 2025-11-25 · Streamable HTTP · zero dependencies

**Voiceover:**
> "This is a self-hosted MCP server — the integration surface Alexa+ actually requires. Seven
> tools, implementing protocol revision 2025-11-25 over Streamable HTTP, using only the
> Python standard library."

---

### Shot 3 — Proof it works (0:26 – 0:44) · 18s

**On screen:** Run the smoke test. Let the PASS lines scroll. Do not cut the scroll short.
Hold 4 seconds on the final counter line.

```bash
python tests/smoke_test.py
```

**Voiceover:**
> "Before anything else, proof. This starts a real HTTP server and drives the full MCP
> client sequence — initialize, capability negotiation, tool discovery, tool calls. It also
> asserts the failure modes: a bad Origin header returns 403 to block DNS rebinding, an
> expired session returns 404, and malformed arguments come back as tool errors the model can
> recover from. Fifty-seven checks, zero failures."

**On screen (lower third):**
> 57 checks · 0 failures
> Origin 403 · Session 404 · Tool errors recoverable

**Why this shot early:** It answers "does it actually run" before asking for belief.

---

### Shot 4 — The conversation (0:44 – 1:46) · 62s

**On screen:** Split view. Left: the terminal running
`python scripts/demo_transcript.py`. Right: a simple browser panel showing the `display`
field.

**Voiceover (over the status turn):**
> "Now the actual product. A customer asks what is running right now."

**Hold on screen 2s so the answer is readable.**

> **Customer:** What is running in my house right now?
> **Alexa+:** Six of twelve devices are on, drawing about 8,360 watts. It is peak pricing
> until 21:00, and the space heater and the living room AC could wait until later to save
> money.

**Voiceover:**
> "Six devices, the live load, and — the part that matters — which of them could wait. Then
> the question people actually ask."

**Let the energy report turn render fully. Hold 3s.**

> **Customer:** How much energy did we use today?
> **Alexa+ (screen):** Total 31.98 kWh · Cost USD 9.91 · Dryer 16.8% · Thermostat 13.8% …

**Voiceover:**
> "A real breakdown. And notice the numbers are measured from fourteen days of hourly
> samples — not invented."

**Let the waste turn render.**

> **Customer:** Are we wasting power?
> **Alexa+:** I found 3 things worth changing, about 2,600 watts…

**Voiceover:**
> "Then it ranks what is worth changing."

---

### Shot 5 — The money shot: propose, confirm, done (1:46 – 2:24) · 38s

**On screen:** This is the most important 38 seconds. Do not talk over it. Let the three
turns land with a beat between each.

> **Customer:** How can I lower my bill?
> **Alexa+:** I have 1 suggestion worth about USD 13.88 a month. Top one: put oven on an
> off-peak schedule. Should I set it up?
>
> **Customer:** Tell me what that would do.
> **Alexa+:** This would change 1 thing and save about USD 13.88 a month. Shall I go ahead?
> *— and the screen shows: Oven: Scheduled between 22:00 and 06:00 **(not yet applied)***
>
> **Customer:** Go ahead.
> **Alexa+:** Done. I applied 1 change, saving roughly USD 13.88 a month.

**Voiceover (after the third turn, calm and deliberate):**
> "Watch the number. Thirteen dollars eighty-eight — the same figure in all three turns,
> because the recommendation, the preview, and the confirmation share one calculation.
>
> And nothing changed until the customer said yes. Every write in this server is two-phase.
> A voice assistant that silently rewires your house is not a feature."

**On screen (lower third):**
> Propose → confirm → act
> One calculation · one number

---

### Shot 6 — Engineering honesty (2:24 – 2:40) · 16s

**On screen:** Open `friction-log/FRICTION_LOG.md` and scroll to entry 1, showing:

```
HTTP/2 202
content-type: text/html; charset=utf-8
content-length: 0
```

**Voiceover:**
> "One more thing. The Alexa+ MCP documentation returned an empty body to every
> non-browser client — a two-oh-two, with zero bytes. We wrote up that and eight other
> findings with the raw commands and output. It is in the repo, and it is the friction log
> the hackathon asks for."

**Why:** The friction log is worth up to 10% and almost nobody submits a real one. Showing
the raw evidence proves it is genuine.

---

### Shot 7 — What's next (2:40 – 2:50) · 10s

**On screen:** An AWS architecture diagram: MCP server in a container on **ECS Fargate**
behind an **ALB**, calling **Amazon Bedrock** for phrasing, with **AgentCore** for session
memory.

**Voiceover:**
> "Next: this container on Fargate behind a TLS load balancer, Bedrock phrasing the responses
> while the MCP server stays authoritative for every number — so a hallucination can never
> become a wrong bill. Code and friction log are in the repo. Thanks."

**End card (hold 2s):**
> Home Energy Copilot · Alexa+ MCP add-on
> github.com/`<YOUR USERNAME>`/home-energy-copilot

---

## Post-production

- **Captions:** Burn in subtitles. Around a third of judges watch muted, and accented speech
  is easier to follow with text.
- **Audio:** Normalise to about −16 LUFS. Voiceover at least 6 dB above the terminal.
- **Pace:** If the edit lands over 3:00, cut Shot 4's energy report hold first, then shorten
  Shot 6. **Never cut Shot 5.**
- **Export:** 1080p H.264, and confirm the upload is public or unlisted-and-viewable before
  pasting the link into Devpost. A private video scores zero.

## Timing summary

| Shot | Content | Duration | Cumulative |
|---|---|---|---|
| 1 | The problem | 0:14 | 0:14 |
| 2 | What it is | 0:12 | 0:26 |
| 3 | Proof: 57 checks | 0:18 | 0:44 |
| 4 | The conversation | 1:02 | 1:46 |
| 5 | Propose → confirm → act | 0:38 | 2:24 |
| 6 | Friction log evidence | 0:16 | 2:40 |
| 7 | What's next | 0:10 | 2:50 |

**Total 2:50 — 10 seconds of headroom under the 3-minute limit.**
