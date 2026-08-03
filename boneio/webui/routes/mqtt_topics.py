"""MQTT topic discovery routes for configuration autocomplete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from boneio.core.manager import Manager

router = APIRouter(prefix="/api/mqtt/topics", tags=["mqtt_topics"])


def get_manager() -> Manager:
    """Get manager instance - overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


class MqttTopicDiscoveryRequest(BaseModel):
    """Request for a short, prefix-scoped MQTT topic scan."""

    prefix: str = Field(min_length=1, max_length=512)


def topic_filter_from_prefix(prefix: str) -> str:
    """Convert a literal topic prefix into a scoped MQTT wildcard filter."""
    normalized = prefix.strip()
    if not normalized:
        raise ValueError("MQTT topic prefix cannot be empty")
    if "#" in normalized or "+" in normalized:
        raise ValueError("MQTT topic prefix cannot contain wildcard characters")
    if "/" not in normalized:
        # A root-level value may be only a fragment (for example "go" for
        # "go-eCharger"). MQTT cannot wildcard part of a topic level, so scan
        # root topics and filter the concrete results below.
        return "#"
    return f"{normalized}#" if normalized.endswith("/") else f"{normalized}/#"


@router.post("/discover")
async def discover_mqtt_topics(
    request: MqttTopicDiscoveryRequest,
    manager: Manager = Depends(get_manager),
) -> dict[str, str | list[str]]:
    """Observe retained/live MQTT topics below a literal prefix for two seconds."""
    try:
        topic_filter = topic_filter_from_prefix(request.prefix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    topics = await manager.message_bus.discover_topics(topic_filter, timeout=2.0)
    normalized_prefix = request.prefix.strip()
    topics = [topic for topic in topics if topic.startswith(normalized_prefix)]
    return {
        "prefix": normalized_prefix,
        "topics": topics[:200],
    }
