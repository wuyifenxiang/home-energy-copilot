# AWS deployment guide

Written for someone who has never used AWS. Work top to bottom.

> **Honesty note.** I could not verify current AWS pricing, free-tier limits, or
> the exact model IDs from inside the environment this guide was written in
> (outbound HTTPS was blocked, and the Alexa+ developer docs return an empty body
> to non-browser clients). Every AWS-specific figure below is marked
> **[verify]** — confirm it in the AWS console before relying on it. Everything
> about *this project's* behaviour has been tested and is accurate.

---

## Part 0 — Read this first: the billing warning

**AWS charges real money.** There is a free tier, but it has limits, and the
services in this guide are not all free. A misconfiguration can produce a bill.

Do these three things **before** creating any resource:

1. **Create a budget alert.** AWS Console → search `Budgets` → Create budget →
   Zero-spend budget (or a $1 threshold). Enter your email. This is the single
   most important step and it takes two minutes.
2. **Never commit AWS keys to Git.** Your `.gitignore` already ignores `.env`.
   Keep it that way.
3. **Delete resources when you are done.** Part 5 covers this. An idle container
   service still bills.

If you are not willing to put a card on an AWS account, **skip to Part 2 (the
free tunnel route)**. You can still submit a strong entry: the AWS Builder
mini-challenge is optional.

---

## Part 1 — Do you actually need a cloud deployment?

Be clear about what the judging criteria require:

| What you need | Does it require AWS? |
|---|---|
| A working, demo-ready project | No — it runs locally |
| A public code repository | No — GitHub |
| A demo video under 3 minutes | No — screen recording |
| A self-hosted MCP server | A tunnel counts, and so does a container anywhere |
| The **AWS Builder mini-challenge** | **Yes — a documented AWS integration** |

So AWS buys you exactly one thing: eligibility for one mini-challenge prize.
It is worth doing, but it is not worth a week of frustration or a surprise bill.

---

## Part 2 — Free route: expose it locally (do this today)

This gets you a public HTTPS URL with no AWS account and no cost. You need
`winget`, which your machine already has.

```powershell
winget install --id Cloudflare.cloudflared
```

Then start the server in one window:

```powershell
cd "C:\Users\86185\Desktop\代码\DSH\hackathon-amazon-2026"
python -m alexa_mcp --host 127.0.0.1 --port 8765
```

And in a second window:

```powershell
cloudflared tunnel --url http://127.0.0.1:8765
```

It prints a URL like `https://random-words-1234.trycloudflare.com`. Your MCP
endpoint is that URL plus `/mcp`, and the health check is that URL plus
`/healthz`.

**Open the `/healthz` URL in a browser.** You should see JSON listing the tools.
That is your public proof the server runs.

### The honest limitation

This URL only works while your PC is on, the tunnel is running, and your proxy is
up. **Judges will not be able to reach it days later.**

So: use it as *evidence in the video*, not as your live submission link. Do not
put it in the Devpost "Try it out" field unless you accept that it may be dead at
judging time.

If you record the video now, this is enough. Cloudflare Tunnel also has named
tunnels with a stable hostname, but those need a Cloudflare account and a domain
— extra steps for a link that still dies when your PC sleeps.

---

## Part 3 — Connect Amazon Bedrock (the AWS Builder requirement)

This is the integration that earns the mini-challenge, and **the code is already
written and tested**. You only need credentials and a model ID.

### 3.1 Create the AWS account

1. Go to https://aws.amazon.com/ and choose **Create an AWS Account**.
2. You need an email and a payment card. **[verify]** Whether your card is
   accepted depends on your region; some cards are declined for new accounts.
3. Choose the **Basic (free) support plan** — do not pick a paid plan.
4. Set up the budget alert from Part 0 immediately.

### 3.2 Enable model access

Bedrock does not work until you explicitly request access to a model:

1. AWS Console → search `Bedrock` → open **Amazon Bedrock**.
2. Left menu → **Model access** → **Modify model access**.
3. Request access to a small, cheap text model. Anthropic Claude Haiku, Amazon
   Nova Lite, or Amazon Titan Text are the usual choices. **[verify]** which
   models are offered in your chosen region — availability differs by region.
4. Wait for the status to become **Access granted**. This is usually minutes but
   can take longer.

### 3.3 Create an access key

1. Console → search `IAM` → **Users** → **Create user**.
2. Name it something like `hackathon-bedrock`.
3. **Do not** give it console access. Attach permissions directly.
4. Permissions → **Attach policies directly** → search for
   `AmazonBedrockFullAccess`. **[verify]** For a submission this is acceptable;
   in production you would write a policy limited to `bedrock:InvokeModel` on the
   one model ARN.
5. Create the user → open it → **Security credentials** → **Create access key**
   → choose **Application running outside AWS**.
6. **Copy the secret key now.** AWS shows it exactly once.

### 3.4 Find your model ID

In the Bedrock console, open the model you enabled and copy its **model ID**. It
looks like a long string with a version suffix, and for some models it starts with
a region prefix such as `us.`. **[verify]** the exact string in your console —
do not copy one from a blog post, because model IDs change.

### 3.5 Configure and run

```powershell
cd "C:\Users\86185\Desktop\代码\DSH\hackathon-amazon-2026"

$env:AWS_REGION              = "us-east-1"
$env:AWS_ACCESS_KEY_ID       = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY   = "..."
$env:ALEXA_MCP_BEDROCK_MODEL = "<paste the model ID from 3.4>"

python -m alexa_mcp
```

Look for this line in the startup output:

```
INFO alexa_mcp: Amazon Bedrock rewriting: ON (<your-model-id> in us-east-1)
```

If instead you see:

```
INFO alexa_mcp: Amazon Bedrock rewriting: off (templates in use; set ...)
```

then a variable is missing or misspelled. That message names the variable it
wants, so read it carefully.

### 3.6 Prove it works

Enable the diagnostics tool, then ask for a status:

```powershell
$env:ALEXA_MCP_EXPOSE_STATUS = "1"
python -m alexa_mcp
```

In a second window:

```powershell
python -c "import sys; sys.path.insert(0,'.'); from alexa_mcp.client import McpHttpClient; c=McpHttpClient('http://127.0.0.1:8765/mcp'); c.initialize(); print(c.call_tool('get_integration_status')['content'][-1]['text'])"
```

You want to see `Bedrock active: yes` and a non-zero rewrite count.

### 3.7 The safety property you must be able to explain

When Bedrock is active, it **only rephrases**. It is never the source of a
number. After each generation the code extracts every numeric token from the
model's output and compares it against the original templated sentence. If
anything was rounded, dropped, or invented, the model's answer is **discarded**
and the template is used.

This is why the project can claim "a hallucination cannot become a wrong bill."
It is enforced by `alexa_mcp/bedrock.py` and proven by 37 offline tests in
`tests/test_bedrock.py` — including cases where the stub model tries to change
$9.91 into $40, rounds it to $10, or invents a percentage:

```powershell
python tests\test_bedrock.py
```

**Mention this in your Devpost write-up.** If you claim AWS Builder by saying
"we called Bedrock," a judge may ask what stops it from lying about a bill. Have
the answer ready.

---

## Part 4 — Optional: host the container on AWS

Only attempt this once Part 3 works. It is the largest time investment here.

### Easiest managed option: App Runner

**[verify] App Runner's current support for custom container ports and its
pricing before starting.** It is designed to run a container from an image with
much less setup than ECS.

**Step 1 — build the image and push it.** You need Docker Desktop, which your
machine does not have yet:

```powershell
winget install --id Docker.DockerDesktop
```

Then create an ECR repository:

1. Console → search `ECR` → **Create repository** → name it
   `home-energy-copilot` → Private → Create.
2. Click the repo → **View push commands** → follow them. AWS shows the exact
   commands for your account and region, which is more reliable than any
   transcription in this document.

**Step 2 — create the service.**

1. Console → search `App Runner` → **Create service**.
2. Source: **Container registry** → **Amazon ECR** → pick your image and tag.
3. Deployment trigger: **Manual** (so it does not redeploy unexpectedly).
4. Port: **8765** — this must match the `EXPOSE` line in the `Dockerfile`.
5. Add environment variables here rather than baking them into the image:
   `AWS_REGION`, and if you want Bedrock active, the credentials. **[verify]**
   the recommended way to supply secrets; App Runner supports referencing
   Secrets Manager, which is better than plain environment variables.
6. Health check path: `/healthz`.
7. Instance size: the smallest available. This service handles a handful of
   requests; anything larger is wasted money.
8. Create. The first deploy takes several minutes.

**Step 3 — verify.** Open the service URL plus `/healthz` in a browser. You want
the JSON listing 7 (or 8) tools. Then put that URL in the Devpost "Try it out"
field — now it is a real deployment that survives your laptop sleeping.

**Step 4 — TLS.** App Runner provides an HTTPS endpoint. **[verify]** whether
that is automatic or requires a custom domain. If it is HTTPS, you are done.

### Why not ECS Fargate for a first deployment

It is the more "serious" answer and it is what the README's roadmap mentions, but
it requires you to understand VPCs, subnets, security groups, target groups, load
balancers, task definitions, and IAM roles before anything runs. For a first AWS
project under a deadline, that is where days disappear. Use App Runner now; write
"migrate to ECS Fargate with an ALB" as future work. Judges accept a working
simple deployment over an ambitious broken one.

### The one thing you must not forget

Your server binds `0.0.0.0` in the container (`CMD` in the `Dockerfile` already
does this). Binding `127.0.0.1` inside a container makes it unreachable from
outside, which is the most common cause of "it works locally but not deployed."

---

## Part 5 — Clean up, and how to stop paying

Do this whenever you are finished testing, and again the day after you submit.

| Resource | How to remove |
|---|---|
| App Runner service | Console → App Runner → select → Actions → Delete |
| ECR repository | Console → ECR → select → Delete (and delete images first) |
| IAM access key | Console → IAM → Users → your user → Security credentials → Deactivate, then Delete |
| Bedrock | Nothing to delete; you pay per request only |
| Budget alert | Keep this one. It is free and it protects you. |

An App Runner service left running for a month at the smallest size costs real
money. **[verify]** the current hourly rate.

---

## Part 6 — What to put on the Devpost form

Once Part 3 works, you may legitimately claim:

- [x] **Mini challenge: AWS Builder** — "Spoken responses are rephrased by
      Amazon Bedrock using the Converse API over SigV4, with a figure-preservation
      guard that rejects any rewrite where a number changed."
- [x] Tags: add `amazon-bedrock` to the Built with field.

Once Part 4 works, you may additionally claim:

- [x] A live deployment URL in "Try it out".

Do not claim either before it actually works. A judge who clicks a dead link
trusts everything else in your submission less.

---

## Quick reference

```powershell
# Run locally
python -m alexa_mcp

# Run with Bedrock active
$env:ALEXA_MCP_BEDROCK_MODEL = "<model id>"
$env:AWS_REGION = "us-east-1"
$env:AWS_ACCESS_KEY_ID = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
python -m alexa_mcp

# Force templates even when Bedrock is configured
python -m alexa_mcp --no-bedrock

# Expose the diagnostics tool
$env:ALEXA_MCP_EXPOSE_STATUS = "1"

# Both test suites
python tests\smoke_test.py     # 57 checks: transport + tools
python tests\test_bedrock.py   # 37 checks: rewriter + figure guard, no AWS needed
```
