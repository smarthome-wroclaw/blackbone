import { useTranslation } from '@/hooks/useTranslation';
import { FaDownload, FaCopy, FaCheck, FaSave } from 'react-icons/fa';
import { DeviceConfig } from './types';

interface ActionsSectionProps {
  showPreview: boolean;
  setShowPreview: (value: boolean) => void;
  copied: boolean;
  isValid: boolean;
  generateJSON: () => DeviceConfig;
  onCopyJSON: () => void;
  onDownloadJSON: () => void;
  onSaveToDevice?: () => void;
  saving?: boolean;
  saveError?: string | null;
  saveWarning?: string | null;
  editingKey?: string | null;
}

export default function ActionsSection({
  showPreview,
  setShowPreview,
  copied,
  isValid,
  generateJSON,
  onCopyJSON,
  onDownloadJSON,
  onSaveToDevice,
  saving,
  saveError,
  saveWarning,
  editingKey,
}: ActionsSectionProps) {
  const { t } = useTranslation();

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <div className="flex flex-wrap gap-2 justify-between items-center">
          <div className="flex gap-2">
            <button
              className="btn btn-outline"
              onClick={() => setShowPreview(!showPreview)}
            >
              {showPreview ? t('modbus_creator.hide_preview') : t('modbus_creator.show_preview')}
            </button>
          </div>
          
          <div className="flex gap-2">
            <button
              className="btn btn-outline"
              onClick={onCopyJSON}
              disabled={!isValid}
            >
              {copied ? <FaCheck className="mr-1" /> : <FaCopy className="mr-1" />}
              {copied ? t('modbus_creator.copied') : t('modbus_creator.copy_json')}
            </button>
            <button
              className="btn btn-primary"
              onClick={onDownloadJSON}
              disabled={!isValid}
            >
              <FaDownload className="mr-1" /> {t('modbus_creator.download_json')}
            </button>
            {onSaveToDevice && <button className="btn btn-primary" onClick={onSaveToDevice} disabled={!isValid || saving}><FaSave className="mr-1" /> {saving ? t('modbus_creator.saving') : editingKey ? t('modbus_creator.update_on_device') : t('modbus_creator.save_to_device')}</button>}
          </div>
        </div>
        {saveError && <div className="alert alert-error mt-3"><span>{saveError}</span></div>}
        {saveWarning && <div className="alert alert-warning mt-3"><span>{saveWarning}</span></div>}
        
        {showPreview && (
          <div className="mt-4">
            <pre className="bg-base-300 p-4 rounded-lg overflow-auto max-h-96 text-sm">
              {JSON.stringify(generateJSON(), null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
