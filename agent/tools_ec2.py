"""EC2 tools: read freely, write carefully.

Three independent safety layers guard the write tools. Any ONE of them can
stop a bad action, which is the point - a prompt alone is advice, not a
control.

  1. Prompt      - the system prompt tells the agent to confirm first (UX).
  2. Code        - _guard() below refuses instances that are not tagged
                   AIOpsManaged=true, and honours AIOPS_DRY_RUN (enforced).
  3. IAM         - the execution role only allows Start/Stop/Reboot on
                   instances carrying that tag (enforced by AWS itself).
"""

import boto3
from strands import tool

import config

_ec2 = boto3.client("ec2", region_name=config.AWS_REGION)

WRITE_ACTIONS = ("start", "stop", "reboot")


# Error codes that genuinely mean "no such instance". Anything else - an
# AccessDenied, a throttle - must NOT be reported as "not found", or you will
# spend an afternoon debugging the wrong problem.
_NOT_FOUND_CODES = ("InvalidInstanceID.NotFound", "InvalidInstanceID.Malformed")


def _describe(instance_id: str) -> dict | None:
    """Return a compact description of one instance, or None if not found.

    Real failures (permissions, throttling) are re-raised so the agent sees the
    actual AWS error instead of a misleading "not found".
    """
    try:
        reservations = _ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    except _ec2.exceptions.ClientError as err:
        if err.response["Error"]["Code"] in _NOT_FOUND_CODES:
            return None
        raise
    if not reservations:
        return None
    i = reservations[0]["Instances"][0]
    tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
    return {
        "instance_id": i["InstanceId"],
        "name": tags.get("Name", "n/a"),
        "type": i["InstanceType"],
        "state": i["State"]["Name"],
        "az": i["Placement"]["AvailabilityZone"],
        "private_ip": i.get("PrivateIpAddress", "n/a"),
        "tags": tags,
    }


def _guard(instance_id: str, action: str) -> tuple[dict | None, dict | None]:
    """Validate a write request. Returns (details, refusal).

    Exactly one of the two is not None. A refusal is a normal dict, not an
    exception: the agent reads it and explains the block to the user.
    """
    if not instance_id or not instance_id.startswith("i-"):
        return None, {"blocked": True, "reason": "invalid_instance_id",
                      "message": "instance_id must look like i-0abc123..."}

    details = _describe(instance_id)
    if details is None:
        return None, {"blocked": True, "reason": "not_found",
                      "message": f"No instance {instance_id} in {config.AWS_REGION}."}

    tag_value = details["tags"].get(config.MANAGED_TAG_KEY)
    if tag_value != config.MANAGED_TAG_VALUE:
        return None, {
            "blocked": True,
            "reason": "not_managed",
            "message": (
                f"{instance_id} is not tagged "
                f"{config.MANAGED_TAG_KEY}={config.MANAGED_TAG_VALUE}, so this agent "
                f"will not {action} it. Tag the instance first if that is intended."
            ),
            "instance": {k: details[k] for k in ("instance_id", "name", "state")},
        }
    return details, None


def _dry_run(action: str, details: dict) -> dict:
    return {
        "dry_run": True,
        "action": action,
        "message": (
            f"DRY RUN - would {action} {details['instance_id']} "
            f"({details['name']}, currently {details['state']}). "
            "No change was made. Set AIOPS_DRY_RUN=false to execute for real."
        ),
        "instance": details,
    }


@tool
def list_instances(state: str = "all", max_results: int = 10) -> dict:
    """List EC2 instances in the configured region with their state and tags.

    Use this first when the user names an instance by nickname rather than ID,
    or asks what is running.

    Args:
        state: Filter by lifecycle state - "all", "running", "stopped",
            "pending", or "stopping". Defaults to "all".
        max_results: Maximum instances to return, up to 20. Defaults to 10.
    """
    limit = max(1, min(int(max_results), config.MAX_INSTANCES))
    filters = [] if state in ("", "all", None) else [
        {"Name": "instance-state-name", "Values": [state]}
    ]
    pages = _ec2.get_paginator("describe_instances").paginate(
        Filters=filters, PaginationConfig={"MaxItems": limit}
    )
    instances = []
    for page in pages:
        for reservation in page["Reservations"]:
            for i in reservation["Instances"]:
                tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                instances.append({
                    "instance_id": i["InstanceId"],
                    "name": tags.get("Name", "n/a"),
                    "type": i["InstanceType"],
                    "state": i["State"]["Name"],
                    "managed_by_agent": tags.get(config.MANAGED_TAG_KEY) == config.MANAGED_TAG_VALUE,
                })
    return {"region": config.AWS_REGION, "count": len(instances), "instances": instances[:limit]}


@tool
def get_instance_status(instance_id: str) -> dict:
    """Get full detail for one EC2 instance: state, type, AZ, IP, and tags.

    Always call this before proposing a start, stop, or reboot so you can show
    the user exactly what they are about to change.

    Args:
        instance_id: The instance ID, e.g. "i-0abc123def456".
    """
    details = _describe(instance_id)
    if details is None:
        return {"error": f"No instance {instance_id} in {config.AWS_REGION}."}
    details["managed_by_agent"] = (
        details["tags"].get(config.MANAGED_TAG_KEY) == config.MANAGED_TAG_VALUE
    )
    return details


@tool
def stop_instance(instance_id: str) -> dict:
    """Stop a running EC2 instance. Destructive - confirm with the user first.

    Only works on instances tagged AIOpsManaged=true, and does nothing while
    AIOPS_DRY_RUN is enabled.

    Args:
        instance_id: The instance ID to stop, e.g. "i-0abc123def456".
    """
    details, refusal = _guard(instance_id, "stop")
    if refusal:
        return refusal
    if details["state"] in ("stopped", "stopping"):
        return {"success": True, "no_op": True, "state": details["state"],
                "message": f"{instance_id} is already {details['state']}."}
    if config.DRY_RUN:
        return _dry_run("stop", details)
    result = _ec2.stop_instances(InstanceIds=[instance_id])
    return {"success": True, "action": "stop", "instance_id": instance_id,
            "state": result["StoppingInstances"][0]["CurrentState"]["Name"],
            "previous_state": details["state"]}


@tool
def start_instance(instance_id: str) -> dict:
    """Start a stopped EC2 instance. Confirm with the user first.

    Only works on instances tagged AIOpsManaged=true, and does nothing while
    AIOPS_DRY_RUN is enabled.

    Args:
        instance_id: The instance ID to start, e.g. "i-0abc123def456".
    """
    details, refusal = _guard(instance_id, "start")
    if refusal:
        return refusal
    if details["state"] in ("running", "pending"):
        return {"success": True, "no_op": True, "state": details["state"],
                "message": f"{instance_id} is already {details['state']}."}
    if config.DRY_RUN:
        return _dry_run("start", details)
    result = _ec2.start_instances(InstanceIds=[instance_id])
    return {"success": True, "action": "start", "instance_id": instance_id,
            "state": result["StartingInstances"][0]["CurrentState"]["Name"],
            "previous_state": details["state"]}


@tool
def reboot_instance(instance_id: str) -> dict:
    """Reboot a running EC2 instance. Destructive - confirm with the user first.

    Only works on instances tagged AIOpsManaged=true, and does nothing while
    AIOPS_DRY_RUN is enabled.

    Args:
        instance_id: The instance ID to reboot, e.g. "i-0abc123def456".
    """
    details, refusal = _guard(instance_id, "reboot")
    if refusal:
        return refusal
    if details["state"] != "running":
        return {"error": f"Cannot reboot {instance_id}: state is {details['state']}."}
    if config.DRY_RUN:
        return _dry_run("reboot", details)
    _ec2.reboot_instances(InstanceIds=[instance_id])
    return {"success": True, "action": "reboot", "instance_id": instance_id,
            "state": "rebooting"}


READ_TOOLS = [list_instances, get_instance_status]
WRITE_TOOLS = [stop_instance, start_instance, reboot_instance]
EC2_TOOLS = READ_TOOLS + WRITE_TOOLS
