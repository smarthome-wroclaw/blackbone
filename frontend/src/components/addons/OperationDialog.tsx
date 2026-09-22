import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, LoaderCircle, TriangleAlert } from 'lucide-react';
import { getOperation, type AddonOperation } from '@/api/addons';

const FINAL = new Set(['succeeded', 'failed', 'interrupted']);

interface Props { operationId: string; onClose: (finished: boolean) => void; closeLabel: string; title: string; }

export default function OperationDialog({ operationId, onClose, closeLabel, title }: Props) {
  const [operation, setOperation] = useState<AddonOperation | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getOperation(operationId);
        if (!active) return;
        setOperation(next);
        if (!FINAL.has(next.stage)) timer = window.setTimeout(poll, 800);
      } catch {
        if (active) timer = window.setTimeout(poll, 1500);
      }
    };
    void poll();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [operationId]);
  const finished = operation ? FINAL.has(operation.stage) : false;
  useEffect(() => { if (finished) closeRef.current?.focus(); }, [finished]);
  return (
    <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="operation-title">
      <div className="modal-box max-w-lg">
        <h2 id="operation-title" className="text-xl font-semibold">{title}</h2>
        <div className="my-6 flex items-start gap-3">
          {!operation || !finished ? <LoaderCircle className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" /> : operation.stage === 'succeeded' ? <CheckCircle2 className="text-success" aria-hidden="true" /> : <TriangleAlert className="text-error" aria-hidden="true" />}
          <div><p className="font-medium capitalize">{operation?.stage.replace('_', ' ') ?? 'pending'}</p><p className="mt-1 text-sm opacity-75" aria-live="polite">{operation?.message ?? 'Operation queued.'}</p></div>
        </div>
        {operation?.validation_errors.map(error => <div key={`${error.code}:${error.file ?? ''}`} className="alert alert-error mb-2 text-sm"><span>{error.message}</span></div>)}
        <div className="modal-action"><button ref={closeRef} className="btn min-h-11" disabled={!finished} onClick={() => onClose(finished)}>{closeLabel}</button></div>
      </div><div className="modal-backdrop bg-black/50" />
    </div>
  );
}
