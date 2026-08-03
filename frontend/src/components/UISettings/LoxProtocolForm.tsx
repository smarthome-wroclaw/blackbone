import { useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import LoxForm, { type LoxConfigData } from './LoxForm';

interface Props {
  data?: LoxConfigData;
  onChange: (data: LoxConfigData) => void;
  onValidationChange?: (isValid: boolean) => void;
}

export default function LoxProtocolForm({ data, onChange, onValidationChange }: Props) {
  const { t } = useTranslation();
  const enabled = data?.enabled === true;
  const handleValidation = useCallback(
    (isValid: boolean) => onValidationChange?.(isValid),
    [onValidationChange],
  );

  const setEnabled = (nextEnabled: boolean) => {
    if (nextEnabled) onChange({ ...(data || {}), enabled: true });
    else {
      onChange({ ...data, enabled: false });
      onValidationChange?.(true);
    }
  };

  return (
    <div className="space-y-4">
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={enabled}
            onChange={event => setEnabled(event.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('messaging.enable_lox')}</span>
            <span className="label-text-alt text-base-content/60">{t('messaging.enable_lox_help')}</span>
          </div>
        </label>
      </div>
      {enabled ? (
        <LoxForm data={data} onChange={onChange} onValidationChange={handleValidation} />
      ) : (
        <div className="alert"><span>{t('messaging.lox_disabled_info')}</span></div>
      )}
    </div>
  );
}
