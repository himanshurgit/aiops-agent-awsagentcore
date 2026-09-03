"""Configuration for the AIOps agent.

Everything here is read from environment variables so the SAME code runs
unchanged on your laptop and inside AgentCore Runtime. On your laptop you set
these in the notebook; in AgentCore you set them with `agentcore` env config.
"""

import os


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# Region used for Bedrock and for the AWS APIs the tools call.
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Bedrock model the agent reasons with. Use an inference-profile ID (the
# "us." / "eu." / "global." prefixed form), not a bare base model ID.
MODEL_ID = os.environ.get("AIOPS_MODEL_ID", "us.amazon.nova-2-lite-v1:0")

# SAFETY LAYER 1: when true, write tools describe what they WOULD do and
# return without calling EC2. Defaults to true so a fresh clone cannot
# accidentally stop a real instance.
DRY_RUN = _flag("AIOPS_DRY_RUN", "true")

# SAFETY LAYER 2: write tools refuse any instance that does not carry this
# tag. This caps the blast radius in code, not just in the prompt.
MANAGED_TAG_KEY = os.environ.get("AIOPS_MANAGED_TAG_KEY", "AIOpsManaged")
MANAGED_TAG_VALUE = os.environ.get("AIOPS_MANAGED_TAG_VALUE", "true")

# Keep tool results small. Big JSON blobs burn context and slow the agent down.
MAX_EVENTS = int(os.environ.get("AIOPS_MAX_EVENTS", "5"))
MAX_INSTANCES = int(os.environ.get("AIOPS_MAX_INSTANCES", "20"))

# Seconds an identical CloudTrail query is served from the in-process cache.
CACHE_TTL_SECONDS = int(os.environ.get("AIOPS_CACHE_TTL_SECONDS", "60"))


def summary() -> dict:
    """Human-readable snapshot of the active config (handy in notebooks)."""
    return {
        "AWS_REGION": AWS_REGION,
        "MODEL_ID": MODEL_ID,
        "DRY_RUN": DRY_RUN,
        "managed_tag": f"{MANAGED_TAG_KEY}={MANAGED_TAG_VALUE}",
        "MAX_EVENTS": MAX_EVENTS,
        "CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
    }
