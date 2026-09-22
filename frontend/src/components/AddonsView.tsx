import { useCallback, useEffect, useState } from 'react';
import { isAxiosError } from 'axios';
import { Boxes, DatabaseZap, RefreshCw, ShieldCheck } from 'lucide-react';
import {
  addRepository,
  confirmPreview,
  getAddons,
  getCatalog,
  getSnapshots,
  previewAddon,
  refreshRepositories,
  removeAddon,
  removeRepository,
  rollbackAddon,
  toggleAddon,
  type AddonPreview,
  type AddonSnapshot,
  type AddonsState,
  type CatalogAddon,
} from '@/api/addons';
import { useTranslation } from '@/hooks/useTranslation';
import DiscoverTab from './addons/DiscoverTab';
import InstalledTab from './addons/InstalledTab';
import OperationDialog from './addons/OperationDialog';
import RepositoriesTab from './addons/RepositoriesTab';

type Tab = 'discover' | 'installed' | 'repositories';
const OPERATION_STORAGE_KEY = 'blackbone:addons:active-operation';

function errorMessage(error: unknown): string {
  if (isAxiosError<{ message?: string }>(error)) return error.response?.data?.message ?? error.message;
  return error instanceof Error ? error.message : 'Unexpected error';
}

export default function AddonsView() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('discover');
  const [state, setState] = useState<AddonsState | null>(null);
  const [catalog, setCatalog] = useState<CatalogAddon[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<AddonPreview | null>(null);
  const [operationId, setOperationId] = useState<string | null>(() => window.sessionStorage.getItem(OPERATION_STORAGE_KEY));
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [removeConfirmation, setRemoveConfirmation] = useState('');
  const [rollbackTarget, setRollbackTarget] = useState<{ id: string; snapshots: AddonSnapshot[] } | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextState, nextCatalog] = await Promise.all([getAddons(), getCatalog()]);
      setState(nextState); setCatalog(nextCatalog); setError(null);
    } catch (nextError) { setError(errorMessage(nextError)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try { await action(); setError(null); }
    catch (nextError) { setError(errorMessage(nextError)); }
    finally { setBusy(false); }
  };

  const trackOperation = (id: string) => {
    window.sessionStorage.setItem(OPERATION_STORAGE_KEY, id);
    setOperationId(id);
  };

  const labels = {
    discover: {
      empty: t('addons.empty_catalog'), install: t('addons.install'), update: t('addons.update'),
      official: t('addons.official'), custom: t('addons.custom'), incompatible: t('addons.incompatible'),
      conflict: t('addons.repository_conflict'),
    },
    installed: {
      empty: t('addons.empty_installed'), enabled: t('addons.enabled'), disabled: t('addons.disabled'),
      enable: t('addons.enable'), disable: t('addons.disable'), rollback: t('addons.rollback'), remove: t('addons.remove'),
    },
    repositories: {
      name: t('addons.repository_name'), url: t('addons.repository_url'), add: t('addons.add_repository'),
      official: t('addons.official'), custom: t('addons.custom'), offline: t('addons.offline'), remove: t('addons.remove'),
    },
  };

  if (loading) return <div className="flex min-h-[50vh] items-center justify-center"><span className="loading loading-spinner loading-lg text-primary" /></div>;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 p-4 sm:p-6">
      <header className="flex flex-col gap-4 border-b border-base-300 pb-5 md:flex-row md:items-end md:justify-between">
        <div><p className="mb-1 font-mono text-xs uppercase tracking-widest text-primary">{t('addons.eyebrow')}</p><h1 className="text-3xl font-semibold tracking-tight">{t('addons.title')}</h1><p className="mt-2 max-w-2xl opacity-70">{t('addons.description')}</p></div>
        <button className="btn btn-outline min-h-11" disabled={busy} onClick={() => void run(async () => { await refreshRepositories(); await load(); })}><RefreshCw size={18} className={busy ? 'animate-spin motion-reduce:animate-none' : ''} />{t('addons.refresh')}</button>
      </header>

      <section className="grid grid-cols-1 overflow-hidden rounded-box border border-base-300 bg-base-100 sm:grid-cols-3" aria-label={t('addons.safety_title')}>
        <div className="flex items-center gap-3 border-b border-base-300 p-3 sm:border-b-0 sm:border-r"><Boxes size={20} className="text-primary" /><span><strong className="block text-sm">{t('addons.data_only')}</strong><small className="opacity-60">{t('addons.no_code')}</small></span></div>
        <div className="flex items-center gap-3 border-b border-base-300 p-3 sm:border-b-0 sm:border-r"><ShieldCheck size={20} className="text-success" /><span><strong className="block text-sm">{t('addons.hash_pinned')}</strong><small className="opacity-60">SHA-256</small></span></div>
        <div className="flex items-center gap-3 p-3"><DatabaseZap size={20} className="text-info" /><span><strong className="block text-sm">{t('addons.rollback_ready')}</strong><small className="opacity-60">{t('addons.before_changes')}</small></span></div>
      </section>

      {error ? <div role="alert" className="alert alert-error"><span>{error}</span></div> : null}
      <div role="tablist" className="tabs tabs-box w-full sm:w-fit">
        {(['discover', 'installed', 'repositories'] as const).map(item => <button key={item} role="tab" className={`tab min-h-11 ${tab === item ? 'tab-active' : ''}`} aria-selected={tab === item} onClick={() => setTab(item)}>{t(`addons.tabs.${item}`)}</button>)}
      </div>

      {tab === 'discover' ? <DiscoverTab addons={catalog} onPreview={addon => void run(async () => setPreview(await previewAddon(addon, addon.update_available ? 'update' : 'install')))} labels={labels.discover} /> : null}
      {tab === 'installed' ? <InstalledTab installed={state?.installed ?? {}} onToggle={(id, enabled) => void run(async () => trackOperation(await toggleAddon(id, enabled)))} onRollback={id => void run(async () => setRollbackTarget({ id, snapshots: await getSnapshots(id) }))} onRemove={id => { setRemoveId(id); setRemoveConfirmation(''); }} labels={labels.installed} /> : null}
      {tab === 'repositories' ? <RepositoriesTab repositories={state?.repositories ?? []} onAdd={(name, url) => run(async () => { await addRepository(name, url); await load(); })} onRemove={id => run(async () => { await removeRepository(id); await load(); })} labels={labels.repositories} /> : null}

      {preview ? <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="preview-title"><div className="modal-box max-w-2xl"><h2 id="preview-title" className="text-xl font-semibold">{t('addons.preview_title')}</h2><p className="mt-2">{preview.name} <span className="font-mono">v{preview.version}</span></p>{preview.trust === 'custom' ? <div className="alert alert-warning my-4 text-sm"><span>{t('addons.custom_warning')}</span></div> : null}<p className="mt-4 text-sm font-medium">{t('addons.files')}</p><ul className="mt-2 space-y-1 rounded-box bg-base-200 p-3 font-mono text-xs">{preview.files.map(file => <li key={file.path} className="break-all">{file.path}<span className="block opacity-50">{file.sha256}</span></li>)}</ul><p className="mt-4 text-sm">{t('addons.capability_copy')}</p><div className="modal-action"><button className="btn min-h-11" onClick={() => setPreview(null)}>{t('addons.cancel')}</button><button className="btn btn-primary min-h-11" onClick={() => void run(async () => { const id = await confirmPreview(preview); setPreview(null); trackOperation(id); })}>{preview.action === 'install' ? t('addons.install') : t('addons.update')}</button></div></div><button className="modal-backdrop bg-black/50" aria-label={t('addons.cancel')} onClick={() => setPreview(null)} /></div> : null}

      {removeId ? <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="remove-title"><div className="modal-box"><h2 id="remove-title" className="text-xl font-semibold">{t('addons.remove_title')}</h2><p className="mt-2 text-sm opacity-75">{t('addons.type_to_confirm')} <code>{removeId}</code></p><label className="form-control mt-4"><span className="label-text mb-1">{t('addons.addon_id')}</span><input autoFocus className="input input-bordered font-mono" value={removeConfirmation} onChange={event => setRemoveConfirmation(event.target.value)} /></label><div className="modal-action"><button className="btn min-h-11" onClick={() => setRemoveId(null)}>{t('addons.cancel')}</button><button className="btn btn-error min-h-11" disabled={removeConfirmation !== removeId} onClick={() => void run(async () => { const id = await removeAddon(removeId); setRemoveId(null); trackOperation(id); })}>{t('addons.remove')}</button></div></div><div className="modal-backdrop bg-black/50" /></div> : null}
      {rollbackTarget ? <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="rollback-title"><div className="modal-box"><h2 id="rollback-title" className="text-xl font-semibold">{t('addons.rollback_title')}</h2><p className="mt-2 text-sm opacity-75">{rollbackTarget.id}</p>{rollbackTarget.snapshots.length === 0 ? <p className="my-6 rounded-box border border-dashed border-base-300 p-5 text-center opacity-70">{t('addons.no_snapshots')}</p> : <ul className="my-5 space-y-2">{rollbackTarget.snapshots.map(snapshot => <li key={snapshot.id} className="flex items-center justify-between gap-3 rounded-box border border-base-300 p-3"><time className="font-mono text-sm" dateTime={snapshot.created_at}>{new Date(snapshot.created_at).toLocaleString()}</time><button className="btn btn-sm min-h-11" onClick={() => void run(async () => { const id = await rollbackAddon(rollbackTarget.id, snapshot.id); setRollbackTarget(null); trackOperation(id); })}>{t('addons.restore')}</button></li>)}</ul>}<div className="modal-action"><button className="btn min-h-11" onClick={() => setRollbackTarget(null)}>{t('addons.cancel')}</button></div></div><button className="modal-backdrop bg-black/50" aria-label={t('addons.cancel')} onClick={() => setRollbackTarget(null)} /></div> : null}
      {operationId ? <OperationDialog operationId={operationId} title={t('addons.operation_title')} closeLabel={t('addons.close')} onClose={finished => { if (finished) { window.sessionStorage.removeItem(OPERATION_STORAGE_KEY); setOperationId(null); void load(); } }} /> : null}
    </main>
  );
}
