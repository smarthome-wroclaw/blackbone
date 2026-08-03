"""Lox Config Template Generator.

Generates XML configuration templates for importing into Lox Config software.
The templates describe all BoneIO outputs, covers, and sensors as
Virtual UDP Input/Output commands that the Miniserver can use.

Two separate templates are generated:
- VirtualOut: Miniserver → BoneIO (sending commands)
- VirtualInUdp: BoneIO → Miniserver (receiving state feedback)

The output XML files are compatible with Lox Config's import mechanism
and use the correct element names, attributes, and structure required by Lox Config.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Lox template type constants
_TEMPLATE_TYPE_INPUT = "1"   # VirtualInUdp
_TEMPLATE_TYPE_OUTPUT = "3"  # VirtualOut (UDP)
_MIN_VERSION = "17000331"    # Minimum Lox Config version


def _uuid() -> str:
    """Generate a Lox-style UUID (lowercase with dashes)."""
    return str(uuid.uuid4())


def generate_lox_templates(manager: Manager) -> dict[str, str]:
    """Generate one valid Lox Config XML document per virtual device.

    Creates independent XML documents for:
    - VirtualOut: Commands Miniserver sends to BoneIO (ON/OFF, OPEN/CLOSE)
    - VirtualInUdp: State feedback BoneIO sends to Miniserver
    - Each MQTT device: One input for every mapped topic below its parent path

    The generated XML can be imported into Lox Config to quickly set up
    communication between a Lox Miniserver and this BoneIO device.

    Args:
        manager: Active Manager instance with initialized outputs/covers.

    Returns:
        Mapping of safe filenames to standalone XML template documents.
    """
    serial = manager.config_helper.serial_number or "boneio"
    device_name = manager.config_helper.name or serial

    # Get Lox UDP config (host/ports) from running config
    lox_config = _get_lox_config(manager)
    boneio_ip = lox_config.get("boneio_ip", "0.0.0.0")
    listen_port = lox_config.get("listen_port", 4445)  # BoneIO listens on this
    send_port = lox_config.get("send_port", 4444)  # BoneIO sends to this

    # ===========================================================
    # VirtualOut (Miniserver → BoneIO)
    # Miniserver sends commands to BoneIO's listen_port
    # ===========================================================
    vout = ET.Element("VirtualOut")
    vout.set("Title", f"boneIO {device_name}")
    vout.set("Comment", f"BoneIO {serial} output control")
    vout.set("Address", f"/dev/udp/{boneio_ip}/{listen_port}")
    vout.set("CmdInit", "")
    vout.set("CloseAfterSend", "true")
    vout.set("CmdSep", ";")
    vout.set("HintText", "")

    # Info element with template type (required for Lox Config import)
    info_out = ET.SubElement(vout, "Info")
    info_out.set("templateType", _TEMPLATE_TYPE_OUTPUT)
    info_out.set("minVersion", _MIN_VERSION)

    # --- Output commands ---
    outputs = manager.outputs.get_all_outputs()
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        cmd = ET.SubElement(vout, "VirtualOutCmd")
        cmd.set("Title", f"{output.name}")
        cmd.set("Comment", "")
        cmd.set("CmdOnMethod", "GET")
        cmd.set("CmdOffMethod", "GET")
        cmd.set("CmdOn", f"{output_id}=ON")
        cmd.set("CmdOnHTTP", "")
        cmd.set("CmdOnPost", "")
        cmd.set("CmdOff", f"{output_id}=OFF")
        cmd.set("CmdOffHTTP", "")
        cmd.set("CmdOffPost", "")
        cmd.set("CmdAnswer", "")
        cmd.set("Analog", "false")
        cmd.set("Repeat", "0")
        cmd.set("RepeatRate", "0")
        cmd.set("HintText", "")

    # --- Output group commands ---
    output_groups = manager.outputs.get_all_output_groups()
    for group_id, group in output_groups.items():
        cmd = ET.SubElement(vout, "VirtualOutCmd")
        cmd.set("Title", f"Group: {getattr(group, 'name', group_id)}")
        cmd.set("Comment", "")
        cmd.set("CmdOnMethod", "GET")
        cmd.set("CmdOffMethod", "GET")
        cmd.set("CmdOn", f"{group_id}=ON")
        cmd.set("CmdOnHTTP", "")
        cmd.set("CmdOnPost", "")
        cmd.set("CmdOff", f"{group_id}=OFF")
        cmd.set("CmdOffHTTP", "")
        cmd.set("CmdOffPost", "")
        cmd.set("CmdAnswer", "")
        cmd.set("Analog", "false")
        cmd.set("Repeat", "0")
        cmd.set("RepeatRate", "0")
        cmd.set("HintText", "")

    # --- Cover commands ---
    covers = manager.covers.get_all_covers()
    for cover_id, cover in covers.items():
        # Open command
        cmd_open = ET.SubElement(vout, "VirtualOutCmd")
        cmd_open.set("Title", f"{cover.name} Open")
        cmd_open.set("Comment", "")
        cmd_open.set("CmdOnMethod", "GET")
        cmd_open.set("CmdOffMethod", "GET")
        cmd_open.set("CmdOn", f"{cover_id}=OPEN")
        cmd_open.set("CmdOnHTTP", "")
        cmd_open.set("CmdOnPost", "")
        cmd_open.set("CmdOff", f"{cover_id}=STOP")
        cmd_open.set("CmdOffHTTP", "")
        cmd_open.set("CmdOffPost", "")
        cmd_open.set("CmdAnswer", "")
        cmd_open.set("Analog", "false")
        cmd_open.set("Repeat", "0")
        cmd_open.set("RepeatRate", "0")
        cmd_open.set("HintText", "")

        # Close command
        cmd_close = ET.SubElement(vout, "VirtualOutCmd")
        cmd_close.set("Title", f"{cover.name} Close")
        cmd_close.set("Comment", "")
        cmd_close.set("CmdOnMethod", "GET")
        cmd_close.set("CmdOffMethod", "GET")
        cmd_close.set("CmdOn", f"{cover_id}=CLOSE")
        cmd_close.set("CmdOnHTTP", "")
        cmd_close.set("CmdOnPost", "")
        cmd_close.set("CmdOff", f"{cover_id}=STOP")
        cmd_close.set("CmdOffHTTP", "")
        cmd_close.set("CmdOffPost", "")
        cmd_close.set("CmdAnswer", "")
        cmd_close.set("Analog", "false")
        cmd_close.set("Repeat", "0")
        cmd_close.set("RepeatRate", "0")
        cmd_close.set("HintText", "")

    # ===========================================================
    # VirtualInUdp (BoneIO → Miniserver)
    # BoneIO sends state updates to Miniserver's send_port
    # Miniserver listens for these on its own UDP port
    # ===========================================================
    vin = ET.Element("VirtualInUdp")
    vin.set("Title", f"boneIO {device_name} Status")
    vin.set("Comment", f"BoneIO {serial} state feedback")
    vin.set("Address", "")
    vin.set("Port", str(send_port))
    vin.set("HintText", "")

    # Info element with template type
    info_in = ET.SubElement(vin, "Info")
    info_in.set("templateType", _TEMPLATE_TYPE_INPUT)
    info_in.set("minVersion", _MIN_VERSION)

    # --- Output state feedback ---
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
        vi_cmd.set("Title", f"{output.name}")
        vi_cmd.set("Comment", "")
        vi_cmd.set("Address", boneio_ip)
        # A backslash before device_id marks the identifier as literal.
        vi_cmd.set("Check", f"\\{output_id}=\\v")
        vi_cmd.set("Signed", "true")
        vi_cmd.set("Analog", "false")
        vi_cmd.set("SourceValLow", "0")
        vi_cmd.set("DestValLow", "0")
        vi_cmd.set("SourceValHigh", "100")
        vi_cmd.set("DestValHigh", "100")
        vi_cmd.set("DefVal", "0")
        vi_cmd.set("MinVal", "0")
        vi_cmd.set("MaxVal", "1")
        vi_cmd.set("Unit", "")
        vi_cmd.set("HintText", "")

    # --- Cover state feedback (position 0-100) ---
    for cover_id, cover in covers.items():
        vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
        vi_cmd.set("Title", f"{cover.name} Position")
        vi_cmd.set("Comment", "")
        vi_cmd.set("Address", boneio_ip)
        vi_cmd.set("Check", f"\\{cover_id}=\\v")
        vi_cmd.set("Signed", "true")
        vi_cmd.set("Analog", "true")
        vi_cmd.set("SourceValLow", "0")
        vi_cmd.set("DestValLow", "0")
        vi_cmd.set("SourceValHigh", "100")
        vi_cmd.set("DestValHigh", "100")
        vi_cmd.set("DefVal", "0")
        vi_cmd.set("MinVal", "0")
        vi_cmd.set("MaxVal", "100")
        vi_cmd.set("Unit", "%")
        vi_cmd.set("HintText", "")

    # --- Input (event/binary_sensor) state feedback ---
    if manager.inputs:
        all_inputs = manager.inputs.get_all_inputs()
        for input_id, input_obj in all_inputs.items():
            vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
            vi_cmd.set("Title", f"Input {getattr(input_obj, 'name', input_id)}")
            vi_cmd.set("Comment", "")
            vi_cmd.set("Address", boneio_ip)
            vi_cmd.set("Check", f"\\{input_id}=\\v")
            vi_cmd.set("Signed", "true")
            vi_cmd.set("Analog", "false")
            vi_cmd.set("SourceValLow", "0")
            vi_cmd.set("DestValLow", "0")
            vi_cmd.set("SourceValHigh", "100")
            vi_cmd.set("DestValHigh", "100")
            vi_cmd.set("DefVal", "0")
            vi_cmd.set("MinVal", "0")
            vi_cmd.set("MaxVal", "1")
            vi_cmd.set("Unit", "")
            vi_cmd.set("HintText", "")

    # --- MQTT bridge devices ---
    # Each parent topic is represented as one VirtualInUdp device in Lox,
    # while its concrete topics become virtual inputs on that device.
    mqtt_devices = _build_mqtt_virtual_inputs(
        lox_config.get("mqtt_bridge", []),
        boneio_ip=boneio_ip,
        send_port=send_port,
    )

    serial_slug = _safe_filename_part(serial)
    templates = {
        f"boneio_{serial_slug}_outputs.xml": _element_to_xml(vout),
        f"boneio_{serial_slug}_status.xml": _element_to_xml(vin),
    }
    for device in mqtt_devices:
        device_slug = _safe_filename_part(device.get("Title", "mqtt_device"))
        base_name = f"mqtt_{device_slug}"
        filename = f"{base_name}.xml"
        suffix = 2
        while filename in templates:
            filename = f"{base_name}_{suffix}.xml"
            suffix += 1
        templates[filename] = _element_to_xml(device)
    return templates


def build_lox_template_archive(templates: dict[str, str]) -> bytes:
    """Package standalone Lox XML templates into one downloadable ZIP."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for filename, xml_content in templates.items():
            zip_file.writestr(filename, xml_content)
    return archive.getvalue()


def lox_template_archive_name(serial: str) -> str:
    """Return a safe ZIP filename for a BoneIO device."""
    return f"boneio_{_safe_filename_part(serial or 'boneio')}_lox_templates.zip"


def generate_lox_template(manager: Manager) -> str:
    """Return the legacy concatenated representation for internal callers.

    Download routes should use :func:`generate_lox_templates`, because a valid
    XML file can contain only one top-level virtual device.
    """
    return "\n\n".join(generate_lox_templates(manager).values())


def _safe_filename_part(value: str) -> str:
    """Convert a device label into a portable, readable filename segment."""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return normalized.strip("._-").lower() or "device"


def _mqtt_device_prefix(topic: str) -> str:
    """Return the parent path that identifies a concrete MQTT device."""
    normalized = topic.strip().rstrip("/")
    if not normalized:
        return ""
    parent, separator, _leaf = normalized.rpartition("/")
    return parent if separator else normalized


def _build_mqtt_virtual_inputs(
    mappings: list[dict[str, Any]],
    *,
    boneio_ip: str,
    send_port: int,
) -> list[ET.Element]:
    """Build one Lox VirtualInUdp device per MQTT parent topic."""
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        topic = str(mapping.get("topic", "")).strip()
        device_id = str(mapping.get("device_id", "")).strip()
        prefix = _mqtt_device_prefix(topic)
        if topic and device_id and prefix:
            grouped[prefix].append({"topic": topic, "device_id": device_id})

    devices: list[ET.Element] = []
    for prefix in sorted(grouped):
        device = ET.Element("VirtualInUdp")
        device.set("Title", prefix)
        device.set("Comment", f"MQTT device {prefix} via boneIO")
        device.set("Address", "")
        device.set("Port", str(send_port))
        device.set("HintText", "")

        info = ET.SubElement(device, "Info")
        info.set("templateType", _TEMPLATE_TYPE_INPUT)
        info.set("minVersion", _MIN_VERSION)

        for mapping in sorted(grouped[prefix], key=lambda item: item["topic"]):
            topic = mapping["topic"]
            leaf = topic.removeprefix(f"{prefix}/") or topic
            virtual_input = ET.SubElement(device, "VirtualInUdpCmd")
            virtual_input.set("Title", leaf)
            virtual_input.set("Comment", topic)
            virtual_input.set("Address", boneio_ip)
            virtual_input.set("Check", f"\\{mapping['device_id']}=\\v")
            virtual_input.set("Signed", "true")
            virtual_input.set("Analog", "true")
            virtual_input.set("SourceValLow", "0")
            virtual_input.set("DestValLow", "0")
            virtual_input.set("SourceValHigh", "100")
            virtual_input.set("DestValHigh", "100")
            virtual_input.set("DefVal", "0")
            virtual_input.set("MinVal", "-2147483648")
            virtual_input.set("MaxVal", "2147483647")
            virtual_input.set("Unit", "")
            virtual_input.set("HintText", "")

        devices.append(device)

    return devices


def _element_to_xml(element: ET.Element) -> str:
    """Convert an XML element to a pretty-printed string with XML declaration.

    Args:
        element: XML element to serialize.

    Returns:
        Formatted XML string with declaration.
    """
    ET.indent(element, space="\t")
    xml_str = ET.tostring(element, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="utf-8"?>\n{xml_str}'


def generate_lox_summary(manager: Manager) -> dict[str, Any]:
    """Generate a JSON summary of all available Lox UDP commands.

    This is useful for documentation and debugging — shows exactly
    which commands BoneIO will accept and which status messages it sends.

    Args:
        manager: Active Manager instance.

    Returns:
        Dictionary with 'commands' and 'status' sections.
    """
    serial = manager.config_helper.serial_number or "boneio"
    device_name = manager.config_helper.name or serial

    commands: list[dict[str, str]] = []
    status_messages: list[dict[str, str]] = []

    # Outputs
    outputs = manager.outputs.get_all_outputs()
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue
        commands.append({
            "entity": output_id,
            "name": output.name,
            "type": output.output_type,
            "cmd_on": f"{output_id}=ON",
            "cmd_off": f"{output_id}=OFF",
        })
        status_messages.append({
            "entity": output_id,
            "name": output.name,
            "type": output.output_type,
            "format": f"{output_id}=ON|OFF",
        })

    # Output groups
    output_groups = manager.outputs.get_all_output_groups()
    for group_id, group in output_groups.items():
        name = getattr(group, "name", group_id)
        commands.append({
            "entity": group_id,
            "name": name,
            "type": "group",
            "cmd_on": f"{group_id}=ON",
            "cmd_off": f"{group_id}=OFF",
        })

    # Covers
    covers = manager.covers.get_all_covers()
    for cover_id, cover in covers.items():
        commands.append({
            "entity": cover_id,
            "name": cover.name,
            "type": "cover",
            "cmd_on": f"{cover_id}=OPEN",
            "cmd_off": f"{cover_id}=CLOSE",
            "cmd_stop": f"{cover_id}=STOP",
        })
        status_messages.append({
            "entity": cover_id,
            "name": cover.name,
            "type": "cover",
            "format": f"{cover_id}=0..100",
        })

    lox_config = _get_lox_config(manager)
    mqtt_devices: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for mapping in lox_config.get("mqtt_bridge", []):
        topic = str(mapping.get("topic", "")).strip()
        device_id = str(mapping.get("device_id", "")).strip()
        prefix = _mqtt_device_prefix(topic)
        if not topic or not device_id or not prefix:
            continue
        mqtt_input = {
            "entity": device_id,
            "name": topic.removeprefix(f"{prefix}/") or topic,
            "type": "mqtt",
            "format": f"{device_id}=<value>",
            "topic": topic,
        }
        mqtt_devices[prefix].append(mqtt_input)
        status_messages.append(mqtt_input)

    return {
        "device_name": device_name,
        "serial": serial,
        "output_count": len(outputs),
        "cover_count": len(covers),
        "group_count": len(output_groups),
        "commands": commands,
        "status_messages": status_messages,
        "mqtt_devices": [
            {"name": prefix, "inputs": inputs}
            for prefix, inputs in sorted(mqtt_devices.items())
        ],
    }


def _get_lox_config(manager: Manager) -> dict[str, Any]:
    """Extract Lox UDP config from manager's config helper.

    Args:
        manager: Active Manager instance.

    Returns:
        Dictionary with lox_udp configuration values.
    """
    try:
        config = manager.config_helper.get_config()
        lox = config.get("lox_udp", {})
        return {
            "boneio_ip": lox.get("host", "0.0.0.0"),
            "send_port": lox.get("send_port", 4444),
            "listen_port": lox.get("listen_port", 4445),
            "mqtt_bridge": lox.get("mqtt_bridge", []),
        }
    except Exception as e:
        _LOGGER.warning("Could not read lox_udp config: %s", e)
        return {
            "boneio_ip": "0.0.0.0",
            "send_port": 4444,
            "listen_port": 4445,
            "mqtt_bridge": [],
        }
