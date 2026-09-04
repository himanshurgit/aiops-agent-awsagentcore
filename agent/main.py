"""AIOps agent - AgentCore Runtime entrypoint.

Run it three ways, same file:

    python main.py                       # local HTTP server on :8080
    agentcore dev                        # local server + browser inspector
    agentcore deploy && agentcore invoke # hosted on AgentCore Runtime
"""

from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from strands import Agent
from strands.models import BedrockModel

import config
from prompts import SYSTEM_PROMPT
from tools_cloudtrail import CLOUDTRAIL_TOOLS
from tools_ec2 import EC2_TOOLS

# BedrockAgentCoreApp is the HTTP contract AgentCore Runtime speaks. It gives
# you POST /invocations and GET /ping for free; you supply the logic.
app = BedrockAgentCoreApp()

TOOLS = CLOUDTRAIL_TOOLS + EC2_TOOLS


def build_agent() -> Agent:
    """Construct a fresh agent with its own empty conversation history."""
    model = BedrockModel(
        model_id=config.MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.2,          # ops work wants boring, repeatable answers
    )
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=TOOLS)


# AgentCore Runtime gives every session its own isolated microVM and routes a
# session's requests back to the same one, so an in-process dict is enough to
# remember a conversation. Nothing here outlives the session.
_agents: dict[str, Agent] = {}


def get_agent(session_id: str | None) -> Agent:
    key = session_id or "local-session"
    if key not in _agents:
        _agents[key] = build_agent()
    if len(_agents) > 50:                    # bound memory on a long-lived VM
        _agents.pop(next(iter(_agents)))
    return _agents[key]


@app.entrypoint
async def invoke(payload: dict, context: RequestContext):
    """Handle one turn. Yielding strings streams them to the caller."""
    prompt = (payload or {}).get("prompt", "").strip()
    if not prompt:
        yield 'Send a payload like {"prompt": "list my EC2 instances"}.'
        return

    agent = get_agent(context.session_id)
    async for event in agent.stream_async(prompt):
        # Strands emits many event types (tool calls, reasoning, lifecycle).
        # "data" carries user-facing text; forward just that.
        if "data" in event:
            yield event["data"]


if __name__ == "__main__":
    print("AIOps agent starting with config:", config.summary())
    app.run()
