import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
import { NumericInput } from '@/components/ui/NumericInput';
import MqttDeviceGroups, { type LoxMqttBridgeMapping } from './MqttDeviceGroups';

export interface LoxConfigData {
  enabled?: boolean;
  host?: string;
  send_port?: number;
  listen_port?: number;
  mqtt_bridge?: LoxMqttBridgeMapping[];
}

interface LoxFormProps {
  data?: LoxConfigData;
  onChange: (data: LoxConfigData) => void;
  onValidationChange?: (isValid: boolean) => void;
}

/**
 * Validate an IPv4 address string.
 */
function isValidIPv4(ip: string): boolean {
  const parts = ip.split('.');
  if (parts.length !== 4) return false;
  return parts.every(part => {
    const num = Number(part);
    return Number.isInteger(num) && num >= 0 && num <= 255 && part === String(num);
  });
}

/**
 * Validate a hostname string (RFC 1123).
 * Accepts formats like: miniserver.local, lox.home, my-server
 */
function isValidHostname(host: string): boolean {
  if (host.length > 253) return false;
  const labelPattern = /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/;
  return host.split('.').every(label => labelPattern.test(label));
}

/**
 * Validate host as either a valid IPv4 address or a valid hostname.
 */
function isValidHost(host: string): boolean {
  return isValidIPv4(host) || isValidHostname(host);
}

/**
 * Custom form for Lox UDP section configuration.
 * Fields: host, send/listen ports, MQTT bridge mappings, and Lox template actions.
 */
const LoxForm: React.FC<LoxFormProps> = ({ data, onChange, onValidationChange }) => {
  const { t } = useTranslation();
  const [hostTouched, setHostTouched] = useState(false);

  const host = data?.host || '';
  const mappings = data?.mqtt_bridge ?? [];
  const hostEmpty = !host.trim();
  const hostInvalid = !hostEmpty && !isValidHost(host.trim());
  const hostError = hostTouched && (hostEmpty || hostInvalid);
  const deviceIdCounts = mappings.reduce<Record<string, number>>((counts, mapping) => {
    const deviceId = mapping.device_id.trim();
    if (deviceId) counts[deviceId] = (counts[deviceId] ?? 0) + 1;
    return counts;
  }, {});
  const mappingsValid = mappings.every(mapping => (
    mapping.topic.trim() !== ''
    && mapping.device_id.trim() !== ''
    && deviceIdCounts[mapping.device_id.trim()] === 1
  ));
  const isValid = !hostEmpty && !hostInvalid && mappingsValid;

  // Notify parent about validation state
  useEffect(() => {
    onValidationChange?.(isValid);
  }, [isValid, onValidationChange]);

  const handleChange = useCallback(<K extends keyof LoxConfigData>(field: K, value: LoxConfigData[K]) => {
    onChange({ ...(data ?? {}), [field]: value });
  }, [data, onChange]);

  const handleDownloadTemplate = () => {
    window.open('/api/config/lox-template', '_blank');
  };

  const handleViewCommands = async () => {
    window.open('/api/config/lox-commands', '_blank');
  };

  return (
    <div className="space-y-4">
      {/* Host */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.host')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full ${hostError ? 'input-error' : ''}`}
          value={host}
          onChange={(e) => handleChange('host', e.target.value)}
          onBlur={() => setHostTouched(true)}
          placeholder="192.168.1.100"
          required
        />
        {hostError && hostEmpty && (
          <label className="label">
            <span className="label-text-alt text-error">{t('lox_config.host_required')}</span>
          </label>
        )}
        {hostError && hostInvalid && (
          <label className="label">
            <span className="label-text-alt text-error">{t('lox_config.host_invalid')}</span>
          </label>
        )}
        {!hostError && (
          <HelpLabel>{t('lox_config.host_help')}</HelpLabel>
        )}
      </div>

      {/* Send Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.send_port')}</span>
        </label>
        <NumericInput
          value={data?.send_port ?? 4444}
          onChange={(v) => handleChange('send_port', v === '' ? 4444 : v)}
          min={1}
          max={65535}
          placeholder="4444"
        />
        <HelpLabel>{t('lox_config.send_port_help')}</HelpLabel>
      </div>

      {/* Listen Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.listen_port')}</span>
        </label>
        <NumericInput
          value={data?.listen_port ?? 4445}
          onChange={(v) => handleChange('listen_port', v === '' ? 4445 : v)}
          min={1}
          max={65535}
          placeholder="4445"
        />
        <HelpLabel>{t('lox_config.listen_port_help')}</HelpLabel>
      </div>

      {/* MQTT to Lox Bridge */}
      <div className="divider">{t('lox_config.mqtt_bridge_section')}</div>

      <MqttDeviceGroups
        mappings={mappings}
        deviceIdCounts={deviceIdCounts}
        onChange={nextMappings => handleChange('mqtt_bridge', nextMappings)}
      />

      {/* Lox Config Template Actions */}
      <div className="divider">{t('lox_config.template_section')}</div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={handleDownloadTemplate}
        >
          📥 {t('lox_config.download_template')}
        </button>

        <button
          type="button"
          className="btn btn-outline btn-sm btn-ghost"
          onClick={handleViewCommands}
        >
          📋 {t('lox_config.view_commands')}
        </button>
      </div>

      <HelpLabel className="overflow-x-auto [&>span]:max-w-none [&>span]:whitespace-nowrap">
        {t('lox_config.template_help')}
      </HelpLabel>
    </div>
  );
};

export default LoxForm;
