import { ArrowRight, CircleCheck, History, Info, Plug, RotateCcw, RotateCw, ShieldAlert, ShieldX, TriangleAlert, Undo2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { commandFailure, isCommandMissing, restoreSettings, updateSettings } from "@/features/settings/api";
import { useRefreshCfg, useSettingsHistory } from "@/features/settings/hooks";
import type { SettingItem, SettingsPreview, SettingsRead, SettingValue } from "@/features/settings/types";
import { fmtDateTime, toNum } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { agentAuthor, Bones, fieldClass, fmtRange, fmtValue, optionWord, Panel, Tag, Unavailable } from "./parts";
import { since } from "./parts";
import { SECTIONS, sectionOfKey, type SectionId } from "./sections";

// ---------- values ----------

const toText = (_item: SettingItem, v: SettingValue): string => {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return String(v).replace(".", ",");
  return String(v);
};

/** Parses what Luca typed into the value the Runtime expects, or says why it cannot. */
export function parseDraft(item: SettingItem, text: string): { value: SettingValue; error: string | null } {
  const t = text.trim();
  if (item.type === "int" || item.type === "float") {
    const n = toNum(t.replace(/\./g, "").replace(",", "."));
    if (n === null || t === "") return { value: null, error: "Serve un numero" };
    if (item.type === "int" && !Number.isInteger(n)) return { value: n, error: "Serve un numero intero" };
    if (item.min !== null && n < item.min) return { value: n, error: `Minimo ${fmtValue(item, item.min)}` };
    if (item.max !== null && n > item.max) return { value: n, error: `Massimo ${fmtValue(item, item.max)}` };
    return { value: n, error: null };
  }
  if (item.type === "bool") return { value: t === "true", error: null };
  if (item.type === "time") return /^([01]\d|2[0-3]):[0-5]\d$/.test(t) ? { value: t, error: null } : { value: t, error: "Ora non valida (HH:MM)" };
  if (item.type === "enum") return item.options?.includes(t) ? { value: t, error: null } : { value: t, error: "Valore non ammesso" };
  return t ? { value: t, error: null } : { value: t, error: "Non può essere vuoto" };
}

const same = (a: SettingValue, b: SettingValue) => (typeof a === "number" && typeof b === "number" ? Math.abs(a - b) < 1e-9 : a === b);

// ---------- draft store ----------

type Draft = {
  settings: SettingsRead | null;
  items: Map<string, SettingItem>;
  text: Record<string, string>;
  set: (key: string, text: string) => void;
  discard: (keys?: string[]) => void;
  /** Valid changes against the current values, and invalid drafts. */
  changes: { item: SettingItem; value: SettingValue }[];
  invalid: { item: SettingItem; error: string }[];
  reviewOpen: boolean;
  setReviewOpen: (o: boolean) => void;
};

const Ctx = createContext<Draft | null>(null);

export function DraftProvider({ settings, children }: { settings: SettingsRead | null; children: ReactNode }) {
  const [text, setText] = useState<Record<string, string>>({});
  const [reviewOpen, setReviewOpen] = useState(false);
  const items = useMemo(() => new Map((settings?.sections ?? []).flatMap((s) => s.items).map((i) => [i.key, i])), [settings]);

  const set = useCallback((key: string, t: string) => setText((d) => ({ ...d, [key]: t })), []);
  const discard = useCallback((keys?: string[]) => setText((d) => (keys ? Object.fromEntries(Object.entries(d).filter(([k]) => !keys.includes(k))) : {})), []);

  const { changes, invalid } = useMemo(() => {
    const changes: Draft["changes"] = [];
    const invalid: Draft["invalid"] = [];
    for (const [key, t] of Object.entries(text)) {
      const item = items.get(key);
      if (!item) continue;
      const p = parseDraft(item, t);
      if (p.error) invalid.push({ item, error: p.error });
      else if (!same(p.value, item.value)) changes.push({ item, value: p.value });
    }
    return { changes, invalid };
  }, [text, items]);

  // Leaving with unsent changes asks first.
  useEffect(() => {
    if (!changes.length && !invalid.length) return;
    const onLeave = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [changes.length, invalid.length]);

  const value = useMemo(() => ({ settings, items, text, set, discard, changes, invalid, reviewOpen, setReviewOpen }), [settings, items, text, set, discard, changes, invalid, reviewOpen]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDraft(): Draft {
  const c = useContext(Ctx);
  if (!c) throw new Error("useDraft outside DraftProvider");
  return c;
}

/** Drafted changes per page section, for the index. */
export function useDraftCounts(): Partial<Record<SectionId, number>> {
  const { changes, invalid } = useDraft();
  const out: Partial<Record<SectionId, number>> = {};
  for (const { item } of [...changes, ...invalid]) out[sectionOfKey(item.key)] = (out[sectionOfKey(item.key)] ?? 0) + 1;
  return out;
}

// ---------- the ledger row ----------

function Control({ item, text, onText, invalid, disabled }: { item: SettingItem; text: string; onText: (t: string) => void; invalid: boolean; disabled: boolean }) {
  const id = `set-${item.key}`;
  const opts = item.options ?? [];
  if (item.type === "bool" || (item.type === "enum" && opts.length <= 3 && opts.every((o) => optionWord(o).length <= 8))) {
    const choices = item.type === "bool" ? [{ v: "false", l: "No" }, { v: "true", l: "Sì" }] : opts.map((o) => ({ v: o, l: optionWord(o) }));
    return (
      <div role="radiogroup" aria-label={item.label} className="seg w-full">
        {choices.map((c) => (
          <button key={c.v} type="button" role="radio" aria-checked={text === c.v} disabled={disabled} onClick={() => onText(c.v)} className="seg-item flex-1 justify-center">
            {c.l}
          </button>
        ))}
      </div>
    );
  }
  if (item.type === "enum") {
    return (
      <select id={id} aria-label={item.label} value={text} disabled={disabled} onChange={(e) => onText(e.target.value)} className={cn(fieldClass, "appearance-auto pr-2", invalid && "border-down")}>
        {!opts.includes(text) && <option value={text}>{text || "—"}</option>}
        {opts.map((o) => (
          <option key={o} value={o}>
            {optionWord(o)}
          </option>
        ))}
      </select>
    );
  }
  if (item.type === "time") {
    return <input id={id} type="time" aria-label={item.label} value={text} disabled={disabled} onChange={(e) => onText(e.target.value)} aria-invalid={invalid} className={cn(fieldClass, "num [color-scheme:dark]", invalid && "border-down")} />;
  }
  const numeric = item.type === "int" || item.type === "float";
  const prefix = item.unit === "$";
  const suffix = item.unit && item.unit !== "$" ? item.unit : null;
  return (
    <span className="relative block">
      {prefix && <span className="pointer-events-none absolute inset-y-0 left-2.5 grid place-items-center text-xs text-fg-subtle">$</span>}
      <input
        id={id}
        aria-label={item.label}
        inputMode={numeric ? "decimal" : undefined}
        spellCheck={false}
        value={text}
        disabled={disabled}
        onChange={(e) => onText(e.target.value)}
        aria-invalid={invalid}
        className={cn(fieldClass, numeric ? "num text-right" : "font-mono text-xs", prefix && "pl-6", suffix && (suffix.length > 3 ? "pr-14" : "pr-9"), invalid && "border-down")}
      />
      {suffix && <span className="pointer-events-none absolute inset-y-0 right-2.5 grid place-items-center text-2xs text-fg-subtle">{suffix}</span>}
    </span>
  );
}

/** One setting read like a ledger line: what it is, its value, its default, when it takes effect. */
export function SettingRow({ item, label, pending }: { item: SettingItem; label?: string; pending: boolean }) {
  const { text, set, discard } = useDraft();
  const { writable } = useShell();
  const drafted = item.key in text;
  const t = drafted ? text[item.key] : toText(item, item.value);
  const parsed = drafted ? parseDraft(item, t) : { value: item.value, error: null };
  const changed = drafted && !parsed.error && !same(parsed.value, item.value);
  const differsFromDefault = !same(parsed.value, item.default);
  const bounds = fmtRange(item);

  return (
    <div
      data-key={item.key}
      data-state={parsed.error ? "invalid" : changed ? "changed" : undefined}
      className={cn("grid gap-x-6 gap-y-2 rounded-item px-2.5 py-2.5 transition-colors md:grid-cols-[minmax(0,1fr)_17.5rem]", changed && "bg-accent-soft/50", parsed.error && "bg-down-soft/60")}
    >
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5">
          <label htmlFor={`set-${item.key}`} className="text-[13px] font-medium text-fg" title={item.key}>
            {label ?? item.label}
          </label>
          {item.apply === "restart" && !pending && (
            <Tag icon={RotateCw} title="Il Runtime la legge all'avvio: una modifica vale dal prossimo riavvio">
              Al riavvio
            </Tag>
          )}
          {pending && (
            <Tag icon={RotateCw} tone="warn" title="Salvata, non ancora in uso: vale dal prossimo riavvio del Runtime">
              In attesa di riavvio
            </Tag>
          )}
          {item.capital && (
            <Tag icon={ShieldAlert} title="Tocca il capitale: la conferma è esplicita">
              Capitale
            </Tag>
          )}
        </p>
        {item.description && <p className="mt-0.5 text-2xs leading-4 text-fg-subtle">{item.description}</p>}
      </div>
      <div className="min-w-0">
        <Control item={item} text={t} onText={(v) => set(item.key, v)} invalid={!!parsed.error} disabled={!writable} />
        <p className="mt-1 flex min-h-4 flex-wrap items-center gap-x-2 text-2xs leading-4 text-fg-subtle">
          {parsed.error ? (
            <span className="text-down">{parsed.error}</span>
          ) : changed ? (
            <span className="num inline-flex items-center gap-1 text-fg-muted">
              ora {fmtValue(item, item.value)} <ArrowRight className="size-3" aria-hidden /> <span className="text-fg">{fmtValue(item, parsed.value)}</span>
            </span>
          ) : (
            <span className="num">{differsFromDefault ? `Modificata · default ${fmtValue(item, item.default)}` : "Default"}</span>
          )}
          {bounds && !parsed.error && <span className="num">· {bounds}</span>}
          <span className="ml-auto flex items-center gap-0.5">
            {drafted && (
              <button type="button" onClick={() => discard([item.key])} className="inline-flex h-5 items-center gap-1 rounded-tag px-1 text-fg-subtle hover:bg-hover hover:text-fg" title="Annulla questa modifica">
                <Undo2 className="size-3" aria-hidden /> Annulla
              </button>
            )}
            {differsFromDefault && item.default !== null && writable && (
              <button type="button" onClick={() => set(item.key, toText(item, item.default))} className="inline-flex h-5 items-center gap-1 rounded-tag px-1 text-fg-subtle hover:bg-hover hover:text-fg" title={`Torna al default: ${fmtValue(item, item.default)}`}>
                <RotateCcw className="size-3" aria-hidden /> Default
              </button>
            )}
          </span>
        </p>
      </div>
    </div>
  );
}

/** Rows of one contract section (or a filtered subset), under its title. */
export function SettingsRows({ items, pending, labelOf }: { items: SettingItem[]; pending: string[]; labelOf?: (i: SettingItem) => string }) {
  return (
    <div className="space-y-px px-1.5 pb-2">
      {items.map((i) => (
        <SettingRow key={i.key} item={i} pending={pending.includes(i.key)} label={labelOf?.(i)} />
      ))}
    </div>
  );
}

/** Settings of a page section, grouped by the contract's section titles, one tile each. */
export function SettingsPanels({ section, q, exclude }: { section: SectionId; q: { data?: { source: string; note?: string; data?: SettingsRead }; isPending: boolean; error: Error | null }; exclude?: (key: string) => boolean }) {
  if (q.isPending) return <Panel title="Impostazioni"><Bones rows={4} className="px-4 pb-4" /></Panel>;
  if (q.error) return <Panel title="Impostazioni"><p role="alert" className="px-4 pb-4 text-xs text-down">Impostazioni non disponibili: {q.error.message}</p></Panel>;
  if (!q.data?.data) return <Panel title="Impostazioni"><Unavailable className="mx-4 mb-4">{q.data?.note}</Unavailable></Panel>;
  const s = q.data.data;
  const groups = s.sections
    .map((g) => ({ ...g, items: g.items.filter((i) => sectionOfKey(i.key) === section && !exclude?.(i.key)) }))
    .filter((g) => g.items.length);
  if (!groups.length) return null;
  return (
    <>
      {groups.map((g) => (
        <Panel key={g.id} title={g.title} meta={`${g.items.length} ${g.items.length === 1 ? "voce" : "voci"}`}>
          <SettingsRows items={g.items} pending={s.pending_restart} labelOf={(i) => (i.key.startsWith("agents.") ? `${i.label} · ${agentAuthor(i.key.split(".")[1]).short}` : i.label)} />
        </Panel>
      ))}
    </>
  );
}

// ---------- pending restart ----------

export function PendingRestartBanner() {
  const { settings, items } = useDraft();
  const keys = settings?.pending_restart ?? [];
  if (!keys.length) return null;
  const names = keys.map((k) => {
    const i = items.get(k);
    const agent = k.startsWith("agents.") ? k.split(".")[1] : null;
    return i ? `${i.label}${agent ? ` (${agent.replace(/_/g, " ")})` : ""}` : k;
  });
  return (
    <div role="status" className="flex items-start gap-2.5 rounded-control bg-warn-soft px-3.5 py-2.5 text-xs">
      <RotateCw className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden />
      <p className="text-fg">
        <span className="font-medium text-warn">{keys.length === 1 ? "Una modifica aspetta" : `${keys.length} modifiche aspettano`} il riavvio del Runtime.</span>{" "}
        <span className="text-fg-muted">Salvate, ma fino al riavvio vale il valore precedente: {names.join(", ")}.</span>
      </p>
    </div>
  );
}

// ---------- draft bar and review ----------

export function DraftBar() {
  const { changes, invalid, discard, setReviewOpen } = useDraft();
  const { writable } = useShell();
  const n = changes.length + invalid.length;
  if (!n) return null;
  const sections = new Set([...changes, ...invalid].map((c) => sectionOfKey(c.item.key)));
  const where = sections.size > 1 ? ` in ${sections.size} sezioni` : "";
  return (
    <div className="pointer-events-none sticky bottom-0 z-20 pb-2 pt-3 max-md:fixed max-md:inset-x-2 max-md:bottom-[calc(env(safe-area-inset-bottom)+60px)]">
      <div data-region="draft-bar" role="region" aria-label="Modifiche in bozza" className="draft-in pointer-events-auto mx-auto flex max-w-[640px] items-center gap-2 rounded-control border border-line-strong bg-raised py-1.5 pl-3.5 pr-1.5 shadow-[0_12px_32px_-8px_oklch(0_0_0/0.6),0_2px_6px_oklch(0_0_0/0.3)]">
        <span className="min-w-0 flex-1 truncate text-xs">
          <span className="font-medium text-fg">
            {changes.length} {changes.length === 1 ? "modifica" : "modifiche"}
            {where}
          </span>
          {invalid.length > 0 && <span className="text-down"> · {invalid.length} da correggere</span>}
        </span>
        <Button size="sm" variant="ghost" onClick={() => discard()}>
          Scarta
        </Button>
        <Button size="sm" variant="outline" disabled={!changes.length || invalid.length > 0 || !writable} onClick={() => setReviewOpen(true)} title={invalid.length ? "Correggi i valori segnati in rosso" : !writable ? "Runtime irraggiungibile" : undefined}>
          Rivedi
        </Button>
      </div>
    </div>
  );
}

export function ReviewSheet() {
  const { changes, reviewOpen, setReviewOpen, discard } = useDraft();
  const { client } = useRuntime();
  const { writable } = useShell();
  const refresh = useRefreshCfg();
  const wide = useMediaQuery("(min-width: 768px)");
  const [preview, setPreview] = useState<SettingsPreview | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [reason, setReason] = useState("");
  const [capitalOk, setCapitalOk] = useState(false);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [sending, setSending] = useState(false);

  const payload = useMemo(() => Object.fromEntries(changes.map((c) => [c.item.key, c.value])), [changes]);
  const capital = changes.some((c) => c.item.capital);
  const restart = changes.some((c) => c.item.apply === "restart");

  useEffect(() => {
    if (!reviewOpen) return;
    let alive = true;
    setPreview(null);
    setPreviewError(null);
    setRefusal(null);
    setFailure(null);
    setLoading(true);
    updateSettings(client, { changes: payload, reason: reason.trim() || "anteprima", confirm: false, dry_run: true })
      .then((r) => alive && setPreview(r.data ?? { changes: [], warnings: r.ok ? [] : r.reasons }))
      .catch((e) => alive && setPreviewError(e))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // The preview reflects the drafted values; the reason does not change the verdict.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewOpen, client, payload]);

  const rows = changes.map((c) => ({ ...c, p: preview?.changes.find((x) => x.key === c.item.key) ?? null }));
  const rejected = rows.filter((r) => r.p && !r.p.ok).length;
  const reasonOk = reason.trim().length >= 5;
  const canSend = !!preview && !rejected && reasonOk && (!capital || capitalOk) && writable && !sending;

  const submit = async () => {
    setRefusal(null);
    setFailure(null);
    setSending(true);
    try {
      const r = await updateSettings(client, { changes: payload, reason: reason.trim(), confirm: capital ? capitalOk : false, dry_run: false });
      if (!r.ok) {
        setRefusal(r.reasons);
        if (r.data) setPreview(r.data);
        return;
      }
      toast.success(changes.length === 1 ? "Impostazione aggiornata" : `${changes.length} impostazioni aggiornate`, { description: restart ? "Alcune valgono dal prossimo riavvio del Runtime." : undefined });
      discard(changes.map((c) => c.item.key));
      setReason("");
      setCapitalOk(false);
      setReviewOpen(false);
    } catch (e) {
      setFailure(e);
    } finally {
      setSending(false);
      refresh("settings", "agents", "health");
    }
  };

  const agentOf = (k: string) => (k.startsWith("agents.") ? k.split(".")[1].replace(/_/g, " ") : null);

  return (
    <Sheet open={reviewOpen} onOpenChange={setReviewOpen}>
      <SheetContent side={wide ? "right" : "bottom"} className={cn("gap-0 border-line-strong bg-raised p-0", wide ? "w-full max-w-[520px] rounded-l-tile" : "max-h-[92dvh] rounded-t-tile")}>
        <div className="border-b border-line px-5 py-4 pr-12">
          <SheetTitle className="text-base">Rivedi {changes.length === 1 ? "la modifica" : `${changes.length} modifiche`}</SheetTitle>
          <SheetDescription className="mt-1 text-xs text-fg-muted">Il Runtime controlla ogni valore prima di salvarlo. Ogni versione è registrata con te come autore, il motivo e i valori prima e dopo.</SheetDescription>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {loading ? (
            <Bones rows={Math.min(4, changes.length + 1)} />
          ) : isCommandMissing(previewError) ? (
            <Unavailable>Il Runtime non espone ancora il comando update_settings: anteprima e salvataggio arrivano con il backend. Le modifiche restano in bozza.</Unavailable>
          ) : previewError ? (
            <p role="alert" className="text-xs text-down">Anteprima non riuscita: {commandFailure(previewError, "update_settings")}</p>
          ) : null}
          <ul className="space-y-1.5" aria-label="Modifiche">
            {rows.map(({ item, value, p }) => (
              <li key={item.key} className={cn("rounded-control px-3 py-2.5", p && !p.ok ? "bg-down-soft" : "bg-[oklch(0_0_0/0.18)]")}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                  {p ? p.ok ? <CircleCheck className="size-3.5 shrink-0 text-fg-subtle" aria-label="Accettata" /> : <ShieldX className="size-3.5 shrink-0 text-down" aria-label="Rifiutata" /> : <span className="size-3.5" />}
                  <span className="font-medium text-fg">{item.label}</span>
                  {agentOf(item.key) && <span className="text-fg-subtle">{agentOf(item.key)}</span>}
                  <span className="num ml-auto inline-flex items-center gap-1.5 text-fg-muted">
                    {fmtValue(item, item.value)} <ArrowRight className="size-3" aria-hidden /> <span className="text-fg">{fmtValue(item, value)}</span>
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 pl-5.5 text-2xs text-fg-subtle">
                  {(p?.apply ?? item.apply) === "restart" ? (
                    <Tag icon={RotateCw} tone="warn">Vale dal prossimo riavvio</Tag>
                  ) : (
                    <span>Vale subito, dal prossimo ciclo</span>
                  )}
                  {item.capital && <Tag icon={ShieldAlert}>Capitale</Tag>}
                </div>
                {p && !p.ok && <p className="mt-1.5 pl-5.5 text-xs text-fg">{p.reason ?? "Rifiutata senza motivo"}</p>}
              </li>
            ))}
          </ul>
          {preview?.warnings.length ? (
            <ul className="space-y-1.5">
              {preview.warnings.map((w) => (
                <li key={w} className="flex items-start gap-2 rounded-control bg-warn-soft px-3 py-2 text-xs text-fg">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden /> {w}
                </li>
              ))}
            </ul>
          ) : null}
          {rejected > 0 && (
            <p className="text-xs text-down">
              {rejected === 1 ? "Una voce è stata rifiutata" : `${rejected} voci sono state rifiutate`}: correggila nella pagina o annullala, poi rivedi di nuovo.
            </p>
          )}
          <label className="block pt-1">
            <span className="text-2xs text-fg-subtle">Motivo (obbligatorio, resta nello storico)</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Es. cicli più frequenti nella prima ora di sessione" className={cn(fieldClass, "mt-1 h-auto resize-none py-2")} />
          </label>
          {capital && (
            <label className="flex items-start gap-2.5 rounded-control border border-line-strong px-3 py-2.5 text-xs text-fg">
              <input type="checkbox" checked={capitalOk} onChange={(e) => setCapitalOk(e.target.checked)} className="mt-0.5 size-3.5 accent-[var(--accent-strong)]" />
              <span>
                <span className="font-medium">Confermo la modifica che tocca il capitale.</span>{" "}
                <span className="text-fg-muted">Cambia chi approva gli ordini prima dell'invio al broker. Il Risk Gate resta sovrano in ogni modalità.</span>
              </span>
            </label>
          )}
          {failure ? <p role="alert" className="text-xs text-down">{commandFailure(failure, "update_settings")}</p> : null}
          {refusal && (
            <div role="alert" className="rounded-control border border-[oklch(0.67_0.195_20/0.4)] bg-down-soft px-3 py-2.5 text-xs">
              <p className="flex items-center gap-1.5 font-medium text-down">
                <ShieldX className="size-3.5" /> Rifiutato dal Runtime
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-fg">
                {(refusal.length ? refusal : ["Nessuna ragione indicata"]).map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 border-t border-line px-5 py-3">
          <Button variant="ghost" className="mr-auto" onClick={() => setReviewOpen(false)}>
            Torna alla pagina
          </Button>
          <Button data-action="confirm-settings" disabled={!canSend} onClick={submit} title={!reasonOk ? "Scrivi un motivo di almeno 5 caratteri" : capital && !capitalOk ? "Conferma la modifica che tocca il capitale" : undefined}>
            Conferma e applica
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ---------- history ----------

/** Values as they were right after `version`, according to the history: what a restore would bring back. */
function restoreDiff(history: { version: number; changes: { key: string; old: SettingValue; new: SettingValue }[] }[], version: number) {
  const back = new Map<string, SettingValue>();
  for (const h of history.filter((x) => x.version > version)) for (const c of h.changes) back.set(c.key, c.old);
  return back;
}

export function SettingsHistory({ section }: { section: SectionId }) {
  const q = useSettingsHistory();
  const { items, settings } = useDraft();
  const { writable } = useShell();
  const now = useNow(60_000);
  const [restoring, setRestoring] = useState<number | null>(null);
  const label = (k: string) => {
    const i = items.get(k);
    const agent = k.startsWith("agents.") ? k.split(".")[1].replace(/_/g, " ") : null;
    return i ? `${i.label}${agent ? ` · ${agent}` : ""}` : k;
  };
  const sectionLabel = SECTIONS.find((s) => s.id === section)?.label ?? "";

  let body: ReactNode;
  if (q.isPending) body = <Bones rows={2} className="px-4 pb-4" />;
  else if (q.isError) body = <p className="px-4 pb-4 text-xs text-down">Storico non disponibile: {q.error.message}</p>;
  else if (q.data.source === "unavailable") body = <Unavailable className="mx-4 mb-4">{q.data.note}</Unavailable>;
  else {
    const all = q.data.data;
    const mine = all.filter((h) => h.changes.some((c) => sectionOfKey(c.key) === section));
    body = !mine.length ? (
      <p className="flex items-start gap-2 px-4 pb-4 text-xs text-fg-subtle">
        <Info className="mt-px size-3.5 shrink-0" aria-hidden />
        {all.length ? `Nessuna modifica in ${sectionLabel}: valgono i default di configurazione o le versioni registrate in altre sezioni.` : "Nessuna modifica dal cockpit: valgono i default di config/office.toml. La prima modifica diventa la versione 2."}
      </p>
    ) : (
      <ol className="space-y-px px-1.5 pb-2">
        {mine.map((h) => (
          <li key={h.version} className="group flex gap-3 rounded-item px-2.5 py-2 hover:bg-hover/60">
            <AuthorChip actor={h.actor} size="sm" className="mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                <span className="font-medium text-fg">Versione {h.version}</span>
                {settings?.version === h.version && <Tag tone="accent">In uso</Tag>}
                <span className="num text-2xs text-fg-subtle" title={fmtDateTime(h.ts)}>
                  {since(h.ts, now)}
                </span>
              </p>
              <p className="mt-0.5 text-xs text-fg-muted">«{h.reason}»</p>
              <p className="mt-1.5 flex flex-wrap gap-1">
                {h.changes.map((c) => {
                  const i = items.get(c.key);
                  const f = (v: SettingValue) => (i ? fmtValue(i, v) : String(v));
                  return (
                    <span key={c.key} className={cn("num inline-flex max-w-full items-center gap-1 truncate rounded-tag bg-hover px-1.5 py-0.5 text-2xs text-fg-muted", sectionOfKey(c.key) !== section && "opacity-70")}>
                      {label(c.key)} {f(c.old)} <ArrowRight className="size-2.5 shrink-0" aria-hidden /> <span className="text-fg">{f(c.new)}</span>
                    </span>
                  );
                })}
              </p>
            </div>
            {settings && h.version < settings.version && (
              <Button size="xs" variant="ghost" className="shrink-0 self-start opacity-80 group-hover:opacity-100" disabled={!writable} onClick={() => setRestoring(h.version)}>
                <History /> Ripristina
              </Button>
            )}
          </li>
        ))}
      </ol>
    );
  }
  const data = q.data?.source === "runtime" ? q.data.data : [];
  return (
    <Panel title="Storico" meta={settings ? `in uso la versione ${settings.version}` : undefined}>
      {body}
      {restoring !== null && <RestoreDialog version={restoring} back={restoreDiff(data, restoring)} label={label} onClose={() => setRestoring(null)} />}
    </Panel>
  );
}

function RestoreDialog({ version, back, label, onClose }: { version: number; back: Map<string, SettingValue>; label: (k: string) => string; onClose: () => void }) {
  const { client } = useRuntime();
  const { items } = useDraft();
  const refresh = useRefreshCfg();
  const [reason, setReason] = useState("");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [sending, setSending] = useState(false);
  const rows = [...back.entries()].map(([k, v]) => ({ k, v, i: items.get(k) })).filter((r) => !r.i || !same(r.i.value, r.v));

  const submit = async () => {
    setSending(true);
    setRefusal(null);
    setFailure(null);
    try {
      const r = await restoreSettings(client, { version, reason: reason.trim() });
      if (!r.ok) return setRefusal(r.reasons);
      toast.success(`Ripristinata la versione ${version}`);
      onClose();
    } catch (e) {
      setFailure(e);
    } finally {
      setSending(false);
      refresh("settings", "agents");
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[520px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">Ripristinare la versione {version}?</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">Il ripristino crea una nuova versione con i valori di allora: lo storico non si cancella.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 px-5 py-4">
          {rows.length ? (
            <>
              <p className="text-2xs text-fg-subtle">Secondo lo storico tornano così:</p>
              <ul className="space-y-1">
                {rows.map(({ k, v, i }) => (
                  <li key={k} className="flex flex-wrap items-center gap-2 rounded-item bg-[oklch(0_0_0/0.18)] px-3 py-1.5 text-xs">
                    <span className="text-fg">{label(k)}</span>
                    <span className="num ml-auto inline-flex items-center gap-1.5 text-fg-muted">
                      {i ? fmtValue(i, i.value) : "?"} <ArrowRight className="size-3" aria-hidden /> <span className="text-fg">{i ? fmtValue(i, v) : String(v)}</span>
                    </span>
                    {i?.apply === "restart" && <Tag icon={RotateCw} tone="warn">Al riavvio</Tag>}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-xs text-fg-muted">I valori attuali coincidono già con quelli della versione {version}.</p>
          )}
          <label className="block">
            <span className="text-2xs text-fg-subtle">Motivo (obbligatorio)</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={cn(fieldClass, "mt-1 h-auto resize-none py-2")} placeholder="Es. torno alla cadenza di prima: troppi cicli a vuoto" />
          </label>
          {failure ? <p role="alert" className="text-xs text-down">{commandFailure(failure, "restore_settings")}</p> : null}
          {refusal && (
            <div role="alert" className="rounded-control bg-down-soft px-3 py-2 text-xs text-fg">
              <p className="font-medium text-down">Rifiutato dal Runtime</p>
              <ul className="mt-1 list-disc pl-5">{(refusal.length ? refusal : ["Nessuna ragione indicata"]).map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          {isCommandMissing(failure) && <p className="flex items-center gap-1.5 text-2xs text-fg-subtle"><Plug className="size-3" /> Arriva con il backend della pagina.</p>}
        </div>
        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>
            Annulla
          </Button>
          <Button disabled={reason.trim().length < 5 || sending || !rows.length} onClick={submit}>
            Ripristina la versione {version}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
