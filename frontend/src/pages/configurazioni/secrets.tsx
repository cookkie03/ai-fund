import { CircleCheck, CircleX, KeyRound, Loader2, LockKeyhole, PlugZap, ShieldAlert, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { clearSecret, commandFailure, isBrokerKey, setSecret, testConnection, testTargetFor } from "@/features/settings/api";
import { useRefreshCfg, useSecrets } from "@/features/settings/hooks";
import type { SecretResult, SecretStatus, TestTarget } from "@/features/settings/types";
import { fmtDateTime } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { Bones, fieldClass, Panel, Tag, Unavailable } from "./parts";
import { since } from "./parts";

const PROVIDERS: { target: TestTarget | null; title: string; what: string }[] = [
  { target: "omniroute", title: "OmniRoute", what: "Gateway dei modelli usato da tutti gli agenti. La prova elenca i modelli disponibili." },
  { target: "alpaca", title: "Alpaca", what: "Broker e dati di mercato. Key ID e secret vanno in coppia. La prova legge il conto, senza ordini." },
  { target: "openbb", title: "OpenBB", what: "Dati fondamentali e notizie per gli analisti." },
  { target: null, title: "Altri provider dati", what: "Chiavi che il Runtime gestisce senza una prova di connessione dedicata." },
];

const SOURCE: Record<SecretStatus["source"], { word: string; hint: string }> = {
  store: { word: "Archivio del Runtime", hint: "Salvata dal cockpit nel file dei segreti del Runtime, fuori dal repository e dal database." },
  env: { word: "Da ambiente", hint: "Arriva da .env o da una variabile d'ambiente: per toglierla va rimossa da lì. Una chiave salvata qui ha la precedenza." },
  none: { word: "Mancante", hint: "Non impostata in nessuna fonte." },
};

type LocalResult = { kind: "saved"; r: SecretResult } | { kind: "test"; ok: boolean; detail: string | null };

function TestLine({ ok, detail, ts, now }: { ok: boolean; detail: string | null; ts?: string | null; now: number }) {
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5 text-2xs", ok ? "text-fg-muted" : "text-down")}>
      {ok ? <CircleCheck className="size-3 shrink-0 text-fg-subtle" aria-hidden /> : <CircleX className="size-3 shrink-0" aria-hidden />}
      <span className="truncate">
        {ok ? "Prova riuscita" : "Prova fallita"}
        {detail ? `: ${detail}` : ""}
      </span>
      {ts && <span className="num shrink-0 text-fg-subtle" title={fmtDateTime(ts)}>· {since(ts, now)}</span>}
    </span>
  );
}

/**
 * Write-only key field. The value lives only in the uncontrolled <input> until it is sent: no React state, no
 * query or mutation cache, no URL (the form never submits natively). The field is emptied before the request
 * resolves, and only the Runtime's {set, last4, test} answer is shown afterwards.
 */
function KeyForm({ s, onDone, onCancel }: { s: SecretStatus; onDone: (r: SecretResult) => void; onCancel: () => void }) {
  const { client } = useRuntime();
  const refresh = useRefreshCfg();
  const input = useRef<HTMLInputElement>(null);
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [filled, setFilled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string[] | null>(null);
  const broker = isBrokerKey(s.name);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const el = input.current;
    if (!el || !el.value.trim()) return;
    const value = el.value;
    el.value = "";
    setFilled(false);
    setBusy(true);
    setError(null);
    try {
      const r = await setSecret(client, { name: s.name, value, reason: reason.trim(), confirm: broker ? confirm : false });
      if (!r.ok) return setError(r.reasons.length ? r.reasons : ["Rifiutata senza motivo"]);
      onDone(r.data);
    } catch (err) {
      setError([commandFailure(err, "set_secret")]);
    } finally {
      setBusy(false);
      refresh("secrets", "health");
    }
  };

  return (
    <form onSubmit={submit} autoComplete="off" className="mt-2 space-y-2.5 rounded-control bg-[oklch(0_0_0/0.18)] p-3" aria-label={`Nuovo valore per ${s.label}`}>
      <label className="block">
        <span className="text-2xs text-fg-subtle">{s.set ? "Nuovo valore (sostituisce quello attuale)" : "Valore"}</span>
        <span className="relative mt-1 block">
          <LockKeyhole className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
          <input
            ref={input}
            type="password"
            name={`secret-${s.name.toLowerCase()}`}
            autoComplete="new-password"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            data-1p-ignore
            data-lpignore="true"
            placeholder="Incolla la chiave"
            onChange={(e) => setFilled(e.target.value.trim().length > 0)}
            className={cn(fieldClass, "pl-8 font-mono text-xs")}
          />
        </span>
      </label>
      <label className="block">
        <span className="text-2xs text-fg-subtle">Motivo (obbligatorio, finisce nell'audit; il valore no)</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Es. rotazione trimestrale" className={cn(fieldClass, "mt-1")} />
      </label>
      {broker && (
        <label className="flex items-start gap-2.5 text-xs text-fg">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} className="mt-0.5 size-3.5 accent-[var(--accent-strong)]" />
          <span>
            <span className="font-medium">Confermo: è una chiave del broker.</span> <span className="text-fg-muted">Con questa chiave il Runtime invia ordini sul conto. Key ID e secret devono appartenere alla stessa coppia.</span>
          </span>
        </label>
      )}
      {error && (
        <ul role="alert" className="list-disc rounded-item bg-down-soft py-2 pl-7 pr-3 text-xs text-fg">
          {error.map((m) => <li key={m}>{m}</li>)}
        </ul>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Annulla
        </Button>
        <Button type="submit" size="sm" disabled={!filled || reason.trim().length < 5 || (broker && !confirm) || busy} data-action="save-secret">
          {busy && <Loader2 className="animate-spin" />} Salva e prova
        </Button>
      </div>
    </form>
  );
}

function SecretRow({ s, now }: { s: SecretStatus; now: number }) {
  const { writable } = useShell();
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [local, setLocal] = useState<LocalResult | null>(null);
  const src = SOURCE[s.source];

  return (
    <li className="rounded-item px-2.5 py-2.5" data-secret={s.name}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px] font-medium text-fg">{s.label}</span>
            <span className="font-mono text-2xs text-fg-subtle">{s.name}</span>
            {isBrokerKey(s.name) && <Tag icon={ShieldAlert} title="Chiave del broker: ogni modifica chiede una conferma esplicita">Broker</Tag>}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-fg-subtle">
            <Tag tone={s.source === "none" ? "warn" : "neutral"} title={src.hint}>
              {src.word}
            </Tag>
            {s.set && s.last4 && (
              <span className="num font-mono text-fg-muted" aria-label={`Termina con ${s.last4}`}>
                •••• {s.last4}
              </span>
            )}
            {s.updated_ts && (
              <span className="inline-flex items-center gap-1">
                {s.updated_by && <AuthorChip actor={s.updated_by} size="xs" />}
                <span className="num" title={fmtDateTime(s.updated_ts)}>{since(s.updated_ts, now)}</span>
              </span>
            )}
          </p>
          <div className="mt-1">
            {local?.kind === "saved" ? (
              <p role="status" className="flex flex-wrap items-center gap-x-2 text-2xs">
                <span className="font-medium text-fg">Salvata{local.r.last4 ? ` · termina con ${local.r.last4}` : ""}.</span>
                {local.r.test ? <TestLine ok={local.r.test.ok} detail={local.r.test.detail} now={now} /> : <span className="text-fg-subtle">Nessuna prova eseguita.</span>}
              </p>
            ) : s.test ? (
              <TestLine ok={s.test.ok} detail={s.test.detail} ts={s.test.ts} now={now} />
            ) : s.set ? (
              <span className="text-2xs text-fg-subtle">Mai provata</span>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {!editing && (
            <Button size="sm" variant={s.set ? "ghost" : "outline"} disabled={!writable} onClick={() => { setEditing(true); setLocal(null); }}>
              <KeyRound /> {s.set ? "Sostituisci" : "Imposta"}
            </Button>
          )}
          {s.set && !editing && (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Rimuovi ${s.label}`}
              title={s.source === "env" ? "Arriva dall'ambiente: va tolta da .env o dalla variabile" : `Rimuovi ${s.label}`}
              disabled={!writable || s.source === "env"}
              onClick={() => setRemoving(true)}
              className="text-fg-subtle hover:text-down"
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </div>
      {editing && (
        <KeyForm
          s={s}
          onCancel={() => setEditing(false)}
          onDone={(r) => {
            setEditing(false);
            setLocal({ kind: "saved", r });
            toast.success(`${s.label} salvata`, { description: r.test ? (r.test.ok ? "Prova di connessione riuscita" : "Prova di connessione fallita") : undefined });
          }}
        />
      )}
      {removing && <RemoveDialog s={s} onClose={() => setRemoving(false)} />}
    </li>
  );
}

function RemoveDialog({ s, onClose }: { s: SecretStatus; onClose: () => void }) {
  const { client } = useRuntime();
  const refresh = useRefreshCfg();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await clearSecret(client, { name: s.name, reason: reason.trim(), confirm: true });
      if (!r.ok) return setError(r.reasons.length ? r.reasons : ["Rifiutato senza motivo"]);
      toast.success(`${s.label} rimossa`);
      onClose();
    } catch (e) {
      setError([commandFailure(e, "clear_secret")]);
    } finally {
      setBusy(false);
      refresh("secrets", "health");
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[460px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">Rimuovere {s.label}?</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">
            {isBrokerKey(s.name) ? "Senza questa chiave il Runtime non può più leggere il conto né inviare ordini." : "I servizi che la usano smettono di funzionare finché non ne imposti un'altra."} Se la stessa chiave esiste nell'ambiente, torna in uso quella.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 px-5 py-4">
          <label className="block">
            <span className="text-2xs text-fg-subtle">Motivo (obbligatorio)</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} className={cn(fieldClass, "mt-1")} placeholder="Es. chiave revocata dal provider" />
          </label>
          {error && <ul role="alert" className="list-disc rounded-item bg-down-soft py-2 pl-7 pr-3 text-xs text-fg">{error.map((m) => <li key={m}>{m}</li>)}</ul>}
        </div>
        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>Annulla</Button>
          <Button variant="destructive" disabled={reason.trim().length < 5 || busy} onClick={submit}>Rimuovi la chiave</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProviderPanel({ title, what, target, keys, now }: { title: string; what: string; target: TestTarget | null; keys: SecretStatus[]; now: number }) {
  const { client } = useRuntime();
  const { writable } = useShell();
  const refresh = useRefreshCfg();
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<LocalResult | null>(null);
  const missing = keys.filter((k) => !k.set).length;
  const failed = keys.some((k) => k.test && !k.test.ok);

  const test = async () => {
    if (!target) return;
    setTesting(true);
    setResult(null);
    try {
      const r = await testConnection(client, target);
      setResult(r.ok ? { kind: "test", ok: r.data.ok, detail: r.data.detail } : { kind: "test", ok: false, detail: r.reasons.join(" · ") || "Rifiutata" });
    } catch (e) {
      setResult({ kind: "test", ok: false, detail: commandFailure(e, "test_connection") });
    } finally {
      setTesting(false);
      refresh("secrets", "health");
    }
  };

  return (
    <Panel
      title={title}
      meta={missing ? undefined : failed ? undefined : keys.length > 1 ? `${keys.length} chiavi` : undefined}
      end={
        target ? (
          <Button size="sm" variant="ghost" disabled={!writable || testing || missing === keys.length} onClick={test} title={missing === keys.length ? "Imposta prima la chiave" : undefined}>
            {testing ? <Loader2 className="animate-spin" /> : <PlugZap />} Prova connessione
          </Button>
        ) : undefined
      }
    >
      <p className="-mt-1 px-4 pb-1 text-2xs leading-4 text-fg-subtle">{what}</p>
      {result?.kind === "test" && (
        <p role="status" className="px-4 pb-1">
          <TestLine ok={result.ok} detail={result.detail} now={now} />
        </p>
      )}
      <ul className="space-y-px px-1.5 pb-2">
        {keys.map((k) => <SecretRow key={k.name} s={k} now={now} />)}
      </ul>
    </Panel>
  );
}

export function SecretsSection() {
  const q = useSecrets();
  const now = useNow(30_000);
  const list = q.data?.source === "runtime" ? q.data.data : null;
  const intro = (
    <div className="flex items-start gap-2.5 rounded-control bg-ground px-4 py-3 text-xs leading-relaxed text-fg-muted">
      <LockKeyhole className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      <p>
        Le chiavi sono <span className="text-fg">in sola scrittura</span>: il Runtime le salva fuori dal repository e dal database e non le rimanda mai al cockpit. Qui vedi solo se sono impostate, da dove arrivano, le ultime 4 cifre e l'esito dell'ultima prova. L'audit registra chi e quando, mai il valore.
      </p>
    </div>
  );
  if (q.isPending) return <>{intro}<Panel title="Chiavi"><Bones rows={4} className="px-4 pb-4" /></Panel></>;
  if (q.error) return <>{intro}<Panel title="Chiavi"><p role="alert" className="px-4 pb-4 text-xs text-down">Stato delle chiavi non disponibile: {q.error.message}</p></Panel></>;
  if (!list) return <>{intro}<Panel title="Chiavi"><Unavailable className="mx-4 mb-4">{q.data?.source === "unavailable" ? q.data.note : null} Fino ad allora le chiavi si impostano in .env e valgono al riavvio.</Unavailable></Panel></>;
  return (
    <>
      {intro}
      {PROVIDERS.map((p) => {
        const keys = list.filter((s) => testTargetFor(s.name) === p.target);
        return keys.length ? <ProviderPanel key={p.title} {...p} keys={keys} now={now} /> : null;
      })}
    </>
  );
}
