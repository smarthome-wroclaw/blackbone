import axios from '@/api/axios';
import type { DeviceConfig } from '@/components/ModbusDeviceCreator/types';
const MODEL_KEY_RE = /^[a-z0-9][a-z0-9_-]{1,63}$/;
export interface DefinitionSummary { key:string; source:'builtin'|'custom'|`addon:${string}`; model:string; manufacturer:string; description:string; category:string; default_address:number; default_update_interval:string; has_set_base:boolean; used_by:string[] }
export interface SaveResult { key:string; source:string; reloaded:string[]; warning:string|null }
export const isValidModelKey=(key:string)=>MODEL_KEY_RE.test(key);
export const listDefinitions=async():Promise<DefinitionSummary[]>=>(await axios.get('/api/modbus/device_definitions')).data.definitions;
export const getDefinition=async(key:string):Promise<{key:string;source:string;definition:DeviceConfig}> => (await axios.get(`/api/modbus/device_definitions/${key}`)).data;
export const createDefinition=async(key:string,definition:DeviceConfig):Promise<SaveResult> => (await axios.post('/api/modbus/device_definitions',{key,definition})).data;
export const updateDefinition=async(key:string,definition:DeviceConfig):Promise<SaveResult> => (await axios.put(`/api/modbus/device_definitions/${key}`,{definition})).data;
export const deleteDefinition=async(key:string):Promise<void> => { await axios.delete(`/api/modbus/device_definitions/${key}`); };
