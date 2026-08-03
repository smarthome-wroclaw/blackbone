import React, { useState, useCallback, useEffect } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
import { NumericInput } from '@/components/ui/NumericInput';

interface LoxMqttBridgeMapping {
  topic: string;
  device_id: string;
}

interface LoxConfigData {
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
 * Accepts formats like: miniserver.local, loxone.home, my-server
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

  const updateMapping = (index: number, field: keyof LoxMqttBridgeMapping, value: string) => {
    const updatedMappings = mappings.map((mapping, mappingIndex) => (
      mappingIndex === index ? { ...mapping, [field]: value } : mapping
    ));
    handleChange('mqtt_bridge', updatedMappings);
  };

  const addMapping = () => {
    handleChange('mqtt_bridge', [...mappings, { topic: '', device_id: '' }]);
  };

  const removeMapping = (index: number) => {
    handleChange('mqtt_bridge', mappings.filter((_, mappingIndex) => mappingIndex !== index));
  };

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

      {/* MQTT to Loxone Bridge */}
      <div className="divider">{t('lox_config.mqtt_bridge_section')}</div>

      <div className="space-y-3">
        {mappings.map((mapping, index) => {
          const topicEmpty = mapping.topic.trim() === '';
          const deviceIdEmpty = mapping.device_id.trim() === '';
          const deviceIdDuplicate = !deviceIdEmpty && deviceIdCounts[mapping.device_id.trim()] > 1;

          return (
            <div key={index} className="rounded-box border border-base-300 bg-base-100 p-3">
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start">
                <div className="form-control">
                  <label className="label py-1">
                    <span className="label-text font-medium">{t('lox_config.mqtt_bridge_topic')}</span>
                  </label>
                  <input
                    type="text"
                    className={`input input-bordered w-full ${topicEmpty ? 'input-error' : ''}`}
                    value={mapping.topic}
                    onChange={(event) => updateMapping(index, 'topic', event.target.value)}
                    placeholder="go-eCharger/408783/wh"
                    required
                  />
                  {topicEmpty && (
                    <HelpLabel className="[&>span]:text-error">
                      {t('lox_config.mqtt_bridge_required')}
                    </HelpLabel>
                  )}
                </div>

                <div className="form-control">
                  <label className="label py-1">
                    <span className="label-text font-medium">{t('lox_config.mqtt_bridge_device_id')}</span>
                  </label>
                  <input
                    type="text"
                    className={`input input-bordered w-full ${deviceIdEmpty || deviceIdDuplicate ? 'input-error' : ''}`}
                    value={mapping.device_id}
                    onChange={(event) => updateMapping(index, 'device_id', event.target.value)}
                    placeholder="echarger_wh"
                    required
                  />
                  {deviceIdEmpty && (
                    <HelpLabel className="[&>span]:text-error">
                      {t('lox_config.mqtt_bridge_required')}
                    </HelpLabel>
                  )}
                  {deviceIdDuplicate && (
                    <HelpLabel className="[&>span]:text-error">
                      {t('lox_config.mqtt_bridge_duplicate_device_id')}
                    </HelpLabel>
                  )}
                </div>

                <button
                  type="button"
                  className="btn btn-ghost btn-sm mt-7 text-error"
                  onClick={() => removeMapping(index)}
                  aria-label={t('lox_config.mqtt_bridge_remove')}
                  title={t('lox_config.mqtt_bridge_remove')}
                >
                  <FaTrash />
                </button>
              </div>
            </div>
          );
        })}

        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={addMapping}
        >
          <FaPlus /> {t('lox_config.mqtt_bridge_add')}
        </button>

        <HelpLabel>{t('lox_config.mqtt_bridge_help')}</HelpLabel>
      </div>

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

      <HelpLabel>{t('lox_config.template_help')}</HelpLabel>
    </div>
  );
};

export default LoxForm;
