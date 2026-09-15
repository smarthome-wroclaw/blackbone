import { History, Power, PowerOff, Trash2 } from 'lucide-react';
import type { InstalledAddon } from '@/api/addons';

interface Props {
  installed: Record<string, InstalledAddon>;
  onToggle: (id: string, enabled: boolean) => void;
  onRollback: (id: string) => void;
  onRemove: (id: string) => void;
  labels: { empty: string; enabled: string; disabled: string; enable: string; disable: string; rollback: string; remove: string };
}

export default function InstalledTab({ installed, onToggle, onRollback, onRemove, labels }: Props) {
  const entries = Object.entries(installed);
  if (entries.length === 0) return <div className="rounded-box border border-dashed border-base-300 p-8 text-center opacity-70">{labels.empty}</div>;
  return (
    <div className="overflow-x-auto rounded-box border border-base-300 bg-base-100">
      <table className="table">
        <thead><tr><th>Add-on</th><th>Version</th><th>Status</th><th className="text-right">Actions</th></tr></thead>
        <tbody>{entries.map(([id, addon]) => (
          <tr key={id}>
            <td><span className="font-medium">{id}</span><div className="text-xs opacity-60">{addon.files.length} files</div></td>
            <td className="font-mono">{addon.version}</td>
            <td><span className={`badge ${addon.enabled ? 'badge-success' : 'badge-ghost'}`}>{addon.enabled ? labels.enabled : labels.disabled}</span></td>
            <td><div className="flex justify-end gap-2">
              <button className="btn btn-sm min-h-11" onClick={() => onToggle(id, !addon.enabled)}>
                {addon.enabled ? <PowerOff size={17} /> : <Power size={17} />}{addon.enabled ? labels.disable : labels.enable}
              </button>
              <button className="btn btn-sm min-h-11" onClick={() => onRollback(id)}><History size={17} />{labels.rollback}</button>
              <button className="btn btn-sm btn-error btn-outline min-h-11" onClick={() => onRemove(id)}><Trash2 size={17} />{labels.remove}</button>
            </div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
