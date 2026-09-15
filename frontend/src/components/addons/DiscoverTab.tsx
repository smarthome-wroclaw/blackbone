import { Download, ShieldCheck, TriangleAlert } from 'lucide-react';
import type { CatalogAddon } from '@/api/addons';

interface Props {
  addons: CatalogAddon[];
  onPreview: (addon: CatalogAddon) => void;
  labels: { empty: string; install: string; update: string; official: string; custom: string; incompatible: string; conflict: string };
}

export default function DiscoverTab({ addons, onPreview, labels }: Props) {
  if (addons.length === 0) return <div className="rounded-box border border-dashed border-base-300 p-8 text-center opacity-70">{labels.empty}</div>;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {addons.map(addon => (
        <article key={`${addon.repository_id}:${addon.id}`} className="card border border-base-300 bg-base-100 shadow-sm">
          <div className="card-body gap-3 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="card-title text-lg">{addon.name}</h2>
                <p className="font-mono text-xs opacity-60">{addon.id}</p>
              </div>
              <span className={`badge gap-1 ${addon.trust === 'official' ? 'badge-success' : 'badge-warning'}`}>
                {addon.trust === 'official' ? <ShieldCheck size={14} /> : <TriangleAlert size={14} />}
                {addon.trust === 'official' ? labels.official : labels.custom}
              </span>
            </div>
            <div className="flex flex-wrap gap-2 text-sm">
              <span className="badge badge-outline font-mono">v{addon.version}</span>
              <span className="badge badge-ghost">{addon.repository_name}</span>
              {!addon.compatible ? <span className="badge badge-error">{labels.incompatible}</span> : null}
              {addon.repository_conflict ? <span className="badge badge-error">{labels.conflict}</span> : null}
            </div>
            <div className="card-actions mt-1 justify-end">
              <button className="btn btn-primary min-h-11" disabled={!addon.compatible || addon.repository_conflict || (addon.installed && !addon.update_available)} onClick={() => onPreview(addon)}>
                <Download size={18} /> {addon.update_available ? labels.update : labels.install}
              </button>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
