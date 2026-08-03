import { useState } from 'react';
import {
  FaBoxOpen,
  FaCodeBranch,
  FaDownload,
  FaExclamationTriangle,
  FaSearch,
  FaSpinner,
} from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';

export type AlternativeUpdateSourceType = 'package' | 'repository';

export interface AlternativeUpdateRequest {
  source_type: AlternativeUpdateSourceType;
  source: string;
  source_version?: string;
}

interface PyPIVersion {
  version: string;
  prerelease: boolean;
  uploaded_at: string;
}

interface PyPIPackageInfo {
  status: 'success' | 'error';
  message?: string;
  package?: string;
  summary?: string;
  project_url?: string;
  latest?: string;
  latest_stable?: string;
  versions?: PyPIVersion[];
}

interface AlternativeUpdateSourceProps {
  isUpdating: boolean;
  onInstall: (request: AlternativeUpdateRequest) => Promise<void>;
}

const SOURCE_OPTIONS: Array<{
  type: AlternativeUpdateSourceType;
  icon: typeof FaBoxOpen;
  labelKey: string;
}> = [
  { type: 'package', icon: FaBoxOpen, labelKey: 'software_update.alternative_package' },
  { type: 'repository', icon: FaCodeBranch, labelKey: 'software_update.alternative_repository' },
];

export default function AlternativeUpdateSource({
  isUpdating,
  onInstall,
}: AlternativeUpdateSourceProps) {
  const { t } = useTranslation();
  const [sourceType, setSourceType] = useState<AlternativeUpdateSourceType>('package');
  const [source, setSource] = useState('');
  const [packageInfo, setPackageInfo] = useState<PyPIPackageInfo | null>(null);
  const [selectedVersion, setSelectedVersion] = useState('');
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [lookupError, setLookupError] = useState('');

  const normalizedSource = source.trim();
  const isRepository = sourceType === 'repository';
  const placeholder = isRepository
    ? 'https://github.com/example/blackbone.git@main'
    : 'blackbone';
  const canInstall = Boolean(
    normalizedSource
    && (isRepository || selectedVersion)
    && !isLookingUp
    && !isUpdating,
  );

  const clearPackageLookup = () => {
    setPackageInfo(null);
    setSelectedVersion('');
    setLookupError('');
  };

  const lookupPackage = async () => {
    if (!normalizedSource) return;
    setIsLookingUp(true);
    clearPackageLookup();
    try {
      const { data } = await axios.get<PyPIPackageInfo>('/api/update/pypi-versions', {
        params: { package: normalizedSource },
      });
      if (data.status !== 'success' || !data.versions?.length) {
        setLookupError(data.message || t('software_update.alternative_lookup_failed'));
        return;
      }
      setPackageInfo(data);
      setSelectedVersion(data.latest_stable || data.latest || data.versions[0].version);
    } catch {
      setLookupError(t('software_update.alternative_lookup_failed'));
    } finally {
      setIsLookingUp(false);
    }
  };

  const handleInstall = async () => {
    if (!canInstall) return;
    const target = isRepository
      ? normalizedSource
      : `${normalizedSource}==${selectedVersion}`;
    if (!window.confirm(t('software_update.alternative_confirm', { source: target }))) {
      return;
    }
    await onInstall({
      source_type: sourceType,
      source: normalizedSource,
      source_version: isRepository ? undefined : selectedVersion,
    });
  };

  return (
    <section className="rounded-box border border-dashed border-primary/40 bg-base-100/45 p-4 sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="card-title text-lg">{t('software_update.alternative_title')}</h3>
          <p className="mt-1 text-sm text-base-content/65">
            {t('software_update.alternative_description')}
          </p>
        </div>
        <span className="badge badge-outline badge-primary shrink-0">
          {t('software_update.alternative_one_off')}
        </span>
      </div>

      <div className="mt-4 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,1.35fr)]">
        <div className="min-w-0">
          <label className="label pt-0">
            <span className="label-text font-medium">
              {t('software_update.alternative_source_type')}
            </span>
          </label>
          <div className="join grid grid-cols-2" role="group">
            {SOURCE_OPTIONS.map(option => {
              const Icon = option.icon;
              const selected = sourceType === option.type;
              return (
                <button
                  key={option.type}
                  type="button"
                  className={`btn join-item ${selected ? 'btn-primary' : 'btn-outline'}`}
                  aria-pressed={selected}
                  onClick={() => {
                    setSourceType(option.type);
                    setSource('');
                    clearPackageLookup();
                  }}
                  disabled={isUpdating}
                >
                  <Icon />
                  {t(option.labelKey)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="min-w-0">
          <label className="label pt-0" htmlFor="alternative-update-source">
            <span className="label-text font-medium">
              {isRepository
                ? t('software_update.alternative_repository_label')
                : t('software_update.alternative_package_label')}
            </span>
          </label>
          <div className="flex gap-2">
            <input
              id="alternative-update-source"
              type="text"
              className="input input-bordered min-w-0 flex-1 font-mono"
              value={source}
              onChange={event => {
                setSource(event.target.value);
                clearPackageLookup();
              }}
              onKeyDown={event => {
                if (!isRepository && event.key === 'Enter') {
                  event.preventDefault();
                  void lookupPackage();
                }
              }}
              placeholder={placeholder}
              autoComplete="off"
              spellCheck={false}
              disabled={isUpdating}
            />
            {!isRepository && (
              <button
                type="button"
                className="btn btn-primary shrink-0"
                onClick={() => void lookupPackage()}
                disabled={!normalizedSource || isLookingUp || isUpdating}
              >
                {isLookingUp ? <FaSpinner className="animate-spin" /> : <FaSearch />}
                <span className="hidden sm:inline">
                  {t('software_update.alternative_check_versions')}
                </span>
              </button>
            )}
          </div>
          <p className="mt-1.5 text-xs text-base-content/55">
            {isRepository
              ? t('software_update.alternative_repository_help')
              : t('software_update.alternative_package_help')}
          </p>
          {lookupError && <p className="mt-2 text-sm text-error">{lookupError}</p>}
        </div>
      </div>

      {!isRepository && packageInfo?.versions && (
        <div className="mt-4 grid gap-3 rounded-lg border border-base-300 bg-base-200/60 p-3 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,0.45fr)] sm:items-end">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono font-semibold">{packageInfo.package || normalizedSource}</span>
              {packageInfo.latest_stable && (
                <span className="badge badge-success badge-sm">
                  {t('software_update.alternative_latest_stable')}: {packageInfo.latest_stable}
                </span>
              )}
            </div>
            {packageInfo.summary && (
              <p className="mt-1 truncate text-sm text-base-content/60" title={packageInfo.summary}>
                {packageInfo.summary}
              </p>
            )}
          </div>
          <div>
            <label className="label py-0.5" htmlFor="alternative-update-version">
              <span className="label-text text-xs">
                {t('software_update.alternative_select_version')}
              </span>
            </label>
            <select
              id="alternative-update-version"
              className="select select-bordered select-sm w-full font-mono"
              value={selectedVersion}
              onChange={event => setSelectedVersion(event.target.value)}
              disabled={isUpdating}
            >
              {packageInfo.versions.map(version => (
                <option key={version.version} value={version.version}>
                  {version.version}{version.prerelease ? ' (dev)' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-2 text-sm text-warning">
          <FaExclamationTriangle className="mt-0.5 shrink-0" />
          <span>{t('software_update.alternative_warning')}</span>
        </div>
        <button
          type="button"
          className="btn btn-warning shrink-0"
          onClick={() => void handleInstall()}
          disabled={!canInstall}
        >
          <FaDownload />
          {isUpdating
            ? t('software_update.updating')
            : t('software_update.alternative_install')}
        </button>
      </div>
    </section>
  );
}
