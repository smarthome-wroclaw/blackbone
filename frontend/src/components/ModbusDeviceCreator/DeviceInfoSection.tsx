import { useTranslation } from '@/hooks/useTranslation';
import { CATEGORIES } from './types';
import { NumericInput } from '@/components/ui/NumericInput';

interface DeviceInfoSectionProps {
  modelName: string;
  setModelName: (value: string) => void;
  fileName: string;
  setFileName: (value: string) => void;
  category: string;
  setCategory: (value: string) => void;
  manufacturer: string; setManufacturer: (value: string) => void;
  description: string; setDescription: (value: string) => void;
  defaultAddress: number; setDefaultAddress: (value: number) => void;
  defaultUpdateInterval: string; setDefaultUpdateInterval: (value: string) => void;
  testDeviceAddress: number;
  setTestDeviceAddress: (value: number) => void;
}

export default function DeviceInfoSection({
  modelName,
  setModelName,
  fileName,
  setFileName,
  category,
  setCategory,
  manufacturer, setManufacturer, description, setDescription, defaultAddress, setDefaultAddress, defaultUpdateInterval, setDefaultUpdateInterval,
  testDeviceAddress,
  setTestDeviceAddress,
}: DeviceInfoSectionProps) {
  const { t } = useTranslation();

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h3 className="card-title text-lg">{t('modbus_creator.device_info')}</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="form-control">
            <label className="label">
              <span className="label-text">{t('modbus_creator.model_name')} *</span>
            </label>
            <input
              type="text"
              className="input input-bordered"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="SHT30 Temp and Humidity sensor"
            />
          </div>
          
          <div className="form-control">
            <label className="label">
              <span className="label-text">{t('modbus_creator.file_name')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered"
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              placeholder="sht30"
            />
          </div>
          
          <div className="form-control">
            <label className="label">
              <span className="label-text">{t('modbus_creator.category')}</span>
            </label>
            <select
              className="select select-bordered"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map(cat => (
                <option key={cat.value} value={cat.value}>{cat.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <label className="form-control"><span className="label-text">{t('modbus_creator.manufacturer')}</span><input className="input input-bordered" value={manufacturer} onChange={e => setManufacturer(e.target.value)} /></label>
          <label className="form-control"><span className="label-text">{t('modbus_creator.description')}</span><input className="input input-bordered" value={description} onChange={e => setDescription(e.target.value)} /></label>
          <label className="form-control"><span className="label-text">{t('modbus_creator.default_address')}</span><NumericInput value={defaultAddress} onChange={v => setDefaultAddress(v === '' ? 1 : v)} min={1} max={247} /></label>
          <label className="form-control"><span className="label-text">{t('modbus_creator.default_update_interval')}</span><input className="input input-bordered" value={defaultUpdateInterval} onChange={e => setDefaultUpdateInterval(e.target.value)} /></label>
        </div>
        
        <div className="form-control mt-2">
          <label className="label">
            <span className="label-text">{t('modbus_creator.test_device_address')}</span>
            <span className="label-text-alt">{t('modbus_creator.test_device_hint')}</span>
          </label>
          <NumericInput
            className="w-32"
            value={testDeviceAddress}
            onChange={(v) => setTestDeviceAddress(v === '' ? 1 : v)}
            min={1}
            max={247}
          />
        </div>
      </div>
    </div>
  );
}
