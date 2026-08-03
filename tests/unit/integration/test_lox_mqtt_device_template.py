"""Tests for grouped MQTT devices in Lox Config templates."""

import io
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import MagicMock

from boneio.integration.lox_template import (
    _build_mqtt_virtual_inputs,
    _mqtt_device_prefix,
    build_lox_template_archive,
    generate_lox_templates,
    lox_template_archive_name,
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


def test_generates_one_valid_xml_file_per_virtual_device():
    manager = MagicMock()
    manager.config_helper.serial_number = "BLK/test 01"
    manager.config_helper.name = "Test controller"
    manager.config_helper.get_config.return_value = {
        "lox_udp": {
            "host": "192.168.1.22",
            "send_port": 4444,
            "listen_port": 4445,
            "mqtt_bridge": [
                {"topic": "go-eCharger/408783/wh", "device_id": "charger_wh"},
                {"topic": "go-eCharger/408783/eto", "device_id": "charger_eto"},
                {"topic": "shelly/kitchen/power", "device_id": "shelly_power"},
            ],
        }
    }
    manager.outputs.get_all_outputs.return_value = {}
    manager.outputs.get_all_output_groups.return_value = {}
    manager.covers.get_all_covers.return_value = {}
    manager.inputs = None

    templates = generate_lox_templates(manager)

    assert list(templates) == [
        "boneio_blk_test_01_outputs.xml",
        "boneio_blk_test_01_status.xml",
        "mqtt_go-echarger_408783.xml",
        "mqtt_shelly_kitchen.xml",
    ]
    roots = {filename: ET.fromstring(xml) for filename, xml in templates.items()}
    assert roots["mqtt_go-echarger_408783.xml"].tag == "VirtualInUdp"
    assert len(roots["mqtt_go-echarger_408783.xml"].findall("VirtualInUdpCmd")) == 2
    assert len(roots["mqtt_shelly_kitchen.xml"].findall("VirtualInUdpCmd")) == 1


def test_packages_templates_in_one_zip_without_changing_xml():
    templates = {
        "mqtt_charger.xml": '<?xml version="1.0"?><VirtualInUdp />',
        "boneio_outputs.xml": '<?xml version="1.0"?><VirtualOut />',
    }

    archive = build_lox_template_archive(templates)

    with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
        assert zip_file.namelist() == list(templates)
        assert {
            name: zip_file.read(name).decode("utf-8")
            for name in zip_file.namelist()
        } == templates


def test_archive_filename_is_portable():
    assert lox_template_archive_name("BLK/test 01") == "boneio_blk_test_01_lox_templates.zip"
