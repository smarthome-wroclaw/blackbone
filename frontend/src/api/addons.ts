import axios from '@/api/axios';

export type RepositoryTrust = 'official' | 'custom';
export type OperationStage = 'pending' | 'downloading' | 'validating' | 'applying' | 'reloading' | 'rolling_back' | 'succeeded' | 'failed' | 'interrupted';

export interface AddonRepository {
  id: string;
  name: string;
  url: string;
  trust: RepositoryTrust;
  enabled: boolean;
  offline: boolean;
}

export interface InstalledAddon {
  version: string;
  repository_id: string;
  manifest_sha256: string;
  enabled: boolean;
  installed_at: string;
  files: string[];
  last_operation_id: string;
}

export interface AddonsState {
  health: 'ok' | 'recovery_required';
  repositories: AddonRepository[];
  installed: Record<string, InstalledAddon>;
  updates: string[];
}

export interface CatalogAddon {
  id: string;
  name: string;
  version: string;
  repository_id: string;
  repository_name: string;
  trust: RepositoryTrust;
  compatible: boolean;
  repository_offline: boolean;
  installed: boolean;
  enabled: boolean;
  installed_version: string | null;
  update_available: boolean;
  repository_conflict: boolean;
}

export interface AddonPreview {
  id: string;
  name: string;
  version: string;
  action: 'install' | 'update' | 'downgrade';
  repository_id: string;
  trust: RepositoryTrust;
  files: Array<{ path: string; sha256: string }>;
  models: string[];
  confirmation_token: string;
  expires_at: number;
}

export interface AddonOperation {
  id: string;
  addon_id: string;
  stage: OperationStage;
  message: string;
  validation_errors: Array<{ code: string; message: string; file?: string; model?: string }>;
  completed_at: string | null;
}

export interface AddonSnapshot {
  id: string;
  operation_id: string;
  created_at: string;
}

export const getAddons = async (): Promise<AddonsState> => (await axios.get<AddonsState>('/api/addons')).data;
export const getCatalog = async (): Promise<CatalogAddon[]> => (await axios.get<{ addons: CatalogAddon[] }>('/api/addons/catalog')).data.addons;
export const refreshRepositories = async (): Promise<void> => { await axios.post('/api/addons/refresh'); };
export const addRepository = async (name: string, url: string): Promise<void> => { await axios.post('/api/addons/repositories', { name, url }); };
export const removeRepository = async (id: string): Promise<void> => { await axios.delete(`/api/addons/repositories/${encodeURIComponent(id)}`); };
export const previewAddon = async (addon: CatalogAddon, action: AddonPreview['action']): Promise<AddonPreview> => (
  await axios.post<AddonPreview>(`/api/addons/${encodeURIComponent(addon.id)}/preview`, {
    repository_id: addon.repository_id,
    version: addon.version,
    action,
  })
).data;
export const confirmPreview = async (preview: AddonPreview): Promise<string> => (
  await axios.post<{ operation_id: string }>(
    `/api/addons/${encodeURIComponent(preview.id)}/${preview.action === 'install' ? 'install' : 'update'}`,
    { confirmation_token: preview.confirmation_token },
  )
).data.operation_id;
export const toggleAddon = async (id: string, enabled: boolean): Promise<string> => (
  await axios.post<{ operation_id: string }>(`/api/addons/${encodeURIComponent(id)}/${enabled ? 'enable' : 'disable'}`)
).data.operation_id;
export const removeAddon = async (id: string): Promise<string> => (
  await axios.delete<{ operation_id: string }>(`/api/addons/${encodeURIComponent(id)}`, { data: { confirmation: id } })
).data.operation_id;
export const getOperation = async (id: string): Promise<AddonOperation> => (
  await axios.get<AddonOperation>(`/api/addons/operations/${encodeURIComponent(id)}`)
).data;
export const getSnapshots = async (id: string): Promise<AddonSnapshot[]> => (
  await axios.get<{ snapshots: AddonSnapshot[] }>(`/api/addons/${encodeURIComponent(id)}/snapshots`)
).data.snapshots;
export const rollbackAddon = async (id: string, snapshotId: string): Promise<string> => (
  await axios.post<{ operation_id: string }>(`/api/addons/${encodeURIComponent(id)}/rollback`, {
    snapshot_id: snapshotId,
  })
).data.operation_id;
