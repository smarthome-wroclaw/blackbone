/** Return a literal parent prefix suitable for scoped MQTT topic discovery. */
export function getMqttDiscoveryPrefix(topicOrPrefix: string): string {
  const value = topicOrPrefix.trim();
  if (!value) return '';
  if (value.endsWith('/')) return value;

  const lastSlash = value.lastIndexOf('/');
  return lastSlash >= 0 ? value.slice(0, lastSlash + 1) : `${value}/`;
}

function normalizeIdPart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
}

/** Build a readable default Loxone input ID from the root and leaf topic segments. */
export function suggestLoxDeviceId(topic: string): string {
  const segments = topic.split('/').map(segment => segment.trim()).filter(Boolean);
  if (segments.length === 0) return '';

  const leaf = normalizeIdPart(segments[segments.length - 1]);
  if (segments.length === 1) return leaf;

  const root = normalizeIdPart(segments[0].replace(/^go[-_]?/i, ''));
  if (!root || root === leaf) return leaf;
  return `${root}_${leaf}`;
}
