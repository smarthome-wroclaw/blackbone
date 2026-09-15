# Custom Modbus devices

Device definitions saved from WebUI live beside the configuration file, at
`<config.yaml directory>/modbus_devices/<key>.json`. They are user data and
are not replaced when the BoneIO package is upgraded.

The key is both the filename (without `.json`) and the value used by `model:`
in `config.yaml`. It must match `^[a-z0-9][a-z0-9_-]{1,63}$`. Built-in keys
cannot be overwritten; load one in the creator and save it under a new key to
make a fork.

Definitions contain a display `model`, optional `manufacturer`, `description`,
`category`, `default_address`, and `default_update_interval`, plus one or more
`registers_base` blocks. A block has `base`, `length`, optional
`register_type` (`input` is the default), and `registers`. `set_base` may
describe address/baudrate configuration registers. `additional_entities` may
contain derived entities.

```json
{
  "model": "My two-register sensor",
  "manufacturer": "Example",
  "category": "sensors",
  "default_address": 1,
  "registers_base": [{
    "base": 0,
    "length": 2,
    "registers": [
      {"name": "Temperature", "address": 0, "unit_of_measurement": "°C", "state_class": "measurement", "value_type": "S_WORD"},
      {"name": "Humidity", "address": 1, "unit_of_measurement": "%", "state_class": "measurement", "value_type": "S_WORD"}
    ]
  }]
}
```

The creator edits metadata and readable registers. Imported writable and
derived entities are retained unchanged when the definition is saved again.
Deleting a definition used by `modbus_devices` is blocked. Remove or change
those devices in `config.yaml` first, then delete the definition.
