/**
 * Section definitions for the settings editor.
 *
 * Sections are grouped by the question they answer, not by where their data
 * lives — see SETTINGS_IA.md. The old split put the password boneIO connects
 * with in Settings and the broker's own accounts in System, because one is in
 * config.yaml and the other is not. Nobody asks that question; they ask how to
 * change a password.
 *
 * Three lists, because "which group is it in" and "what does saving it cost"
 * are different facts:
 *
 *   RELOAD_SECTIONS   config.yaml, applied without a restart
 *   RESTART_SECTIONS  config.yaml, needs the app restarted — carries the badge
 *   SYSTEM_SECTIONS   acts on the operating system, takes effect at once
 *
 * Only the group decides where an entry appears. The lists decide whether
 * `requiresRestart` is true, which is what the badge and the save banner read.
 */

export interface SectionDefinition {
  name: string;
  icon: string;
  translationKey: string;
  /** Optional badge key (e.g. 'experimental') — shown next to section label. */
  badge?: string;
  /** Optional group tag for visual grouping in sidebar (e.g. 'remote', 'web'). */
  group?: string;
}

export type SectionGroup =
  | 'device'
  | 'control'
  | 'connections'
  | 'services'
  | 'access'
  | 'maintenance'
  | 'advanced';

/**
 * Groups in the order they appear in the sidebar, outermost concern first:
 * what the controller is, what it drives, what it talks to, what runs on it,
 * who may reach it, keeping it running, and the sharp tools.
 */
export const SECTION_GROUPS: { name: SectionGroup; icon: string; translationKey: string }[] = [
  { name: 'device', icon: '🔧', translationKey: 'settings.group_device' },
  { name: 'control', icon: '💡', translationKey: 'settings.group_control' },
  { name: 'connections', icon: '🔌', translationKey: 'settings.group_connections' },
  { name: 'services', icon: '📦', translationKey: 'settings.group_services' },
  { name: 'access', icon: '🛡️', translationKey: 'settings.group_access' },
  { name: 'maintenance', icon: '🧰', translationKey: 'settings.group_maintenance' },
  { name: 'advanced', icon: '⚙️', translationKey: 'settings.group_advanced' },
];

/**
 * Sections that only require reload (hot reload supported).
 * Changes to these sections can be applied without restarting the application.
 */
export const RELOAD_SECTIONS: SectionDefinition[] = [
  { name: 'areas', icon: '🏠', translationKey: 'sections.areas' },
  { name: 'local_inputs', icon: '📥', translationKey: 'sections.local_inputs' },
  { name: 'output', icon: '💡', translationKey: 'sections.output' },
  { name: 'output_group', icon: '🔗', translationKey: 'sections.output_group' },
  { name: 'cover', icon: '🚪', translationKey: 'sections.cover' },
  { name: 'modbus_devices', icon: '📱', translationKey: 'sections.modbus_devices' },
  { name: 'sensor', icon: '🌡️', translationKey: 'sections.sensor' },
  { name: 'adc', icon: '📊', translationKey: 'sections.adc' },
  { name: 'virtual_energy_sensor', icon: '⚡', translationKey: 'sections.virtual_energy_sensor' },
  { name: 'template', icon: '🧩', translationKey: 'sections.template' },
  { name: 'logger', icon: '📝', translationKey: 'sections.logger' },
  { name: 'oled', icon: '🖥️', translationKey: 'sections.oled' },
  { name: 'remote_devices', icon: '🌐', translationKey: 'sections.remote_devices', group: 'remote' },
  { name: 'remote_inputs', icon: '🔌', translationKey: 'sections.remote_inputs', group: 'remote' },
  { name: 'remote_outputs', icon: '📡', translationKey: 'sections.remote_outputs', group: 'remote' },
  { name: 'binding_matrix', icon: '📊', translationKey: 'sections.binding_matrix', group: 'tools' },
  { name: 'accounts', icon: '👥', translationKey: 'sections.accounts', group: 'web' },
];

/**
 * Sections that require full application restart.
 * Changes to these sections require restarting the application to take effect.
 */
export const RESTART_SECTIONS: SectionDefinition[] = [
  { name: 'boneio', icon: '🔧', translationKey: 'sections.boneio' },
  { name: 'mqtt', icon: '📡', translationKey: 'sections.mqtt' },
  { name: 'lox_udp', icon: '📨', translationKey: 'sections.lox_udp' },
  { name: 'web', icon: '🌐', translationKey: 'sections.web', group: 'web', badge: 'restart' },
  { name: 'modbus', icon: '🔌', translationKey: 'sections.modbus' },
  { name: 'can', icon: '🔗', translationKey: 'sections.can' },
  { name: 'mcp23017', icon: '🔗', translationKey: 'sections.mcp23017' },
  { name: 'board_sensors', icon: '🔌', translationKey: 'sections.board_sensors' },
];

/**
 * Sections that act on the operating system rather than on config.yaml.
 * These use the standalone section registry and take effect immediately.
 */
export const SYSTEM_SECTIONS: SectionDefinition[] = [
  { name: 'hostname', icon: '🏷️', translationKey: 'sections.hostname' },
  { name: 'timezone', icon: '🕓', translationKey: 'sections.timezone' },
  { name: 'mosquitto', icon: '📨', translationKey: 'sections.mosquitto' },
  { name: 'nodered_service', icon: '🔀', translationKey: 'sections.nodered_service' },
  { name: 'update', icon: '⬆️', translationKey: 'sections.update' },
  { name: 'backup', icon: '💾', translationKey: 'sections.backup' },
  { name: 'migrations', icon: '🧬', translationKey: 'sections.migrations' },
  { name: 'power', icon: '🔄', translationKey: 'sections.power' },
  { name: 'device_tools', icon: '🔬', translationKey: 'sections.device_tools' },
  { name: 'hardware_errors', icon: '⚠️', translationKey: 'sections.hardware_errors' },
  { name: 'factory_reset', icon: '♻️', translationKey: 'sections.factory_reset' },
];

/**
 * All config sections combined.
 */
export const ALL_SECTIONS: SectionDefinition[] = [
  ...RELOAD_SECTIONS,
  ...RESTART_SECTIONS,
  ...SYSTEM_SECTIONS,
];

/**
 * Sections that use ArrayTableWidget (array-based data).
 */
export const ARRAY_SECTIONS = [
  'local_inputs',
  'remote_inputs',
  'output',
  'output_group',
  'cover',
  'modbus_devices',
  'areas',
  'sensor',
  'virtual_energy_sensor',
  'remote_devices',
  'remote_outputs',
  'template',
  'adc',
  'board_sensors',
  'virtual_switch',
  'schedule',
] as const;

/**
 * Composite sections that combine multiple YAML keys into one UI section.
 * The key is the virtual section name, the value is an array of actual YAML keys.
 */
export const COMPOSITE_SECTIONS: Record<string, string[]> = {
  board_sensors: ['lm75', 'ina219', 'ina226', 'mcp9808'],
  local_inputs: ['binary_sensor', 'event'],
};

export type ArraySectionType = typeof ARRAY_SECTIONS[number];

/**
 * Check if a section is an array section.
 */
export function isArraySection(sectionName: string): sectionName is ArraySectionType {
  return ARRAY_SECTIONS.includes(sectionName as ArraySectionType);
}

/**
 * Check if a section requires restart.
 */
export function requiresRestart(sectionName: string): boolean {
  return RESTART_SECTIONS.some(s => s.name === sectionName);
}

/**
 * Get section definition by name.
 */
export function getSectionDefinition(sectionName: string): SectionDefinition | undefined {
  return ALL_SECTIONS.find(s => s.name === sectionName);
}
