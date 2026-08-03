"""Tests for Lox MQTT bridge configuration validation."""

import pytest

from boneio.core.config.yaml_util import (
    ConfigurationException,
    clear_config_cache,
    load_config_from_string,
)


@pytest.fixture(autouse=True)
def fresh_schema_cache():
    """Clear the configuration schema cache around every test."""
    clear_config_cache(clear_static=True)
    yield
    clear_config_cache(clear_static=True)


def test_multiple_mqtt_bridge_mappings_are_valid():
    """Multiple mappings with distinct device IDs should pass validation."""
    config = load_config_from_string(
        """
boneio:
  name: test
lox_udp:
  enabled: true
  host: 127.0.0.1
  mqtt_bridge:
    - topic: go-eCharger/408783/wh
      device_id: echarger_wh
    - topic: go-eCharger/408783/car
      device_id: echarger_car
"""
    )

    assert config["lox_udp"]["mqtt_bridge"] == [
        {"topic": "go-eCharger/408783/wh", "device_id": "echarger_wh"},
        {"topic": "go-eCharger/408783/car", "device_id": "echarger_car"},
    ]


def test_duplicate_mqtt_bridge_device_id_is_rejected():
    """A Lox virtual input may only be targeted by one mapping."""
    with pytest.raises(ConfigurationException, match="validation failed"):
        load_config_from_string(
            """
boneio:
  name: test
lox_udp:
  enabled: true
  host: 127.0.0.1
  mqtt_bridge:
    - topic: go-eCharger/408783/wh
      device_id: echarger_value
    - topic: go-eCharger/408783/car
      device_id: echarger_value
"""
        )


@pytest.mark.parametrize("missing_field", ["topic", "device_id"])
def test_mqtt_bridge_mapping_requires_both_fields(missing_field):
    """Every mapping must define both its MQTT topic and Lox device ID."""
    mapping = {
        "topic": "go-eCharger/408783/wh",
        "device_id": "echarger_wh",
    }
    del mapping[missing_field]
    mapping_yaml = "\n".join(f"      {key}: {value}" for key, value in mapping.items())

    with pytest.raises(ConfigurationException, match="validation failed"):
        load_config_from_string(
            f"""
boneio:
  name: test
lox_udp:
  enabled: true
  host: 127.0.0.1
  mqtt_bridge:
    -
{mapping_yaml}
"""
        )
