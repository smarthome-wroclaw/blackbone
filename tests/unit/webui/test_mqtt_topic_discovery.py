"""Tests for the WebUI MQTT topic discovery endpoint."""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.modules.setdefault("gpiod", MagicMock())
sys.modules.setdefault("gpiod.line", MagicMock())

from boneio.webui.routes.mqtt_topics import (
    MqttTopicDiscoveryRequest,
    discover_mqtt_topics,
    topic_filter_from_prefix,
)


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("go-eCharger/408783/", "go-eCharger/408783/#"),
        (" go-eCharger/408783 ", "go-eCharger/408783/#"),
        ("go", "#"),
    ],
)
def test_topic_filter_from_prefix(prefix, expected):
    """A literal prefix should become a scoped MQTT wildcard filter."""
    assert topic_filter_from_prefix(prefix) == expected


@pytest.mark.parametrize("prefix", ["", "   ", "devices/#", "devices/+/state"])
def test_topic_filter_from_prefix_rejects_empty_or_wildcard_prefix(prefix):
    """Users may only scan literal, non-empty prefixes."""
    with pytest.raises(ValueError):
        topic_filter_from_prefix(prefix)


@pytest.mark.asyncio
async def test_discover_mqtt_topics_uses_manager_message_bus():
    """The endpoint delegates discovery to the application's existing bus."""
    manager = MagicMock()
    manager.message_bus.discover_topics = AsyncMock(
        return_value=[
            "go-eCharger/408783/car",
            "go-eCharger/408783/wh",
            "homeassistant/sensor/example/config",
        ]
    )
    request = MqttTopicDiscoveryRequest(prefix="go-eCharger/408783/")

    result = await discover_mqtt_topics(request, manager)

    manager.message_bus.discover_topics.assert_awaited_once_with(
        "go-eCharger/408783/#",
        timeout=2.0,
    )
    assert result == {
        "prefix": "go-eCharger/408783/",
        "topics": [
            "go-eCharger/408783/car",
            "go-eCharger/408783/wh",
        ],
    }


@pytest.mark.asyncio
async def test_discover_mqtt_topics_filters_partial_root_prefix():
    """A partial root fragment should scan root topics and filter the response."""
    manager = MagicMock()
    manager.message_bus.discover_topics = AsyncMock(
        return_value=[
            "go-eCharger/408783/eto",
            "homeassistant/status",
        ]
    )

    result = await discover_mqtt_topics(MqttTopicDiscoveryRequest(prefix="go"), manager)

    manager.message_bus.discover_topics.assert_awaited_once_with("#", timeout=2.0)
    assert result == {
        "prefix": "go",
        "topics": ["go-eCharger/408783/eto"],
    }
