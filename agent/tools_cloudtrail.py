"""Read-only CloudTrail tools.

In the old Bedrock Agents build these were Lambda functions behind an OpenAPI
schema. Here they are plain Python functions with an @tool decorator: the
function signature and docstring ARE the schema the model sees, so there is no
separate JSON file to keep in sync.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import boto3
from strands import tool

import config

_cloudtrail = boto3.client("cloudtrail", region_name=config.AWS_REGION)

# CloudTrail LookupEvents is rate limited (2 requests/second). A tiny cache
# stops a chatty agent from hammering it while exploring a question.
_cache: dict[str, tuple[datetime, dict]] = {}


def _cache_key(name: str, params: dict) -> str:
    raw = f"{name}:{json.dumps(params, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cached(name: str, params: dict, fetch):
    key = _cache_key(name, params)
    now = datetime.now(timezone.utc)
    hit = _cache.get(key)
    if hit and (now - hit[0]).total_seconds() < config.CACHE_TTL_SECONDS:
        return {**hit[1], "cached": True}
    result = fetch()
    _cache[key] = (now, result)
    if len(_cache) > 32:                      # crude LRU: drop the oldest entry
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    return result


def _window(hours: int, max_hours: int) -> tuple[datetime, datetime]:
    hours = max(1, min(int(hours), max_hours))
    end = datetime.now(timezone.utc)
    return end - timedelta(hours=hours), end


def _lookup(lookup_attributes, hours, max_results, max_hours):
    start, end = _window(hours, max_hours)
    limit = max(1, min(int(max_results), config.MAX_EVENTS))
    kwargs = {"StartTime": start, "EndTime": end, "MaxResults": limit}
    if lookup_attributes:
        kwargs["LookupAttributes"] = lookup_attributes
    response = _cloudtrail.lookup_events(**kwargs)
    return [
        {
            "time": e["EventTime"].isoformat(),
            "event": e["EventName"],
            "user": e.get("Username", "n/a"),
            "source": e.get("EventSource", "n/a"),
        }
        for e in response.get("Events", [])[:limit]
    ]


@tool
def get_recent_events(hours: int = 1, max_results: int = 5) -> dict:
    """Get the most recent AWS API activity from CloudTrail across all services.

    Use this to answer open questions like "what happened recently?" or
    "is anything going on in the account right now?".

    Args:
        hours: How far back to look, 1-3 hours. Defaults to 1.
        max_results: How many events to return, up to 5. Defaults to 5.
    """
    params = {"hours": hours, "max_results": max_results}
    def fetch():
        events = _lookup(None, hours, max_results, max_hours=3)
        return {"count": len(events), "window_hours": hours, "events": events}
    return _cached("recent", params, fetch)


@tool
def get_events_by_user(username: str, hours: int = 24, max_results: int = 5) -> dict:
    """Get recent CloudTrail events performed by one IAM user or role session.

    Use this to answer "what did <person> do?" during an incident review.

    Args:
        username: The IAM user name or role session name, e.g. "alice" or "admin".
        hours: How far back to look, 1-24 hours. Defaults to 24.
        max_results: How many events to return, up to 5. Defaults to 5.
    """
    if not username:
        return {"error": "username is required"}
    params = {"username": username, "hours": hours, "max_results": max_results}
    def fetch():
        attrs = [{"AttributeKey": "Username", "AttributeValue": username}]
        events = _lookup(attrs, hours, max_results, max_hours=24)
        return {"username": username, "count": len(events), "events": events}
    return _cached("by_user", params, fetch)


@tool
def get_events_by_service(service: str, hours: int = 12, max_results: int = 5) -> dict:
    """Get recent CloudTrail events emitted by one AWS service.

    Use this to narrow an investigation, e.g. "show me recent EC2 activity".

    Args:
        service: Service name such as "ec2", "s3", or "iam". The
            ".amazonaws.com" suffix is added automatically if you omit it.
        hours: How far back to look, 1-12 hours. Defaults to 12.
        max_results: How many events to return, up to 5. Defaults to 5.
    """
    if not service:
        return {"error": "service is required"}
    source = service if service.endswith(".amazonaws.com") else f"{service}.amazonaws.com"
    params = {"service": source, "hours": hours, "max_results": max_results}
    def fetch():
        attrs = [{"AttributeKey": "EventSource", "AttributeValue": source}]
        events = _lookup(attrs, hours, max_results, max_hours=12)
        return {"service": source, "count": len(events), "events": events}
    return _cached("by_service", params, fetch)


@tool
def find_events_by_name(event_name: str, hours: int = 24, max_results: int = 5) -> dict:
    """Find recent CloudTrail events with a specific API name.

    Use this for targeted questions like "who called StopInstances today?"
    or "were there any ConsoleLogin failures?".

    Args:
        event_name: Exact CloudTrail event name, e.g. "StopInstances",
            "RunInstances", "ConsoleLogin". Case sensitive.
        hours: How far back to look, 1-24 hours. Defaults to 24.
        max_results: How many events to return, up to 5. Defaults to 5.
    """
    if not event_name:
        return {"error": "event_name is required"}
    params = {"event_name": event_name, "hours": hours, "max_results": max_results}
    def fetch():
        attrs = [{"AttributeKey": "EventName", "AttributeValue": event_name}]
        events = _lookup(attrs, hours, max_results, max_hours=24)
        return {"event_name": event_name, "count": len(events), "events": events}
    return _cached("by_name", params, fetch)


CLOUDTRAIL_TOOLS = [
    get_recent_events,
    get_events_by_user,
    get_events_by_service,
    find_events_by_name,
]
