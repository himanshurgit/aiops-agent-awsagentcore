# AIOps Agent on Amazon Bedrock AgentCore

An AWS operations assistant — CloudTrail monitoring plus safe EC2 management —
built on **Amazon Bedrock AgentCore**, with three explained Jupyter notebooks.

This is the rebuild of the original [Bedrock Agents version](https://github.com/himanshurgit/aiops-agent),
which used a service that entered **maintenance mode** and closed to new customers
on **30 July 2026**. AWS's recommended path is AgentCore, so the demo moved.

Part of **[AI Fundamentals for Beginners: Learn LLM, Agentic AI & MCP](https://www.udemy.com/course/ai-fundamentals-for-beginners-learn-llm-agentic-ai-mcp/?referralCode=4D49F0BFDF7A68F7CF22)**.

> **Migrating from the old build?** Jump to [Migration reference](#migration-reference).
> The original Bedrock Agents version is preserved at
> [himanshurgit/aiops-agent](https://github.com/himanshurgit/aiops-agent) — reading
> the two side by side is the clearest way to see what actually changed.

---

## Three notebooks

Work through them in order. Together they take about 90 minutes.

| Notebook | What it covers | Runs where |
| --- | --- | --- |
| [`01_concepts_and_setup.ipynb`](notebooks/01_concepts_and_setup.ipynb) | What changed and why, the old→new migration map, environment setup, model access | Local |
| [`02_build_and_test_locally.ipynb`](notebooks/02_build_and_test_locally.ipynb) | The agent loop, `@tool` functions, the system prompt, three layers of safety, first real runs | Local, against real AWS |
| [`03_deploy_to_agentcore_runtime.ipynb`](notebooks/03_deploy_to_agentcore_runtime.ipynb) | The AgentCore entrypoint, the CLI, deploy, IAM scoping, observability, Memory & Gateway, cleanup | AWS |

Notebook 02 **writes** the files in `agent/` via `%%writefile`, so the code you
read in the lecture is exactly the code that gets deployed. The files are also
committed here, so the repo works without running anything.

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
| `AIOPS_MODEL_ID` | `us.anthropic.claude-sonnet-5` | Bedrock **inference profile** ID (keep the `us.`/`eu.`/`global.` prefix) |
| `AIOPS_DRY_RUN` | `true` | When true, write tools simulate and change nothing |
| `AIOPS_MANAGED_TAG_KEY` | `AIOpsManaged` | Tag key the write guard requires |
| `AIOPS_MANAGED_TAG_VALUE` | `true` | Tag value the write guard requires |
| `AIOPS_MAX_EVENTS` | `5` | Hard cap on CloudTrail events per query |
| `AIOPS_MAX_INSTANCES` | `20` | Hard cap on instances per listing |
| `AIOPS_CACHE_TTL_SECONDS` | `60` | CloudTrail query cache lifetime |

---

## Prerequisites

- AWS account where you can create IAM roles
- AWS CLI configured (`aws sso login` recommended)
- Bedrock **model access** granted for an Anthropic Claude model
- Python 3.10+
- Node.js 20+ — notebook 03 only, for the AgentCore CLI
- An EC2 instance is **optional**; dry-run mode covers every exercise

---

## Cost

Under **$5** for the full three-notebook run. Bedrock tokens dominate; an idle
deployed agent costs nothing. Notebook 03 ends with a teardown — please run it.

---

## Migration reference
<a id="migration-reference"></a>

| Bedrock Agents (Classic) | AgentCore |
| --- | --- |
| Console "Instructions for the Agent" | `prompts.py` |
| Action group + OpenAPI JSON schema | `@tool` function — hints and docstring **are** the schema |
| One Lambda per action group | Plain functions in the agent process (or keep the Lambdas behind Gateway) |
| `messageVersion` / `apiPath` response envelope | `return {...}` |
| AWS-owned orchestration loop | Strands loop, in your process |
| Prepare / versions / aliases | `agentcore deploy` |
| `bedrock-agent-runtime:InvokeAgent` | Runtime endpoint, `POST /invocations` |
| Managed session state | Session-isolated microVM + AgentCore Memory |
| CloudWatch logs | AgentCore Observability — traces and spans |

Already have a large Lambda-backed estate? **AgentCore Gateway** exposes existing
Lambda functions and OpenAPI specs as MCP tools without rewriting them — covered
in notebook 03, section 10.

---

## References

- [Get started with Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html)
- [Bedrock Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- [AgentCore CLI](https://github.com/aws/agentcore-cli) · [AgentCore Python SDK](https://github.com/aws/bedrock-agentcore-sdk-python)
- [Strands Agents SDK](https://strandsagents.com) · [AgentCore samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
