# Submission checklist and 18-day execution plan

Today is **2026-10-05**. The deadline is **2026-10-23 12:00 PDT**, which is
**2026-10-24 03:00 Beijing time** — you have **18 days**.

Treat the real deadline as **2026-10-23 midday Beijing time** and submit a day early.

---

## Part 1 — Devpost submission checklist

Work top to bottom. Everything here corresponds to a field or requirement in the
submission form.

### Required

- [ ] **Project name** — `Home Energy Copilot — an Alexa+ MCP add-on`
- [ ] **Text description** — from `docs/DEVPOST_SUBMISSION.md`
- [ ] **Public GitHub repository** containing all source, assets, and run instructions
- [ ] **Open-source license visible at the top of the repo** — this means the repo **About**
      sidebar, not just a `LICENSE` file. Verify by opening the repo while logged out.
- [ ] **Demo video under 3 minutes** — recorded from `docs/VIDEO_SCRIPT.md`
- [ ] **Video is publicly viewable** — open the link in a private window. *A private video
      scores zero and this is the single most common fatal mistake.*
- [ ] **The repo actually calls the track's required technology in code.** For Alexa+ this
      means a real MCP entry point, import, or loaded configuration — **not a README
      mention**. Ours is `alexa_mcp/server.py` plus `alexa_mcp/__main__.py`.
- [ ] **Product feedback / friction log** — `friction-log/FRICTION_LOG.md` (worth up to
      **+10%** on the final score)
- [ ] **Track selected on the submission form:** Alexa+
- [ ] **Mini challenge selected:** AWS Builder
- [ ] **Mini challenge selected:** Open Source

### For the Open Source mini-challenge

The rules require all four of these, and omit any one and the entry does not qualify:

- [ ] Contribution URL
- [ ] Repository URL
- [ ] Your GitHub username
- [ ] A short description of what you did, how it works, and why it matters

A pull request does **not** need to be merged — a branch or an unmerged fork counts.

### For the AWS Builder mini-challenge

- [ ] Use at least one AWS service in the project with **documented integration**:
      Bedrock, AgentCore, Strands SDK, SageMaker, or Kiro Crew.
      *Using only Kiro Crew qualifies on its own.*
- [ ] The integration is described in the README, not only in the code.

### Before you hit submit

- [ ] `python tests/smoke_test.py` → **57 passed, 0 failed** on a clean clone
- [ ] A fresh clone runs with `python -m alexa_mcp` and **no install step**
- [ ] All `<PLACEHOLDER>` markers replaced — search the repo:
      `grep -rn "<YOUR\|<PLACEHOLDER" .`
- [ ] Repo About section shows the license and the description
- [ ] No secrets, no real household data, no personal files committed
- [ ] Every field on the Devpost form has been re-read once, slowly
- [ ] **Submitted at least 24 hours before the deadline**

### Highest-risk items, ranked

| Risk | Why it kills the entry | Mitigation |
|---|---|---|
| Video is private or over 3 minutes | Automatic zero on a scored criterion | Test in a private window; keep to 2:50 |
| License not visible in the About section | The rules call this out explicitly | Set it in the repo sidebar, then check logged out |
| Track technology only mentioned in README | The rules say a mention does not count | Point judges at `server.py` in the description |
| Submitted in the final hour | Devpost is slow under load; a late entry is not judged | Submit 10-22, not 10-23 |
| Eligibility not confirmed | Prize cannot be awarded to an ineligible resident | See Part 3 below |

---

## Part 2 — 18-day plan

### Phase 1 · Days 1–3 (10-06 → 10-08) — Foundation

- [ ] **Day 1:** Read the Devpost rules page *logged in, in a browser* and confirm the
      eligibility section, the exact submission fields, and the stated prize breakdown.
      Cross-check against what is written in this repo.
- [ ] **Day 1:** Publish the repo to GitHub. Public, MIT license in the About section.
      An empty repo published early is worth more than a perfect repo published on day 16.
- [ ] **Day 2:** Join the official Discord and check the office-hours schedule. Ask one real
      question — the answer is free and the friction log gets an entry.
- [ ] **Day 2:** Verify in the **Alexa+ Web Simulator** that your environment can reach the
      Alexa+ developer tooling at all. Do this now, not on day 14.
- [ ] **Day 3:** Deploy the container somewhere reachable (Fargate, App Runner, or a tunnel).
      This is the step most likely to eat a week. **Do it early.**

**Exit criteria:** public repo, running code, a reachable endpoint.

### Phase 2 · Days 4–9 (10-09 → 10-14) — Depth

- [ ] **Day 4–5:** Wire **Amazon Bedrock** into the `speech` field so responses are phrased
      per customer, with the MCP server remaining authoritative for every number. This
      earns the AWS Builder mini-challenge.
- [ ] **Day 5:** Write the Bedrock integration into the README with a diagram. Undocumented
      integrations do not count for AWS Builder.
- [ ] **Day 6–7:** Open the **Open Source** contribution. Pick a real repository that this
      work touched, make the contribution, and record the URL, the branch, your username,
      and the description **immediately**. Do not leave this to the last week.
- [ ] **Day 8–9:** Add one genuinely differentiating capability. Ambitious candidates:
      tariff-aware scheduling, multi-home support, or an anomaly detector that flags an
      unusual spike without being asked.

**Exit criteria:** AWS integration documented, open-source PR open, one differentiator
working.

### Phase 3 · Days 10–13 (10-15 → 10-18) — Hardening

- [ ] **Day 10:** Extend `tests/smoke_test.py` to cover the new capability. A judge running
      the test sees your confidence.
- [ ] **Day 11:** Add the architecture diagram and the judge quick-verify block to the README.
- [ ] **Day 12:** Accessibility and wording pass. Read every `speech` string aloud. If it
      sounds like a database row, rewrite it.
- [ ] **Day 13:** Freeze features. From here on, only bug fixes and documentation.

**Exit criteria:** features frozen, tests green, README complete.

### Phase 4 · Days 14–16 (10-19 → 10-21) — Submission assets

- [ ] **Day 14:** Fill in `docs/DEVPOST_SUBMISSION.md` completely. Replace every placeholder.
- [ ] **Day 15:** Record the video. Budget **three takes** and expect the first to be
      unusable. Burn in captions.
- [ ] **Day 16:** Edit, upload, and **verify the video in a private browser window.** Then do
      the full checklist in Part 1.

**Exit criteria:** video public and verified, description final.

### Phase 5 · Days 17–18 (10-22 → 10-23) — Submit and stop

- [ ] **Day 17 (10-22):** Submit. Re-read every field once. Then confirm the form shows
      "submitted" and take a screenshot.
- [ ] **Day 17:** Post in the hackathon Discord that you submitted, with the repo link. Real
      feedback from other participants is worth more than another day of polish.
- [ ] **Day 18 (10-23):** Do not touch code. Verify the video is still public. If you find a
      typo in the description, fix that and nothing else.

**Hard rule:** no commits on 10-23. A broken commit in the final 24 hours is the most
avoidable way to lose a prize.

---

## Part 3 — Eligibility: what you must confirm yourself

This is the one item we could not verify for you, because the Devpost rules page returns an
empty body to non-browser clients (see `friction-log/FRICTION_LOG.md` entries 1 and 4).

**Confirm all three in a browser, logged in, on the rules page:**

1. **Eligibility section.** Devpost's standard global-hackathon exclusions are Brazil,
   Quebec, Cuba, Iran, North Korea, Crimea, Russia, and other OFAC-designated regions.
   Mainland China is **not** on that standard list — but the *sponsor's* rules override it.
   Read the actual Eligibility paragraph for this event.
2. **Age requirement.** The published requirement is being above the legal age of majority
   in your country of residence.
3. **Prize mechanics.** How the prize is paid, and what documentation is needed to receive
   it. If you cannot supply what is required, an otherwise winning entry cannot be awarded.

Also confirm that your Amazon Developer account and AWS account can actually reach the
Alexa+ Preview tooling and Bedrock **from your location**. Verify this on day 2, not day 14 —
if there is a regional restriction, you need time to plan around it.

---

## Part 4 — Immediate next actions

Three things, in this order, today and tomorrow:

1. **Publish this repo to GitHub.** Add the MIT license in the About sidebar. Do it now,
   while the code is small and the pressure is zero.
2. **Read the rules page in a browser** and settle Part 3.
3. **Run the judge quick-verify block** on a clean clone, so you know it works for someone
   who is not you:

```bash
git clone <YOUR REPO URL> && cd home-energy-copilot
python -m alexa_mcp --describe      # 7 tools, no install needed
python tests/smoke_test.py          # 57 passed, 0 failed
python scripts/demo_transcript.py   # the full conversation, turn by turn
```

Then start Phase 1, Day 3: get the container reachable. Everything else gets easier once
that is done.
