import { ArrowLeft, Columns2, FileDiff, History, Rows2, ShieldX } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { commandFailure, isCommandMissing, lineDiff, restorePrompt, updatePrompt } from "@/features/settings/api";
import { usePrompt, usePromptHistory, useRefreshCfg } from "@/features/settings/hooks";
import type { DiffLine, PromptRead } from "@/features/settings/types";
import { fmtDateTime } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { Bones, fieldClass, Panel, Tag, Unavailable } from "./parts";
import { since } from "./parts";

const nf = new Intl.NumberFormat("it-IT");

/** Unified or side-by-side diff; unchanged runs longer than 6 lines fold to a count. */
export function DiffView({ lines, split }: { lines: DiffLine[]; split: boolean }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  type Block = { kind: "lines"; lines: (DiffLine & { a: number | null; b: number | null })[] } | { kind: "fold"; id: number; lines: (DiffLine & { a: number | null; b: number | null })[] };
  const blocks = useMemo(() => {
    let a = 0;
    let b = 0;
    const numbered = lines.map((l) => ({ ...l, a: l.op === "add" ? null : ++a, b: l.op === "del" ? null : ++b }));
    const out: Block[] = [];
    let i = 0;
    while (i < numbered.length) {
      if (numbered[i].op !== "eq") {
        const start = i;
        while (i < numbered.length && numbered[i].op !== "eq") i++;
        out.push({ kind: "lines", lines: numbered.slice(start, i) });
        continue;
      }
      const start = i;
      while (i < numbered.length && numbered[i].op === "eq") i++;
      const run = numbered.slice(start, i);
      const headCtx = start === 0 ? 0 : 3;
      const tailCtx = i === numbered.length ? 0 : 3;
      if (run.length > headCtx + tailCtx + 2) {
        if (headCtx) out.push({ kind: "lines", lines: run.slice(0, headCtx) });
        out.push({ kind: "fold", id: start, lines: run.slice(headCtx, run.length - tailCtx) });
        if (tailCtx) out.push({ kind: "lines", lines: run.slice(run.length - tailCtx) });
      } else out.push({ kind: "lines", lines: run });
    }
    return out;
  }, [lines]);

  const cell = (l: DiffLine | null, n: number | null) => (
    <div
      className={cn(
        "grid grid-cols-[2.75rem_1rem_minmax(0,1fr)] font-mono text-[11.5px] leading-[1.15rem]",
        l?.op === "add" && "bg-[oklch(0.7_0.15_251/0.13)]",
        l?.op === "del" && "bg-[oklch(0.7_0.19_25/0.13)]",
        !l && "bg-[oklch(0_0_0/0.12)]",
      )}
    >
      <span className="num select-none pr-2 text-right text-fg-subtle/70">{n ?? ""}</span>
      <span aria-hidden className={cn("select-none", l?.op === "add" ? "text-accent-c" : l?.op === "del" ? "text-down" : "text-transparent")}>
        {l?.op === "add" ? "+" : l?.op === "del" ? "−" : " "}
      </span>
      <span className={cn("whitespace-pre-wrap break-words pr-3", l?.op === "eq" ? "text-fg-muted" : "text-fg")}>
        {l ? (l.text || " ") : ""}
        {l && l.op !== "eq" && <span className="sr-only">{l.op === "add" ? " (aggiunta)" : " (rimossa)"}</span>}
      </span>
    </div>
  );

  const renderLines = (ls: (DiffLine & { a: number | null; b: number | null })[], key: string) => {
    if (!split) return ls.map((l, i) => <div key={`${key}-${i}`}>{cell(l, l.op === "del" ? l.a : l.b)}</div>);
    // Pair deletions with additions inside a change block, eq lines on both sides.
    const dels = ls.filter((l) => l.op === "del");
    const adds = ls.filter((l) => l.op === "add");
    if (ls.every((l) => l.op === "eq")) return ls.map((l, i) => <div key={`${key}-${i}`} className="grid grid-cols-2 divide-x divide-line">{cell(l, l.a)}{cell(l, l.b)}</div>);
    const n = Math.max(dels.length, adds.length);
    return Array.from({ length: n }, (_, i) => (
      <div key={`${key}-${i}`} className="grid grid-cols-2 divide-x divide-line">
        {cell(dels[i] ?? null, dels[i]?.a ?? null)}
        {cell(adds[i] ?? null, adds[i]?.b ?? null)}
      </div>
    ));
  };

  return (
    <div className="overflow-hidden rounded-control bg-[oklch(0_0_0/0.22)] py-1" role="table" aria-label="Differenze dal prompt attivo">
      {split && (
        <div className="grid grid-cols-2 border-b border-line pb-1 text-2xs text-fg-subtle">
          <span className="pl-[3.75rem]">Versione attiva</span>
          <span className="pl-[3.75rem]">Nuova versione</span>
        </div>
      )}
      {blocks.map((b, i) =>
        b.kind === "fold" && !open.has(b.id) ? (
          <button key={i} type="button" onClick={() => setOpen((s) => new Set(s).add(b.id))} className="block w-full py-1 text-center text-2xs text-fg-subtle hover:bg-hover hover:text-fg">
            {nf.format(b.lines.length)} righe invariate · mostra
          </button>
        ) : (
          <div key={i}>{renderLines(b.lines, String(i))}</div>
        ),
      )}
    </div>
  );
}

function stats(lines: DiffLine[]) {
  return { add: lines.filter((l) => l.op === "add").length, del: lines.filter((l) => l.op === "del").length };
}

/** The agent's prompt: monospace editor, diff against the active version, reason, then confirm. */
export function PromptEditor({ agent, name, fullscreen, onExitFullscreen }: { agent: string; name: string; fullscreen?: boolean; onExitFullscreen?: () => void }) {
  const q = usePrompt(agent);
  const { client } = useRuntime();
  const { writable } = useShell();
  const refresh = useRefreshCfg();
  const wideDiff = useMediaQuery("(min-width: 1180px)");
  const now = useNow(60_000);
  const [text, setText] = useState<string | null>(null);
  const [step, setStep] = useState<"edit" | "review">("edit");
  const [split, setSplit] = useState(true);
  const [serverDiff, setServerDiff] = useState<DiffLine[] | null>(null);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const p: PromptRead | null = q.data?.source === "runtime" ? q.data.data : null;
  // A new active version from elsewhere resets a clean editor, never a dirty one.
  useEffect(() => {
    setText(null);
    setStep("edit");
    setReason("");
  }, [agent]);

  const value = text ?? p?.text ?? "";
  const dirty = !!p && text !== null && text !== p.text;
  const diff = useMemo(() => (p && dirty ? serverDiff ?? lineDiff(p.text, value) : []), [p, dirty, value, serverDiff]);
  const s = stats(diff);

  const review = async () => {
    if (!p) return;
    setRefusal(null);
    setFailure(null);
    setServerDiff(null);
    setBusy(true);
    try {
      const r = await updatePrompt(client, { agent, text: value, reason: reason.trim() || "anteprima", dry_run: true });
      if (!r.ok) setRefusal(r.reasons);
      setServerDiff(r.data?.diff ?? null);
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
      setStep("review");
    }
  };

  const submit = async () => {
    setRefusal(null);
    setFailure(null);
    setBusy(true);
    try {
      const r = await updatePrompt(client, { agent, text: value, reason: reason.trim(), dry_run: false });
      if (!r.ok) return setRefusal(r.reasons);
      toast.success(`Prompt di ${name} aggiornato`, { description: "Vale dal prossimo ciclo dell'agente." });
      setText(null);
      setReason("");
      setStep("edit");
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
      refresh("prompt", "agents");
    }
  };

  if (q.isPending) return <Bones rows={5} className="px-4 pb-4" />;
  if (q.error) return <p role="alert" className="px-4 pb-4 text-xs text-down">Prompt non disponibile: {q.error.message}</p>;
  if (!p) return <Unavailable className="mx-4 mb-4">{q.data?.source === "unavailable" ? q.data.note : "Prompt non disponibile."}</Unavailable>;

  const lines = value.split("\n").length;
  const missing = isCommandMissing(failure);

  return (
    <div className={cn("px-4 pb-4", fullscreen && "flex min-h-0 flex-1 flex-col")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pb-2 text-2xs text-fg-subtle">
        <span className="inline-flex items-center gap-1.5">
          Versione <span className="num text-fg-muted">{p.version}</span>
          {p.is_default ? <Tag>Default</Tag> : p.updated_by ? <>· <AuthorChip actor={p.updated_by} size="xs" label /></> : null}
          {p.updated_ts && <span className="num" title={fmtDateTime(p.updated_ts)}>{since(p.updated_ts, now)}</span>}
        </span>
        {p.reason && !p.is_default && <span className="min-w-0 truncate">«{p.reason}»</span>}
        <span className="num ml-auto">
          {nf.format(value.length)} caratteri · {nf.format(lines)} righe
          {dirty && (
            <>
              {" "}· <span className="text-accent-c">+{s.add}</span> <span className="text-down">−{s.del}</span>
            </>
          )}
        </span>
      </div>

      {step === "edit" ? (
        <>
          <textarea
            ref={area}
            aria-label={`Prompt di ${name}`}
            value={value}
            onChange={(e) => {
              setText(e.target.value);
              setServerDiff(null);
            }}
            spellCheck={false}
            readOnly={!writable}
            className={cn(
              "block w-full resize-y rounded-control border border-line-strong bg-[oklch(0_0_0/0.22)] px-3 py-2.5 font-mono text-[12px] leading-[1.2rem] text-fg outline-none [tab-size:2] focus:border-accent-c focus-visible:ring-2 focus-visible:ring-ring/40",
              fullscreen ? "min-h-0 flex-1 resize-none" : "h-[360px]",
              dirty && "border-accent-c/60",
            )}
          />
          <div className="flex flex-wrap items-center gap-2 pt-2.5">
            <p className="mr-auto text-2xs text-fg-subtle">Il nuovo prompt vale dal prossimo ciclo dell'agente: il ciclo in corso finisce con quello attuale.</p>
            {fullscreen && onExitFullscreen && (
              <Button size="sm" variant="ghost" onClick={onExitFullscreen}>
                <ArrowLeft /> Agente
              </Button>
            )}
            {dirty && (
              <Button size="sm" variant="ghost" onClick={() => setText(null)}>
                Annulla modifiche
              </Button>
            )}
            <Button size="sm" variant="outline" disabled={!dirty || busy || !writable} onClick={review} title={!writable ? "Runtime irraggiungibile" : undefined}>
              <FileDiff /> Rivedi le differenze
            </Button>
          </div>
        </>
      ) : (
        <div className={cn("space-y-3", fullscreen && "min-h-0 flex-1 overflow-y-auto")}>
          <div className="flex items-center gap-2">
            <p className="text-xs text-fg">
              <span className="font-medium">Differenze dalla versione {p.version}</span>{" "}
              <span className="num text-fg-subtle">
                <span className="text-accent-c">+{s.add}</span> <span className="text-down">−{s.del}</span> righe
              </span>
            </p>
            {wideDiff && (
              <div role="radiogroup" aria-label="Vista delle differenze" className="seg ml-auto">
                <button type="button" role="radio" aria-checked={split} onClick={() => setSplit(true)} className="seg-item" aria-label="Affiancate">
                  <Columns2 className="size-3.5" /> Affiancate
                </button>
                <button type="button" role="radio" aria-checked={!split} onClick={() => setSplit(false)} className="seg-item" aria-label="Unificate">
                  <Rows2 className="size-3.5" /> Unificate
                </button>
              </div>
            )}
          </div>
          <div className={cn("overflow-y-auto", !fullscreen && "max-h-[420px]")}>
            <DiffView lines={diff} split={wideDiff && split} />
          </div>
          {missing ? (
            <Unavailable>Il Runtime non espone ancora il comando update_prompt: la modifica resta nell'editor e non è stata applicata.</Unavailable>
          ) : failure ? (
            <p role="alert" className="text-xs text-down">{commandFailure(failure, "update_prompt")}</p>
          ) : null}
          {refusal && (
            <div role="alert" className="rounded-control border border-[oklch(0.67_0.195_20/0.4)] bg-down-soft px-3 py-2.5 text-xs">
              <p className="flex items-center gap-1.5 font-medium text-down">
                <ShieldX className="size-3.5" /> Rifiutato dal Runtime
              </p>
              <ul className="mt-1 list-disc pl-5 text-fg">{(refusal.length ? refusal : ["Nessuna ragione indicata"]).map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          <label className="block">
            <span className="text-2xs text-fg-subtle">Motivo (obbligatorio, resta nelle versioni)</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Es. chiedo i livelli in tabella con prezzo e forza" className={cn(fieldClass, "mt-1 h-auto resize-none py-2")} />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" className="mr-auto" onClick={() => setStep("edit")}>
              <ArrowLeft /> Torna all'editor
            </Button>
            <Button size="sm" data-action="confirm-prompt" disabled={reason.trim().length < 5 || busy || missing || !writable} onClick={submit} title={reason.trim().length < 5 ? "Scrivi un motivo di almeno 5 caratteri" : undefined}>
              Conferma la versione {p.version + 1}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function PromptVersions({ agent, current }: { agent: string; current: number | null }) {
  const q = usePromptHistory(agent);
  const now = useNow(60_000);
  const { writable } = useShell();
  const [restoring, setRestoring] = useState<number | null>(null);
  return (
    <Panel title="Versioni del prompt" meta={q.data?.source === "runtime" ? `${q.data.data.length}` : undefined}>
      {q.isPending ? (
        <Bones rows={2} className="px-4 pb-4" />
      ) : q.error ? (
        <p className="px-4 pb-4 text-xs text-down">Versioni non disponibili: {q.error.message}</p>
      ) : q.data.source === "unavailable" ? (
        <Unavailable className="mx-4 mb-4">{q.data.note}</Unavailable>
      ) : q.data.data.length <= 1 ? (
        <p className="px-4 pb-4 text-xs text-fg-subtle">Solo la versione di default da prompts/: la prima modifica diventa la versione 2.</p>
      ) : (
        <ol className="space-y-px px-1.5 pb-2">
          {q.data.data.map((v) => (
            <li key={v.version} className="group flex items-start gap-3 rounded-item px-2.5 py-2 hover:bg-hover/60">
              <AuthorChip actor={v.actor} size="sm" className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  <span className="font-medium text-fg">Versione {v.version}</span>
                  {v.version === current && <Tag tone="accent">Attiva</Tag>}
                  <span className="num text-2xs text-fg-subtle" title={fmtDateTime(v.ts)}>{since(v.ts, now)}</span>
                  {v.chars !== null && <span className="num text-2xs text-fg-subtle">{nf.format(v.chars)} caratteri</span>}
                </p>
                <p className="mt-0.5 text-xs text-fg-muted">«{v.reason}»</p>
              </div>
              {current !== null && v.version !== current && (
                <Button size="xs" variant="ghost" className="shrink-0 opacity-80 group-hover:opacity-100" disabled={!writable} onClick={() => setRestoring(v.version)}>
                  <History /> Ripristina
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
      {restoring !== null && <RestorePromptDialog agent={agent} version={restoring} onClose={() => setRestoring(null)} />}
    </Panel>
  );
}

function RestorePromptDialog({ agent, version, onClose }: { agent: string; version: number; onClose: () => void }) {
  const { client } = useRuntime();
  const refresh = useRefreshCfg();
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ tone: "down"; text: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await restorePrompt(client, { agent, version, reason: reason.trim() });
      if (!r.ok) return setMsg({ tone: "down", text: r.reasons.length ? r.reasons : ["Rifiutato senza motivo"] });
      toast.success(`Ripristinata la versione ${version} del prompt`, { description: "Vale dal prossimo ciclo dell'agente." });
      onClose();
    } catch (e) {
      setMsg({ tone: "down", text: [commandFailure(e, "restore_prompt")] });
    } finally {
      setBusy(false);
      refresh("prompt", "agents");
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[480px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">Ripristinare la versione {version} del prompt?</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">Diventa una nuova versione uguale alla {version} e vale dal prossimo ciclo. Le versioni successive restano nello storico.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 px-5 py-4">
          <label className="block">
            <span className="text-2xs text-fg-subtle">Motivo (obbligatorio)</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={cn(fieldClass, "mt-1 h-auto resize-none py-2")} />
          </label>
          {msg && (
            <ul role="alert" className="list-disc rounded-control bg-down-soft px-3 py-2 pl-7 text-xs text-fg">
              {msg.text.map((t) => <li key={t}>{t}</li>)}
            </ul>
          )}
        </div>
        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>Annulla</Button>
          <Button disabled={reason.trim().length < 5 || busy} onClick={submit}>Ripristina la versione {version}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
