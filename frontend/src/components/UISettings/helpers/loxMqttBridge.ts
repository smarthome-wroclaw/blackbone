/** Return a literal parent prefix suitable for scoped MQTT topic discovery. */
export function getMqttDiscoveryPrefix(topicOrPrefix: string): string {
  const value = topicOrPrefix.trim();
  if (!value) return '';
  if (value.endsWith('/')) return value;

  const lastSlash = value.lastIndexOf('/');
  // A root-level fragment (for example "go") is not yet a complete MQTT
  // topic level. Keep it literal so the backend can scan root topics and
  // filter the results by that fragment.
  return lastSlash >= 0 ? value.slice(0, lastSlash + 1) : value;
}

function normalizeIdPart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
}

export interface MqttBridgeMappingLike {
  topic: string;
  device_id: string;
}

export interface MqttDeviceGroup<T extends MqttBridgeMappingLike = MqttBridgeMappingLike> {
  devicePrefix: string;
  mappings: Array<{ index: number; mapping: T }>;
}

/** Return the parent topic path that identifies an MQTT device. */
export function getMqttDevicePrefix(topic: string): string {
  const value = topic.trim().replace(/\/+$/, '');
  if (!value) return '';
  const lastSlash = value.lastIndexOf('/');
  return lastSlash >= 0 ? value.slice(0, lastSlash) : value;
}

/** Return the part of a topic below its device prefix. */
export function getMqttTopicLeaf(topic: string): string {
  const value = topic.trim().replace(/\/+$/, '');
  const lastSlash = value.lastIndexOf('/');
  return lastSlash >= 0 ? value.slice(lastSlash + 1) : value;
}

/** Group concrete MQTT topics by their parent device prefix. */
export function groupDiscoveredTopicsByDevice(topics: string[]): Array<{
  devicePrefix: string;
  topics: string[];
}> {
  const groups = new Map<string, string[]>();
  for (const topic of [...new Set(topics)].sort()) {
    const devicePrefix = getMqttDevicePrefix(topic);
    if (!devicePrefix) continue;
    const group = groups.get(devicePrefix) ?? [];
    group.push(topic);
    groups.set(devicePrefix, group);
  }
  return [...groups.entries()].map(([devicePrefix, groupedTopics]) => ({
    devicePrefix,
    topics: groupedTopics,
  }));
}

/** Group configured flat mappings without changing the persisted YAML shape. */
export function groupMqttBridgeMappings<T extends MqttBridgeMappingLike>(
  mappings: T[],
): MqttDeviceGroup<T>[] {
  const groups = new Map<string, MqttDeviceGroup<T>>();
  mappings.forEach((mapping, index) => {
    const prefix = getMqttDevicePrefix(mapping.topic);
    const key = prefix || `__manual_${index}`;
    const group = groups.get(key) ?? { devicePrefix: prefix, mappings: [] };
    group.mappings.push({ index, mapping });
    groups.set(key, group);
  });
  return [...groups.values()];
}

/** Build a globally unique Lox input ID from every topic segment. */
export function suggestGroupedLoxDeviceId(topic: string): string {
  const segments = topic.split('/').map(segment => segment.trim()).filter(Boolean);
  if (segments.length === 0) return '';
  return segments
    .map((segment, index) => normalizeIdPart(index === 0 ? segment.replace(/^go[-_]?/i, '') : segment))
    .filter(Boolean)
    .join('_');
}

/** Build a readable default Lox input ID from the root and leaf topic segments. */
export function suggestLoxDeviceId(topic: string): string {
  const segments = topic.split('/').map(segment => segment.trim()).filter(Boolean);
  if (segments.length === 0) return '';

  const leaf = normalizeIdPart(segments[segments.length - 1]);
  if (segments.length === 1) return leaf;

  const root = normalizeIdPart(segments[0].replace(/^go[-_]?/i, ''));
  if (!root || root === leaf) return leaf;
  return `${root}_${leaf}`;
}
