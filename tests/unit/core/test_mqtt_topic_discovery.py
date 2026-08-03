"""Tests for temporary MQTT topic discovery sessions."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from boneio.core.messaging.mqtt import MQTTClient


def _make_client(*, connected: bool = True) -> MQTTClient:
    client = MQTTClient.__new__(MQTTClient)
    client._connection_established = connected
    client._topics = []
    client._discovery_topics = []
    client._mqtt_energy_listeners = {}
    client._topic_discovery_sessions = {}
    client.subscribe = AsyncMock()
    client.unsubscribe = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_discover_topics_collects_unique_matching_topics():
    """A discovery session subscribes temporarily and returns sorted topics."""
    client = _make_client()

    task = asyncio.create_task(
        client.discover_topics("go-eCharger/408783/#", timeout=0.01)
    )
    await asyncio.sleep(0)
    sessions = client._topic_discovery_sessions["go-eCharger/408783/#"]
    sessions[0].update(
        {
            "go-eCharger/408783/wh",
            "go-eCharger/408783/car",
        }
    )

    topics = await task

    assert topics == [
        "go-eCharger/408783/car",
        "go-eCharger/408783/wh",
    ]
    client.subscribe.assert_awaited_once_with(topics=["go-eCharger/408783/#"])
    client.unsubscribe.assert_awaited_once_with(["go-eCharger/408783/#"])
    assert client._topic_discovery_sessions == {}


@pytest.mark.asyncio
async def test_discover_topics_preserves_existing_listener_subscription():
    """Discovery must not unsubscribe a filter already used by the bridge."""
    client = _make_client()
    client._mqtt_energy_listeners["go-eCharger/408783/#"] = AsyncMock()

    await client.discover_topics("go-eCharger/408783/#", timeout=0)

    client.subscribe.assert_not_awaited()
    client.unsubscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_discover_topics_while_disconnected_only_collects_locally():
    """A disconnected client should not attempt network subscribe operations."""
    client = _make_client(connected=False)

    topics = await client.discover_topics("go-eCharger/408783/#", timeout=0)

    assert topics == []
    client.subscribe.assert_not_awaited()
    client.unsubscribe.assert_not_awaited()
