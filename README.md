# AIOps Agent on Amazon Bedrock AgentCore

An **AIOps agent** you can talk to in plain English: *"what's been happening in my
AWS account?"*, *"which instances are running?"*, *"stop the staging server"*. It
reads real CloudTrail history, lists real EC2 instances, and refuses to do anything
dangerous.

Built on **Amazon Bedrock AgentCore** with the **Strands Agents** SDK, and taught
through three Jupyter notebooks that explain every line.

Part of **[AI Fundamentals for Beginners: Learn LLM, Agentic AI & MCP](https://www.udemy.com/course/ai-fundamentals-for-beginners-learn-llm-agentic-ai-mcp/?referralCode=4D49F0BFDF7A68F7CF22)**.

> **New to agents?** Start at notebook 01 and work through in order. You need an AWS
> account and about 90 minutes. An EC2 instance is optional — the agent ships in
> dry-run mode.

---

## Three notebooks

Work through them in order. Together they take about 90 minutes.

| Notebook | What it covers | Runs where |
| --- | --- | --- |
| [`01_concepts_and_setup.ipynb`](notebooks/01_concepts_and_setup.ipynb) | What an agent is, what AgentCore gives you, environment setup, model access | Local |
| [`02_build_and_test_locally.ipynb`](notebooks/02_build_and_test_locally.ipynb) | The agent loop, `@tool` functions, the system prompt, three layers of safety, first real runs | Local, against real AWS |
| [`03_deploy_to_agentcore_runtime.ipynb`](notebooks/03_deploy_to_agentcore_runtime.ipynb) | The AgentCore entrypoint, the CLI, deploy, IAM scoping, observability, cleanup | AWS |

Notebook 02 **writes** the files in `agent/` via `%%writefile`, so the code you
read in the lecture is exactly the code that gets deployed. The files are also
committed here, so the repo works without running anything.

**Not covered here.** AgentCore also offers **Memory** (recall that outlives a
session) and **Gateway** (turns existing Lambda functions, OpenAPI specs, and MCP
servers into agent tools). Notebook 03 says what each one is for and when you would
reach for it, then stops — doing either properly is a course of its own. Nothing in
these notebooks turns them on, so nothing here bills for them.

---

## Layout

```
.
├── notebooks/                     # the three lectures
├── agent/                         # the deployable agent
│   ├── main.py                    #   AgentCore Runtime entrypoint
│   ├── config.py                  #   env-driven settings + safety switches
│   ├── prompts.py                 #   the system prompt
│   ├── tools_cloudtrail.py        #   4 read-only monitoring tools
│   ├── tools_ec2.py               #   5 EC2 tools, 2 read + 3 guarded writes
│   └── requirements.txt
└── infra/
    ├── agentcore-execution-policy.json   # least-privilege tool permissions
    └── attach-policy.sh                  # attaches it to the execution role
```

---

## Quick start

First time on this machine? Install Git, the AWS CLI, Python, and Node.js —
see [Installing the tools](#installing-git-the-aws-cli-python-and-nodejs).

```bash
git clone https://github.com/himanshurgit/aiops-agent-awsagentcore.git
cd aiops-agent-awsagentcore
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install jupyterlab
jupyter lab notebooks/01_concepts_and_setup.ipynb
```

To skip the lectures and just run the agent:

```bash
pip install -r agent/requirements.txt
cd agent
export AWS_REGION=us-east-1
export AIOPS_DRY_RUN=true
python main.py                    # serves http://localhost:8080/invocations
```

```bash
curl -N -X POST http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "list my EC2 instances"}'
```

To deploy (needs Node.js 20+):

```bash
npm install -g @aws/agentcore
agentcore create --name AIOpsAgent --framework Strands --model-provider Bedrock --memory none --build CodeZip
cp agent/*.py AIOpsAgent/app/AIOpsAgent/
cd AIOpsAgent && agentcore deploy
```

Then attach the tool permissions — `agentcore deploy` does **not** grant them:

```bash
agentcore status                                    # find the execution role name
../infra/attach-policy.sh <role-name>
agentcore invoke --prompt "what happened in my account recently?"
```

Notebook 03 walks through all of this with the reasoning behind each step.

---

## What the agent can do

**Monitoring — read-only, always safe**

| Tool | Answers |
| --- | --- |
| `get_recent_events` | "What's been happening in the last hour?" |
| `get_events_by_user` | "What did alice do today?" |
| `get_events_by_service` | "Show me recent EC2 activity" |
| `find_events_by_name` | "Who called StopInstances?" |
| `list_instances` | "What's running?" |
| `get_instance_status` | "Tell me about i-0abc123" |

**Management — changes real infrastructure**

`start_instance` · `stop_instance` · `reboot_instance`

---

## Safety model

Three independent layers. Any one of them alone stops a bad action.

| Layer | Where | Enforced by | Bypassable by a clever prompt? |
| --- | --- | --- | --- |
| 1. Ask before acting | `prompts.py` | the model | **Yes** — it is advice |
| 2. Tag guard + dry run | `_guard()` in `tools_ec2.py` | your Python | No |
| 3. IAM tag condition | `infra/agentcore-execution-policy.json` | AWS | No |

Write tools only touch instances tagged `AIOpsManaged=true`, and `AIOPS_DRY_RUN`
defaults to `true` so a fresh clone cannot change anything.

To opt one disposable instance in:

```bash
aws ec2 create-tags --resources i-0abc123def456 --tags Key=AIOpsManaged,Value=true
```

**The point:** a prompt is a preference, code and IAM are controls. Build all three
and never mistake the first for the others.

---

## Configuration

All settings are environment variables, so the same code runs locally and hosted.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Region for Bedrock and the tool APIs |
| `AIOPS_MODEL_ID` | `us.amazon.nova-2-lite-v1:0` | Bedrock **inference profile** ID (keep the `us.`/`eu.`/`global.` prefix) |
| `AIOPS_DRY_RUN` | `true` | When true, write tools simulate and change nothing |
| `AIOPS_MANAGED_TAG_KEY` | `AIOpsManaged` | Tag key the write guard requires |
| `AIOPS_MANAGED_TAG_VALUE` | `true` | Tag value the write guard requires |
| `AIOPS_MAX_EVENTS` | `5` | Hard cap on CloudTrail events per query |
| `AIOPS_MAX_INSTANCES` | `20` | Hard cap on instances per listing |
| `AIOPS_CACHE_TTL_SECONDS` | `60` | CloudTrail query cache lifetime |

---

## Prerequisites

- AWS account where you can create IAM roles
- **Git** — to clone this repo
- **AWS CLI v2**, configured (`aws sso login` recommended) — the notebooks and the
  deploy steps both shell out to it
- Bedrock model access — serverless models are on by default; Anthropic needs a
  one-time use-case form per account, submitted from the Bedrock model catalog
- Python 3.10+
- Node.js 20+ — notebook 03 only, for the AgentCore CLI
- An EC2 instance is **optional**; dry-run mode covers every exercise

### Installing Git, the AWS CLI, Python, and Node.js

Four command-line tools, and you need them before notebook 01 will get past its
first cell:

| Tool | Why | Needed for |
| --- | --- | --- |
| **Git** | clone this repo | all notebooks |
| **AWS CLI v2** | sign in to AWS and run the `aws ...` commands the lectures show | all notebooks |
| **Python 3.10+** | run the notebooks and the agent | all notebooks |
| **Node.js 20+** | the AgentCore CLI is an npm package | notebook 03 |

Check what you already have first — many machines ship with some of these:

```bash
git --version
aws --version
python3 --version
node --version
```

If all four print versions that meet the minimums, skip ahead to
[Configure the AWS CLI](#configure-the-aws-cli). Otherwise install what is missing.

**macOS** — install [Homebrew](https://brew.sh) first if you don't have it, then:

```bash
brew install git awscli python@3.12 node
```

The macOS system Python is old and managed by Apple; install your own rather than
using it. The plain `node` formula tracks the current release, which is well past
20 — you do not need a pinned `node@20`. macOS may already have `git` from the
Xcode command line tools; the Homebrew one is newer and does no harm.

**Windows** — from PowerShell, using the built-in package manager:

```powershell
winget install Git.Git Amazon.AWSCLI Python.Python.3.12 OpenJS.NodeJS.LTS
```

Close and reopen PowerShell afterwards so the new `PATH` takes effect. Prefer
clicking through installers? See [Download the installers
directly](#download-the-installers-directly) below — on the Python installer,
tick **"Add python.exe to PATH"** on the first screen. Note that on Windows the
command is `python`, not `python3`.

**Linux (Debian/Ubuntu)** — Git and Python come from apt; the AWS CLI and Node.js
do not, because the distro packages are v1 and too old respectively:

```bash
sudo apt update && sudo apt install -y git python3 python3-pip python3-venv unzip curl
```

```bash
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install && rm -rf awscliv2.zip aws
```

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

On an ARM machine (Graviton, Raspberry Pi) swap `x86_64` for `aarch64` in the AWS
CLI URL.

#### Download the installers directly

If you would rather not use a package manager, every tool ships an official
installer. Download links below — take them only from these official sites:

| Tool | macOS | Windows | Linux |
| --- | --- | --- | --- |
| **Git** | [git-scm.com/download/mac](https://git-scm.com/download/mac) | [64-bit installer](https://git-scm.com/download/win) | [git-scm.com/download/linux](https://git-scm.com/download/linux) |
| **AWS CLI v2** | [AWSCLIV2.pkg](https://awscli.amazonaws.com/AWSCLIV2.pkg) | [AWSCLIV2.msi](https://awscli.amazonaws.com/AWSCLIV2.msi) | [x86_64 zip](https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip) · [aarch64 zip](https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip) |
| **Python 3.10+** | [python.org/downloads/macos](https://www.python.org/downloads/macos/) | [python.org/downloads/windows](https://www.python.org/downloads/windows/) | [python.org/downloads/source](https://www.python.org/downloads/source/) |
| **Node.js 20+** | [nodejs.org/en/download](https://nodejs.org/en/download) | [nodejs.org/en/download](https://nodejs.org/en/download) | [nodejs.org/en/download](https://nodejs.org/en/download) |

All four landing pages: [git-scm.com/downloads](https://git-scm.com/downloads) ·
[AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) ·
[python.org/downloads](https://www.python.org/downloads/) ·
[nodejs.org/en/download](https://nodejs.org/en/download)

On macOS and Linux, distro packages of Python are often too old and Node.js
almost always is — if an installer gives you a version below the minimum, use the
package-manager commands above instead. After any installer, close and reopen your
terminal before running the checks below.

#### Configure the AWS CLI

Installing the CLI does not sign you in. Do that once, either way:

```bash
aws configure sso      # recommended: IAM Identity Center, short-lived credentials
```

```bash
aws configure          # or: a static access key pair
```

Then prove it worked. This must print your account number and identity ARN:

```bash
aws sts get-caller-identity
```

With SSO you will need to re-run `aws sso login` whenever the session expires —
and if you log in *after* starting Jupyter, restart Jupyter so it picks up the
refreshed credentials.

#### Verify

All four must print a version, and the numbers must be at least 3.10 and 20:

```bash
git --version
aws --version
python3 --version && python3 -m venv --help > /dev/null && echo "python ok"
node --version && npm --version
```

Everything after this point runs inside a virtual environment (`.venv`), so
nothing you install for this course touches your system Python.

---

## Cost

Under **$5** for the full three-notebook run. Bedrock tokens dominate; an idle
deployed agent costs nothing. Notebook 03 ends with a teardown — please run it.

---

## References

- [Get started with Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html)
- [AgentCore CLI](https://github.com/aws/agentcore-cli) · [AgentCore Python SDK](https://github.com/aws/bedrock-agentcore-sdk-python)
- [Strands Agents SDK](https://strandsagents.com) · [AgentCore samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
