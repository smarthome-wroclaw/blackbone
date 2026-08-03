import { describe, expect, it } from 'vitest';
import {
  getMqttDevicePrefix,
  getMqttDiscoveryPrefix,
  getMqttTopicLeaf,
  groupDiscoveredTopicsByDevice,
  groupMqttBridgeMappings,
  suggestGroupedLoxDeviceId,
  suggestLoxDeviceId,
} from './loxMqttBridge';

describe('getMqttDiscoveryPrefix', () => {
  it('keeps an explicitly entered prefix', () => {
    expect(getMqttDiscoveryPrefix('go-eCharger/408783/')).toBe('go-eCharger/408783/');
  });

  it('uses the parent prefix when an exact topic is entered', () => {
    expect(getMqttDiscoveryPrefix('go-eCharger/408783/wh')).toBe('go-eCharger/408783/');
  });

  it('keeps a partial root-level topic fragment', () => {
    expect(getMqttDiscoveryPrefix('go')).toBe('go');
  });

  it('returns an empty prefix for blank input', () => {
    expect(getMqttDiscoveryPrefix('   ')).toBe('');
  });
});

describe('suggestLoxDeviceId', () => {
  it('builds a readable ID from a go-eCharger topic', () => {
    expect(suggestLoxDeviceId('go-eCharger/408783/wh')).toBe('echarger_wh');
  });

  it('sanitizes arbitrary MQTT topic segments', () => {
    expect(suggestLoxDeviceId('Shelly Garage/device-1/Power W')).toBe('shelly_garage_power_w');
  });

  it('returns an empty suggestion for an empty topic', () => {
    expect(suggestLoxDeviceId('')).toBe('');
  });
});

describe('MQTT device grouping', () => {
  it('uses the parent path as the device and the final segment as the input', () => {
    expect(getMqttDevicePrefix('go-eCharger/408783/eto')).toBe('go-eCharger/408783');
    expect(getMqttTopicLeaf('go-eCharger/408783/eto')).toBe('eto');
  });

  it('groups discovered topics by device prefix', () => {
    expect(groupDiscoveredTopicsByDevice([
      'shelly/kitchen/power',
      'go-eCharger/408783/wh',
      'go-eCharger/408783/eto',
    ])).toEqual([
      {
        devicePrefix: 'go-eCharger/408783',
        topics: ['go-eCharger/408783/eto', 'go-eCharger/408783/wh'],
      },
      {
        devicePrefix: 'shelly/kitchen',
        topics: ['shelly/kitchen/power'],
      },
    ]);
  });

  it('groups persisted flat mappings without changing their indices', () => {
    const groups = groupMqttBridgeMappings([
      { topic: 'go-eCharger/408783/eto', device_id: 'eto' },
      { topic: 'shelly/kitchen/power', device_id: 'power' },
      { topic: 'go-eCharger/408783/wh', device_id: 'wh' },
    ]);
    expect(groups[0].devicePrefix).toBe('go-eCharger/408783');
    expect(groups[0].mappings.map(item => item.index)).toEqual([0, 2]);
  });

  it('includes the device serial in grouped Lox input IDs', () => {
    expect(suggestGroupedLoxDeviceId('go-eCharger/408783/eto')).toBe('echarger_408783_eto');
  });
});
