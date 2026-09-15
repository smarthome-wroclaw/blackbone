import { useState, type FormEvent } from 'react';
import { Plus, ShieldCheck, Trash2, TriangleAlert, WifiOff } from 'lucide-react';
import type { AddonRepository } from '@/api/addons';

interface Props {
  repositories: AddonRepository[];
  onAdd: (name: string, url: string) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  labels: { name: string; url: string; add: string; official: string; custom: string; offline: string; remove: string };
}

export default function RepositoriesTab({ repositories, onAdd, onRemove, labels }: Props) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onAdd(name, url);
    setName(''); setUrl('');
  };
  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="grid gap-3 rounded-box border border-base-300 bg-base-100 p-4 md:grid-cols-[1fr_2fr_auto] md:items-end">
        <label className="form-control"><span className="label-text mb-1">{labels.name}</span><input className="input input-bordered w-full" value={name} onChange={e => setName(e.target.value)} required /></label>
        <label className="form-control"><span className="label-text mb-1">{labels.url}</span><input className="input input-bordered w-full font-mono text-sm" type="url" pattern="https://.*" value={url} onChange={e => setUrl(e.target.value)} required /></label>
        <button className="btn btn-primary min-h-11" type="submit"><Plus size={18} />{labels.add}</button>
      </form>
      <div className="space-y-2">{repositories.map(repo => (
        <div key={repo.id} className="flex flex-col gap-3 rounded-box border border-base-300 bg-base-100 p-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2 font-medium">{repo.name}
            <span className={`badge gap-1 ${repo.trust === 'official' ? 'badge-success' : 'badge-warning'}`}>{repo.trust === 'official' ? <ShieldCheck size={13} /> : <TriangleAlert size={13} />}{repo.trust === 'official' ? labels.official : labels.custom}</span>
            {repo.offline ? <span className="badge badge-ghost gap-1"><WifiOff size={13} />{labels.offline}</span> : null}
          </div><p className="truncate font-mono text-xs opacity-60">{repo.url}</p></div>
          {repo.trust === 'custom' ? <button className="btn btn-outline btn-error min-h-11" onClick={() => void onRemove(repo.id)}><Trash2 size={17} />{labels.remove}</button> : null}
        </div>
      ))}</div>
    </div>
  );
}
