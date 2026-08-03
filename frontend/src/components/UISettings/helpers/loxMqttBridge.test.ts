import { describe, expect, it } from 'vitest';
import {
  getMqttDiscoveryPrefix,
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
