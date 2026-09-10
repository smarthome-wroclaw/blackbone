import { FormEvent, useCallback, useEffect, useState } from 'react';
import { FaDownload, FaPuzzlePiece, FaTrash } from 'react-icons/fa';
import {
  AddonCatalogEntry,
  AddonRepository,
  InstalledAddon,
  addAddonRepository,
  getAddonCatalog,
  getAddons,
  installAddon,
  removeAddon,
  removeAddonRepository,
} from '@/api/addons';

type ViewData = { repositories: AddonRepository[]; installed: InstalledAddon[] };

export default function AddonsView() {
  const [data, setData] = useState<ViewData>({ repositories: [], installed: [] });
  const [catalog, setCatalog] = useState<AddonCatalogEntry[]>([]);
  const [registryErrors, setRegistryErrors] = useState<{ repository: string; error: string }[]>([]);
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [state, available] = await Promise.all([getAddons(), getAddonCatalog()]);
      setData(state.data);
      setCatalog(available.data.addons);
      setRegistryErrors(available.data.errors);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load add-ons');
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const run = useCallback(async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
    } catch (cause: unknown) {
      const detail = typeof cause === 'object' && cause && 'response' in cause
        ? (cause as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || (cause instanceof Error ? cause.message : 'The operation failed'));
    } finally {
      setBusy(null);
    }
  }, [load]);

  const submitRepository = (event: FormEvent) => {
    event.preventDefault();
    const url = repositoryUrl.trim();
    if (!url) return;
    void run('repository', async () => {
      await addAddonRepository(url);
      setRepositoryUrl('');
    });
  };

  return (
    <main className="mx-auto w-full max-w-6xl p-4 space-y-6">
      <header className="flex items-start gap-3">
        <div className="rounded-xl bg-primary/15 p-3 text-primary"><FaPuzzlePiece className="h-6 w-6" /></div>
        <div>
          <h1 className="text-2xl font-bold">Add-ons</h1>
          <p className="max-w-2xl text-sm text-base-content/70">Install validated Modbus device packs from repositories. Add-ons cannot run code or directly control hardware.</p>
        </div>
      </header>

      {error ? <div className="alert alert-error"><span>{error}</span></div> : null}
      {registryErrors.map((item) => <div className="alert alert-warning" key={item.repository}><span>{item.repository}: {item.error}</span></div>)}

      <section className="card border border-base-content/10 bg-base-100 shadow-sm">
        <div className="card-body gap-4">
          <div><h2 className="card-title">Discover</h2><p className="text-sm text-base-content/60">Compatible device definitions from enabled repositories.</p></div>
          {catalog.length === 0 ? <p className="text-sm text-base-content/60">Add a repository below to discover device packs.</p> : null}
          <div className="grid gap-3 md:grid-cols-2">
            {catalog.map((addon) => (
              <article className="rounded-xl border border-base-content/10 p-4" key={`${addon.repository}:${addon.id}:${addon.version}`}>
                <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{addon.name}</h3><p className="text-xs text-base-content/60">{addon.id} · v{addon.version}</p></div><span className={`badge badge-sm ${addon.trust === 'official' ? 'badge-success' : 'badge-warning'}`}>{addon.trust === 'official' ? 'Official' : 'Custom'}</span></div>
                {addon.summary ? <p className="mt-3 text-sm text-base-content/70">{addon.summary}</p> : null}
                <div className="mt-4 flex items-center justify-between gap-2">
                  <span className={`text-xs ${addon.compatible ? 'text-success' : 'text-error'}`}>{addon.compatible ? 'Compatible' : 'Incompatible'}</span>
                  <button className="btn btn-primary btn-sm" disabled={!addon.compatible || busy !== null} onClick={() => void run(`install:${addon.id}`, () => installAddon(addon.id, addon.repository, addon.version))}>
                    <FaDownload /> {addon.installed ? 'Update' : 'Install'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="card border border-base-content/10 bg-base-100 shadow-sm">
        <div className="card-body">
          <h2 className="card-title">Installed</h2>
          {data.installed.length === 0 ? <p className="text-sm text-base-content/60">No add-ons are installed.</p> : null}
          <div className="divide-y divide-base-content/10">
            {data.installed.map((addon) => <div className="flex items-center justify-between gap-4 py-3" key={addon.id}><div><p className="font-medium">{addon.name}</p><p className="text-xs text-base-content/60">v{addon.version} · {addon.files.length} device file{addon.files.length === 1 ? '' : 's'}</p></div><button className="btn btn-ghost btn-sm text-error" disabled={busy !== null} onClick={() => void run(`remove:${addon.id}`, () => removeAddon(addon.id))}><FaTrash /> Remove</button></div>)}
          </div>
        </div>
      </section>

      <section className="card border border-base-content/10 bg-base-100 shadow-sm">
        <div className="card-body gap-4">
          <div><h2 className="card-title">Repositories</h2><p className="text-sm text-base-content/60">Only HTTPS repositories are accepted. Custom repositories are not reviewed by BlackBone.</p></div>
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submitRepository}><input className="input input-bordered flex-1" type="url" placeholder="https://example.org/blackbone-addons" value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} required /><button className="btn btn-outline" disabled={busy !== null}>Add repository</button></form>
          <div className="divide-y divide-base-content/10">{data.repositories.map((repository) => <div className="flex items-center justify-between gap-3 py-3" key={repository.id}><div className="min-w-0"><p className="truncate text-sm">{repository.url}</p><span className="text-xs text-base-content/60">{repository.trust}</span></div>{repository.trust === 'custom' ? <button className="btn btn-ghost btn-sm text-error" disabled={busy !== null} onClick={() => void run(`repository:${repository.id}`, () => removeAddonRepository(repository.id))}><FaTrash /> Remove</button> : <span className="badge badge-success badge-sm">Official</span>}</div>)}</div>
        </div>
      </section>
    </main>
  );
}
