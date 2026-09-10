import axios from './axios';

export interface AddonCatalogEntry {
  id: string;
  name: string;
  summary?: string;
  version: string;
  type: 'modbus_device_pack';
  repository: string;
  trust: 'official' | 'custom';
  compatible: boolean;
  installed: boolean;
  installed_version: string | null;
}

export interface InstalledAddon {
  id: string;
  name: string;
  version: string;
  type: string;
  repository: string;
  installed_at: string;
  enabled: boolean;
  files: string[];
}

export interface AddonRepository {
  id: string;
  url: string;
  trust: 'official' | 'custom';
  enabled: boolean;
}

export const getAddons = () => axios.get<{ repositories: AddonRepository[]; installed: InstalledAddon[] }>('/api/addons');
export const getAddonCatalog = () => axios.get<{ addons: AddonCatalogEntry[]; errors: { repository: string; error: string }[] }>('/api/addons/catalog');
export const addAddonRepository = (url: string) => axios.post<AddonRepository>('/api/addons/repositories', { url });
export const removeAddonRepository = (id: string) => axios.delete(`/api/addons/repositories/${id}`);
export const installAddon = (id: string, repository: string, version: string) => axios.post(`/api/addons/${id}/install`, { repository, version });
export const removeAddon = (id: string) => axios.delete(`/api/addons/${id}`);
