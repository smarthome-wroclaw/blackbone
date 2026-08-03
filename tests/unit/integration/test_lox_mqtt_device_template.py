"""Tests for grouped MQTT devices in Lox Config templates."""

from boneio.integration.lox_template import (
    _build_mqtt_virtual_inputs,
    _mqtt_device_prefix,
)


def test_mqtt_device_prefix_uses_parent_topic_path():
    assert _mqtt_device_prefix("go-eCharger/408783/eto") == "go-eCharger/408783"


def test_builds_one_virtual_device_with_an_input_for_each_topic():
    devices = _build_mqtt_virtual_inputs(
        [
            {
                "topic": "go-eCharger/408783/wh",
                "device_id": "echarger_408783_wh",
            },
            {
                "topic": "go-eCharger/408783/eto",
                "device_id": "echarger_408783_eto",
            },
        ],
        boneio_ip="192.168.1.22",
        send_port=4444,
    )

    assert len(devices) == 1
    device = devices[0]
    assert device.tag == "VirtualInUdp"
    assert device.attrib["Title"] == "go-eCharger/408783"
    assert device.attrib["Port"] == "4444"

    inputs = device.findall("VirtualInUdpCmd")
    assert [item.attrib["Title"] for item in inputs] == ["eto", "wh"]
    assert inputs[0].attrib["Comment"] == "go-eCharger/408783/eto"
    assert inputs[0].attrib["Check"] == r"\echarger_408783_eto=\v"


def test_builds_separate_virtual_devices_for_different_topic_parents():
    devices = _build_mqtt_virtual_inputs(
        [
            {"topic": "go-eCharger/408783/eto", "device_id": "charger_eto"},
            {"topic": "shelly/kitchen/power", "device_id": "shelly_power"},
        ],
        boneio_ip="192.168.1.22",
        send_port=4444,
    )

    assert [device.attrib["Title"] for device in devices] == [
        "go-eCharger/408783",
        "shelly/kitchen",
    ]
