import { useMemo, useState } from 'react';
import { FaCheck, FaMicrochip, FaPlus, FaSearch, FaSpinner, FaTrash } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
import {
  getMqttTopicLeaf,
  groupDiscoveredTopicsByDevice,
  groupMqttBridgeMappings,
  suggestGroupedLoxDeviceId,
} from './helpers/loxMqttBridge';

export interface LoxMqttBridgeMapping {
  topic: string;
  device_id: string;
}

interface TopicDiscoveryResponse {
  prefix: string;
  topics: string[];
}

interface Props {
  mappings: LoxMqttBridgeMapping[];
  deviceIdCounts: Record<string, number>;
  onChange: (mappings: LoxMqttBridgeMapping[]) => void;
}

function uniqueId(suggestion: string, usedIds: Set<string>): string {
  let candidate = suggestion || 'mqtt_input';
  let suffix = 2;
  while (usedIds.has(candidate)) {
    candidate = `${suggestion || 'mqtt_input'}_${suffix}`;
    suffix += 1;
  }
  usedIds.add(candidate);
  return candidate;
}

export default function MqttDeviceGroups({ mappings, deviceIdCounts, onChange }: Props) {
  const { t } = useTranslation();
  const [prefix, setPrefix] = useState('');
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState('');
  const [discoveredTopics, setDiscoveredTopics] = useState<string[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set());
  const mappingGroups = useMemo(() => groupMqttBridgeMappings(mappings), [mappings]);
  const discoveredGroups = useMemo(
    () => groupDiscoveredTopicsByDevice(discoveredTopics),
    [discoveredTopics],
  );
  const mappedTopics = useMemo(
    () => new Set(mappings.map(mapping => mapping.topic.trim()).filter(Boolean)),
    [mappings],
  );

  const discoverDevices = async () => {
    const normalizedPrefix = prefix.trim();
    if (!normalizedPrefix) {
      setDiscoveryError(t('lox_config.mqtt_device_prefix_required'));
      return;
    }
    setIsDiscovering(true);
    setDiscoveryError('');
    try {
      const response = await axios.post<TopicDiscoveryResponse>(
        '/api/mqtt/topics/discover',
        { prefix: normalizedPrefix },
      );
      const topics = response.data.topics;
      setDiscoveredTopics(topics);
      setSelectedTopics(new Set(topics.filter(topic => !mappedTopics.has(topic))));
      if (topics.length === 0) setDiscoveryError(t('lox_config.mqtt_bridge_no_topics'));
    } catch {
      setDiscoveredTopics([]);
      setSelectedTopics(new Set());
      setDiscoveryError(t('lox_config.mqtt_bridge_discovery_error'));
    } finally {
      setIsDiscovering(false);
    }
  };

  const toggleTopic = (topic: string) => {
    if (mappedTopics.has(topic)) return;
    setSelectedTopics(previous => {
      const next = new Set(previous);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  };

  const toggleDevice = (topics: string[]) => {
    const available = topics.filter(topic => !mappedTopics.has(topic));
    const allSelected = available.length > 0 && available.every(topic => selectedTopics.has(topic));
    setSelectedTopics(previous => {
      const next = new Set(previous);
      available.forEach(topic => {
        if (allSelected) next.delete(topic);
        else next.add(topic);
      });
      return next;
    });
  };

  const addDeviceTopics = (topics: string[]) => {
    const topicsToAdd = topics.filter(topic => selectedTopics.has(topic) && !mappedTopics.has(topic));
    if (topicsToAdd.length === 0) return;
    const usedIds = new Set(mappings.map(mapping => mapping.device_id.trim()).filter(Boolean));
    const additions = topicsToAdd.map(topic => ({
      topic,
      device_id: uniqueId(suggestGroupedLoxDeviceId(topic), usedIds),
    }));
    onChange([...mappings, ...additions]);
    setSelectedTopics(previous => {
      const next = new Set(previous);
      topicsToAdd.forEach(topic => next.delete(topic));
      return next;
    });
  };

  const updateMapping = (index: number, field: keyof LoxMqttBridgeMapping, value: string) => {
    onChange(mappings.map((mapping, mappingIndex) => (
      mappingIndex === index ? { ...mapping, [field]: value } : mapping
    )));
  };

  const removeMapping = (index: number) => {
    onChange(mappings.filter((_, mappingIndex) => mappingIndex !== index));
  };

  const removeGroup = (indices: number[]) => {
    const removed = new Set(indices);
    onChange(mappings.filter((_, index) => !removed.has(index)));
  };

  return (
    <div className="space-y-4">
      <div className="rounded-box border border-primary/30 bg-primary/5 p-4">
        <div className="mb-3 flex items-start gap-3">
          <div className="rounded-lg bg-primary/15 p-2 text-primary"><FaMicrochip /></div>
          <div>
            <h3 className="font-semibold">{t('lox_config.mqtt_device_add')}</h3>
            <p className="text-sm text-base-content/65">{t('lox_config.mqtt_device_add_help')}</p>
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            className="input input-bordered min-w-0 flex-1 font-mono"
            value={prefix}
            onChange={event => setPrefix(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void discoverDevices();
              }
            }}
            placeholder="go-eCharger/408783/"
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void discoverDevices()}
            disabled={isDiscovering}
          >
            {isDiscovering ? <FaSpinner className="animate-spin" /> : <FaSearch />}
            {t('lox_config.mqtt_device_discover')}
          </button>
        </div>
        {discoveryError && (
          <HelpLabel className="[&>span]:text-warning">{discoveryError}</HelpLabel>
        )}
      </div>

      {discoveredGroups.map(group => {
        const available = group.topics.filter(topic => !mappedTopics.has(topic));
        const selectedCount = available.filter(topic => selectedTopics.has(topic)).length;
        const allSelected = available.length > 0 && selectedCount === available.length;
        return (
          <div key={group.devicePrefix} className="overflow-hidden rounded-box border border-base-300 bg-base-100">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-base-300 bg-base-200/60 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate font-mono font-semibold" title={group.devicePrefix}>
                  {group.devicePrefix}
                </div>
                <div className="text-xs text-base-content/60">
                  {t('lox_config.mqtt_device_topics_found', { count: group.topics.length })}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" className="btn btn-ghost btn-xs" onClick={() => toggleDevice(group.topics)}>
                  <FaCheck /> {allSelected ? t('lox_config.mqtt_device_clear') : t('lox_config.mqtt_device_select_all')}
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={selectedCount === 0}
                  onClick={() => addDeviceTopics(group.topics)}
                >
                  <FaPlus /> {t('lox_config.mqtt_device_add_selected', { count: selectedCount })}
                </button>
              </div>
            </div>
            <div className="grid max-h-72 gap-px overflow-y-auto bg-base-300 sm:grid-cols-2">
              {group.topics.map(topic => {
                const isMapped = mappedTopics.has(topic);
                const checked = isMapped || selectedTopics.has(topic);
                return (
                  <label
                    key={topic}
                    className={`flex min-w-0 items-center gap-3 bg-base-100 px-3 py-2 text-sm ${isMapped ? 'opacity-55' : 'cursor-pointer hover:bg-base-200'}`}
                  >
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary checkbox-sm"
                      checked={checked}
                      disabled={isMapped}
                      onChange={() => toggleTopic(topic)}
                    />
                    <span className="min-w-0 flex-1 truncate font-mono" title={topic}>{getMqttTopicLeaf(topic)}</span>
                    {isMapped && <span className="badge badge-ghost badge-sm">{t('lox_config.mqtt_device_added')}</span>}
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}

      {mappingGroups.map(group => {
        const indices = group.mappings.map(item => item.index);
        return (
          <details key={group.devicePrefix || `manual-${indices[0]}`} open className="group rounded-box border border-base-300 bg-base-100">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-box px-4 py-3 hover:bg-base-200/60">
              <div className="min-w-0">
                <div className="truncate font-mono font-semibold">
                  {group.devicePrefix || t('lox_config.mqtt_device_manual')}
                </div>
                <div className="text-xs text-base-content/60">
                  {t('lox_config.mqtt_device_inputs_configured', { count: group.mappings.length })}
                </div>
              </div>
              <span className="badge badge-outline">{group.mappings.length}</span>
            </summary>
            <div className="border-t border-base-300 p-3">
              <div className="mb-2 flex justify-end">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs text-error"
                  onClick={() => removeGroup(indices)}
                >
                  <FaTrash /> {t('lox_config.mqtt_device_remove')}
                </button>
              </div>
              <div className="space-y-2">
                {group.mappings.map(({ index, mapping }) => {
                  const topicEmpty = !mapping.topic.trim();
                  const deviceIdEmpty = !mapping.device_id.trim();
                  const duplicate = !deviceIdEmpty && deviceIdCounts[mapping.device_id.trim()] > 1;
                  return (
                    <div key={index} className="grid gap-2 rounded-lg bg-base-200/50 p-2 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
                      <input
                        type="text"
                        className={`input input-bordered input-sm min-w-0 font-mono ${topicEmpty ? 'input-error' : ''}`}
                        value={mapping.topic}
                        onChange={event => updateMapping(index, 'topic', event.target.value)}
                        aria-label={t('lox_config.mqtt_bridge_topic')}
                      />
                      <input
                        type="text"
                        className={`input input-bordered input-sm min-w-0 font-mono ${deviceIdEmpty || duplicate ? 'input-error' : ''}`}
                        value={mapping.device_id}
                        onChange={event => updateMapping(index, 'device_id', event.target.value)}
                        aria-label={t('lox_config.mqtt_bridge_device_id')}
                      />
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm text-error"
                        onClick={() => removeMapping(index)}
                        aria-label={t('lox_config.mqtt_bridge_remove')}
                      >
                        <FaTrash />
                      </button>
                      {duplicate && (
                        <div className="text-xs text-error sm:col-span-3">{t('lox_config.mqtt_bridge_duplicate_device_id')}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </details>
        );
      })}

      <button
        type="button"
        className="btn btn-outline btn-sm"
        onClick={() => onChange([...mappings, { topic: '', device_id: '' }])}
      >
        <FaPlus /> {t('lox_config.mqtt_bridge_add')}
      </button>
      <HelpLabel>{t('lox_config.mqtt_bridge_help')}</HelpLabel>
    </div>
  );
}
