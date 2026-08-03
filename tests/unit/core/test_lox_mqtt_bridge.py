"""Tests for forwarding arbitrary MQTT topics to Lox UDP inputs."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from boneio.core.messaging.lox_mqtt_bridge import LoxMqttBridge


@pytest.mark.asyncio
async def test_single_mapping_forwards_payload_to_lox_udp():
    """The subscribed callback should forward the payload under its device ID."""
    message_bus = MagicMock()
    message_bus.subscribe_and_listen = AsyncMock()
    lox_bus = MagicMock()
    bridge = LoxMqttBridge(
        message_bus,
        lox_bus,
        [{"topic": "go-eCharger/408783/wh", "device_id": "echarger_wh"}],
    )

    await bridge.start()
    callback = message_bus.subscribe_and_listen.await_args.args[1]
    await callback("go-eCharger/408783/wh", "21637.9")

    lox_bus.send_udp.assert_called_once_with("echarger_wh", "21637.9")


@pytest.mark.asyncio
async def test_multiple_mappings_forward_independently():
    """Each topic callback should retain the device ID from its own mapping."""
    message_bus = MagicMock()
    message_bus.subscribe_and_listen = AsyncMock()
    lox_bus = MagicMock()
    bridge = LoxMqttBridge(
        message_bus,
        lox_bus,
        [
            {"topic": "go-eCharger/408783/wh", "device_id": "echarger_wh"},
            {"topic": "go-eCharger/408783/car", "device_id": "echarger_car"},
        ],
    )

    await bridge.start()
    first_callback = message_bus.subscribe_and_listen.await_args_list[0].args[1]
    second_callback = message_bus.subscribe_and_listen.await_args_list[1].args[1]
    await first_callback("go-eCharger/408783/wh", "21637.9")
    await second_callback("go-eCharger/408783/car", "2")

    assert lox_bus.send_udp.call_args_list == [
        call("echarger_wh", "21637.9"),
        call("echarger_car", "2"),
    ]


@pytest.mark.asyncio
async def test_stop_unsubscribes_every_registered_topic():
    """Stopping the bridge should remove all topic listeners."""
    message_bus = MagicMock()
    message_bus.subscribe_and_listen = AsyncMock()
    message_bus.unsubscribe_and_stop_listen = AsyncMock()
    bridge = LoxMqttBridge(
        message_bus,
        MagicMock(),
        [
            {"topic": "go-eCharger/408783/wh", "device_id": "echarger_wh"},
            {"topic": "go-eCharger/408783/car", "device_id": "echarger_car"},
        ],
    )

    await bridge.stop()

    assert message_bus.unsubscribe_and_stop_listen.await_args_list == [
        call("go-eCharger/408783/wh"),
        call("go-eCharger/408783/car"),
    ]
