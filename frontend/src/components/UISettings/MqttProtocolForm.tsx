import { useTranslation } from '@/hooks/useTranslation';
import MqttForm from './MqttForm';

interface Props {
  data?: Record<string, unknown> & { enabled?: boolean };
  onChange: (data: Record<string, unknown> & { enabled?: boolean }) => void;
}

export default function MqttProtocolForm({ data, onChange }: Props) {
  const { t } = useTranslation();
  const enabled = data?.enabled !== false;

  return (
    <div className="space-y-4">
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={enabled}
            onChange={event => onChange({ ...data, enabled: event.target.checked })}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('messaging.enable_mqtt')}</span>
            <span className="label-text-alt text-base-content/60">{t('messaging.enable_mqtt_help')}</span>
          </div>
        </label>
      </div>
      {enabled ? (
        <MqttForm data={data} onChange={onChange} />
      ) : (
        <div className="alert"><span>{t('messaging.mqtt_disabled_info')}</span></div>
      )}
    </div>
  );
}
