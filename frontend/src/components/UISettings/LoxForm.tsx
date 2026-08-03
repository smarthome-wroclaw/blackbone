import React, { useState, useCallback, useEffect } from 'react';
import { FaPlus, FaSearch, FaSpinner, FaTrash } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  getMqttDiscoveryPrefix,
  suggestLoxDeviceId,
} from './helpers/loxMqttBridge';

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

interface TopicDiscoveryResponse {
  prefix: string;
  topics: string[];
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
  const [discoveringIndex, setDiscoveringIndex] = useState<number | null>(null);
  const [topicSuggestions, setTopicSuggestions] = useState<Record<number, string[]>>({});
  const [discoveryErrors, setDiscoveryErrors] = useState<Record<number, string>>({});

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

  const selectTopic = (index: number, topic: string) => {
    const updatedMappings = mappings.map((mapping, mappingIndex) => {
      if (mappingIndex !== index) return mapping;
      return {
        ...mapping,
        topic,
        device_id: mapping.device_id.trim() || suggestLoxDeviceId(topic),
      };
    });
    handleChange('mqtt_bridge', updatedMappings);
    setDiscoveryErrors(previous => ({ ...previous, [index]: '' }));
  };

  const discoverTopics = async (index: number) => {
    const prefix = getMqttDiscoveryPrefix(mappings[index].topic);
    if (!prefix) {
      setDiscoveryErrors(previous => ({
        ...previous,
        [index]: t('lox_config.mqtt_bridge_prefix_required'),
      }));
      return;
    }

    setDiscoveringIndex(index);
    setDiscoveryErrors(previous => ({ ...previous, [index]: '' }));
    try {
      const response = await axios.post<TopicDiscoveryResponse>(
        '/api/mqtt/topics/discover',
        { prefix },
      );
      const topics = response.data.topics;
      setTopicSuggestions(previous => ({ ...previous, [index]: topics }));
      if (topics.length === 0) {
        setDiscoveryErrors(previous => ({
          ...previous,
          [index]: t('lox_config.mqtt_bridge_no_topics'),
        }));
      }
    } catch {
      setTopicSuggestions(previous => ({ ...previous, [index]: [] }));
      setDiscoveryErrors(previous => ({
        ...previous,
        [index]: t('lox_config.mqtt_bridge_discovery_error'),
      }));
    } finally {
      setDiscoveringIndex(null);
    }
  };

  const addMapping = () => {
    handleChange('mqtt_bridge', [...mappings, { topic: '', device_id: '' }]);
  };

  const removeMapping = (index: number) => {
    handleChange('mqtt_bridge', mappings.filter((_, mappingIndex) => mappingIndex !== index));
    setTopicSuggestions({});
    setDiscoveryErrors({});
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
          const suggestions = topicSuggestions[index] ?? [];
          const deviceIdSuggestion = mapping.topic.trim().endsWith('/')
            ? ''
            : suggestLoxDeviceId(mapping.topic);

          return (
            <div key={index} className="rounded-box border border-base-300 bg-base-100 p-3">
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start">
                <div className="form-control">
                  <label className="label py-1">
                    <span className="label-text font-medium">{t('lox_config.mqtt_bridge_topic')}</span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      list={`mqtt-topic-suggestions-${index}`}
                      className={`input input-bordered min-w-0 flex-1 ${topicEmpty ? 'input-error' : ''}`}
                      value={mapping.topic}
                      onChange={(event) => {
                        const topic = event.target.value;
                        if (suggestions.includes(topic)) selectTopic(index, topic);
                        else updateMapping(index, 'topic', topic);
                      }}
                      placeholder="go-eCharger/408783/"
                      required
                    />
                    <datalist id={`mqtt-topic-suggestions-${index}`}>
                      {suggestions.map(topic => <option key={topic} value={topic} />)}
                    </datalist>
                    <button
                      type="button"
                      className="btn btn-outline px-3"
                      onClick={() => discoverTopics(index)}
                      disabled={discoveringIndex !== null}
                      title={t('lox_config.mqtt_bridge_discover')}
                      aria-label={t('lox_config.mqtt_bridge_discover')}
                    >
                      {discoveringIndex === index
                        ? <FaSpinner className="animate-spin" />
                        : <FaSearch />}
                    </button>
                  </div>
                  {topicEmpty && (
                    <HelpLabel className="[&>span]:text-error">
                      {t('lox_config.mqtt_bridge_required')}
                    </HelpLabel>
                  )}
                  {discoveryErrors[index] && (
                    <HelpLabel className="[&>span]:text-warning">
                      {discoveryErrors[index]}
                    </HelpLabel>
                  )}
                  {suggestions.length > 0 && (
                    <div className="mt-1 max-h-36 overflow-y-auto rounded-box border border-base-300 bg-base-200 p-1">
                      {suggestions.map(topic => (
                        <button
                          key={topic}
                          type="button"
                          className="btn btn-ghost btn-xs block h-auto w-full justify-start overflow-hidden text-ellipsis whitespace-nowrap text-left font-mono"
                          onClick={() => selectTopic(index, topic)}
                          title={topic}
                        >
                          {topic}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="form-control">
                  <label className="label py-1">
                    <span className="label-text font-medium">{t('lox_config.mqtt_bridge_device_id')}</span>
                  </label>
                  <input
                    type="text"
                    list={`lox-device-id-suggestions-${index}`}
                    className={`input input-bordered w-full ${deviceIdEmpty || deviceIdDuplicate ? 'input-error' : ''}`}
                    value={mapping.device_id}
                    onChange={(event) => updateMapping(index, 'device_id', event.target.value)}
                    placeholder="echarger_wh"
                    required
                  />
                  <datalist id={`lox-device-id-suggestions-${index}`}>
                    {deviceIdSuggestion && <option value={deviceIdSuggestion} />}
                  </datalist>
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
                  {deviceIdSuggestion && mapping.device_id !== deviceIdSuggestion && (
                    <button
                      type="button"
                      className="mt-1 w-fit text-left text-xs text-primary hover:underline"
                      onClick={() => updateMapping(index, 'device_id', deviceIdSuggestion)}
                    >
                      {t('lox_config.mqtt_bridge_use_suggestion', { device_id: deviceIdSuggestion })}
                    </button>
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
