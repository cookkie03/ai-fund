import { ArrowRight, History, Pencil, Plug, ShieldX } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { isCommandMissing } from "@/features/portfolio/api";
import { commandErrorText, useRiskHistory, useUpdateRiskLimits } from "@/features/portfolio/hooks";
import { LIMIT_NAMES, type LimitName, type LimitUsage, type RiskLimits, type RiskLimitsRead, type Sourced } from "@/features/portfolio/types";
import { fmtAge, fmtDateTime, parseTs, toNum } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { Bones, fmtLimit, LIMIT_META, LimitBar, SourceNote, statusFor, StatusWord, Unavailable } from "./parts";
import { useCapitalBlock } from "./position-actions";

const isLimit = (n: string): n is LimitName => (LIMIT_NAMES as string[]).includes(n);

/** Usage bar for a limit; counts and ratios share the same drawing as fractions. */
function UsageBar({ u, threshold }: { u: LimitUsage; threshold: number }) {
  const meta = isLimit(u.limit) ? LIMIT_META[u.limit] : null;
  if (u.current === null || !meta || meta.kind === "days") return <span className="block h-1.5" />;
  const min = !!meta.min;
  const scale = min ? Math.max(threshold * 3, u.current * 1.1) : Math.max(threshold * 1.25, u.current * 1.08);
  return <LimitBar value={u.current} limit={threshold} scale={scale} status={statusFor(u.current, threshold, min)} min={min} label={`${fmtLimit(u.limit, u.current)} su ${fmtLimit(u.limit, threshold)}`} />;
}

function LimitsTable({ data, mobile }: { data: RiskLimitsRead; mobile: boolean }) {
  const usage = new Map(data.usage.map((u) => [u.limit, u]));
  const rows = LIMIT_NAMES.map((name) => ({ name, threshold: data.limits[name], u: usage.get(name) ?? { limit: name, current: null, threshold: data.limits[name], status: "ok" as const, detail: null } }));
  if (mobile) {
    return (
      <ul className="space-y-px px-1.5">
        {rows.map(({ name, threshold, u }) => (
          <li key={name} className="rounded-item px-2.5 py-2.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] font-medium text-fg">{LIMIT_META[name].label}</span>
              <span className="ml-auto">
                <StatusWord status={u.status} compact />
              </span>
            </div>
            <p className="num mt-0.5 text-2xs text-fg-subtle">
              {u.current === null ? "utilizzo n/d" : fmtLimit(name, u.current)} su {LIMIT_META[name].min ? "minimo" : "massimo"} {fmtLimit(name, threshold)}
            </p>
            <div className="mt-2">
              <UsageBar u={u} threshold={threshold} />
            </div>
            {u.detail && <p className="mt-1.5 text-2xs text-fg-subtle">{u.detail}</p>}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <Table className="tile-table w-full min-w-[860px] border-separate border-spacing-0 px-1.5" containerClassName="overflow-x-auto">
      <TableHeader>
        <TableRow className="border-none text-2xs text-fg-subtle hover:bg-transparent">
          <TableHead scope="col" className="h-8 px-2.5 text-left font-medium border-none">Vincolo</TableHead>
          <TableHead scope="col" className="h-8 px-2.5 text-right font-medium border-none">Soglia</TableHead>
          <TableHead scope="col" className="h-8 px-2.5 text-right font-medium border-none">Attuale</TableHead>
          <TableHead scope="col" className="h-8 w-[22%] px-2.5 text-left font-medium border-none">Utilizzo</TableHead>
          <TableHead scope="col" className="h-8 px-2.5 text-left font-medium border-none">Stato</TableHead>
          <TableHead scope="col" className="h-8 px-2.5 text-left font-medium border-none">Dettaglio</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ name, threshold, u }) => (
          <TableRow key={name} className="border-none hover:[&>td]:bg-hover">
            <TableCell className="h-11 px-2.5 transition-colors border-none">
              <span className="block text-xs font-medium text-fg">{LIMIT_META[name].label}</span>
              <span className="block text-2xs text-fg-subtle">{LIMIT_META[name].hint}</span>
            </TableCell>
            <TableCell className="num h-11 whitespace-nowrap px-2.5 text-right text-xs text-fg transition-colors border-none">
              <span className="text-fg-subtle">{LIMIT_META[name].min ? "≥ " : "≤ "}</span>
              {fmtLimit(name, threshold)}
            </TableCell>
            <TableCell className={cn("num h-11 whitespace-nowrap px-2.5 text-right text-xs transition-colors border-none", u.status === "breach" ? "text-down" : u.status === "near" ? "text-warn" : "text-fg")}>
              {u.current === null ? <span className="text-fg-subtle">—</span> : fmtLimit(name, u.current)}
            </TableCell>
            <TableCell className="h-11 px-2.5 transition-colors border-none">
              <UsageBar u={u} threshold={threshold} />
            </TableCell>
            <TableCell className="h-11 px-2.5 transition-colors border-none">
              <StatusWord status={u.status} />
            </TableCell>
            <TableCell className="h-11 max-w-[260px] truncate px-2.5 text-2xs text-fg-subtle transition-colors border-none" title={u.detail ?? undefined}>
              {u.detail ?? ""}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** Editable value for a limit: fractions are typed as percent, the rest as plain numbers. */
const toInput = (name: LimitName, v: number) => (LIMIT_META[name].kind === "fraction" ? String(+(v * 100).toFixed(3)).replace(".", ",") : String(v).replace(".", ","));
const fromInput = (name: LimitName, s: string): number | null => {
  const n = toNum(s.trim().replace(",", "."));
  if (n === null) return null;
  return LIMIT_META[name].kind === "fraction" ? +(n / 100).toFixed(6) : n;
};
const unit = (name: LimitName) => ({ fraction: "%", count: "pos.", ratio: ": 1", days: "giorni" })[LIMIT_META[name].kind];

function EditDialog({ data, onClose }: { data: RiskLimitsRead; onClose: () => void }) {
  const block = useCapitalBlock();
  const send = useUpdateRiskLimits();
  const [text, setText] = useState<Record<LimitName, string>>(() => Object.fromEntries(LIMIT_NAMES.map((n) => [n, toInput(n, data.limits[n])])) as Record<LimitName, string>);
  const [reason, setReason] = useState("");
  const [step, setStep] = useState<"edit" | "review">("edit");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const usage = new Map(data.usage.map((u) => [u.limit, u]));

  const parsed = LIMIT_NAMES.map((name) => {
    const value = fromInput(name, text[name]);
    const b = data.bounds[name];
    const invalid = value === null ? "Numero non valido" : (LIMIT_META[name].kind === "count" || LIMIT_META[name].kind === "days") && !Number.isInteger(value) ? "Serve un numero intero" : b && (value < b.min || value > b.max) ? `Fuori intervallo: ${fmtLimit(name, b.min)}–${fmtLimit(name, b.max)}` : null;
    return { name, value, invalid, changed: value !== null && Math.abs(value - data.limits[name]) > 1e-9 };
  });
  const changes = parsed.filter((p) => p.changed && !p.invalid);
  const anyInvalid = parsed.some((p) => p.invalid);
  const reasonOk = reason.trim().length >= 5;

  const submit = () => {
    setRefusal(null);
    setFailure(null);
    const limits: Partial<RiskLimits> = Object.fromEntries(changes.map((c) => [c.name, c.value]));
    send.mutate(
      { limits, reason: reason.trim(), confirm: true },
      {
        onSuccess: (res) => (res.ok ? onClose() : setRefusal(res.reasons)),
        onError: (err) => setFailure(err),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[600px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">{step === "edit" ? "Modifica i vincoli del Risk Gate" : `Confermi ${changes.length === 1 ? "la modifica" : `${changes.length} modifiche`}?`}</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">
            {step === "edit"
              ? "Valgono dal prossimo controllo del Risk Gate, per gli agenti e per te. Le posizioni aperte non vengono toccate: un eventuale sforamento resta segnalato."
              : "Ogni modifica è registrata con te come autore, il motivo e i valori prima e dopo."}
          </DialogDescription>
        </DialogHeader>

        {step === "edit" ? (
          <div className="max-h-[60vh] space-y-1 overflow-y-auto px-5 py-3">
            {parsed.map(({ name, invalid, changed }) => {
              const b = data.bounds[name];
              return (
                <label key={name} className={cn("grid grid-cols-[1fr_9rem] items-center gap-3 rounded-item px-2 py-1.5", changed && "bg-accent-soft/60")}>
                  <span className="min-w-0">
                    <span className="block text-xs font-medium text-fg">{LIMIT_META[name].label}</span>
                    <span className={cn("block text-2xs", invalid ? "text-down" : "text-fg-subtle")}>
                      {invalid ?? (b ? `Intervallo ${fmtLimit(name, b.min)}–${fmtLimit(name, b.max)} · ora ${fmtLimit(name, data.limits[name])}` : `Ora ${fmtLimit(name, data.limits[name])}`)}
                    </span>
                  </span>
                  <span className="relative">
                    <Input
                      inputMode="decimal"
                      value={text[name]}
                      onChange={(e) => setText((t) => ({ ...t, [name]: e.target.value }))}
                      aria-invalid={!!invalid}
                      aria-label={LIMIT_META[name].label}
                      className={cn("num h-8 w-full rounded-control border bg-ground pl-2.5 pr-12 text-right text-sm text-fg outline-none transition-colors focus-visible:border-accent-c", invalid ? "border-down" : "border-line-strong")}
                    />
                    <span className="pointer-events-none absolute inset-y-0 right-2.5 grid place-items-center text-2xs text-fg-subtle">{unit(name)}</span>
                  </span>
                </label>
              );
            })}
            <label className="block px-2 pb-1 pt-3">
              <span className="text-2xs text-fg-subtle">Motivo (obbligatorio, lo leggono anche gli agenti)</span>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder="Es. riduco il peso massimo dopo la volatilità della settimana"
                className="mt-1 w-full resize-none rounded-control border-line-strong bg-ground px-2.5 py-2 text-sm text-fg outline-none placeholder:text-fg-subtle focus-visible:border-accent-c"
              />
            </label>
          </div>
        ) : (
          <div className="space-y-3 px-5 py-4">
            <ul className="space-y-2.5">
              {changes.map(({ name, value }) => {
                const u = usage.get(name);
                const before = u?.status ?? "ok";
                const after = u && u.current !== null ? statusFor(u.current, value!, !!LIMIT_META[name].min) : "ok";
                return (
                  <li key={name} className="rounded-control bg-[oklch(0_0_0/0.18)] px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-medium text-fg">{LIMIT_META[name].label}</span>
                      <span className="num ml-auto inline-flex items-center gap-1.5 text-fg-muted">
                        {fmtLimit(name, data.limits[name])} <ArrowRight className="size-3" aria-hidden /> <span className="text-fg">{fmtLimit(name, value)}</span>
                      </span>
                    </div>
                    {u && u.current !== null && (
                      <div className="mt-2 grid grid-cols-[1fr_auto] items-center gap-3">
                        <UsageBar u={u} threshold={value!} />
                        <span className="inline-flex items-center gap-1 text-2xs text-fg-subtle">
                          ora {fmtLimit(name, u.current)}
                          {before !== after ? (
                            <>
                              <StatusWord status={before} compact /> <ArrowRight className="size-3" aria-hidden /> <StatusWord status={after} />
                            </>
                          ) : (
                            <StatusWord status={after} />
                          )}
                        </span>
                      </div>
                    )}
                    {after === "breach" && <p className="mt-1.5 text-2xs text-down">Già oltre la nuova soglia: nessuna posizione verrà chiusa, ma il Risk Gate bloccherà nuovi ordini che peggiorano lo sforamento.</p>}
                  </li>
                );
              })}
            </ul>
            <p className="rounded-control bg-[oklch(0_0_0/0.18)] px-3 py-2 text-xs text-fg-muted">
              <span className="text-fg-subtle">Motivo · </span>
              {reason.trim()}
            </p>
            {isCommandMissing(failure) ? (
              <p className="flex items-start gap-2 text-xs text-fg-muted">
                <Plug className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" /> Il Runtime non espone ancora update_risk_limits: la modifica non è stata applicata.
              </p>
            ) : failure ? (
              <p className="text-xs text-down">{commandErrorText(failure, "update_risk_limits")}</p>
            ) : null}
            {refusal && (
              <Alert variant="destructive">
                <ShieldX className="size-4" />
                <AlertTitle>Rifiutato dal Runtime</AlertTitle>
                <AlertDescription>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-fg">
                    {(refusal.length ? refusal : ["Nessuna ragione indicata"]).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
            {block && <p className="text-xs text-warn">{block}: la modifica non può partire ora.</p>}
          </div>
        )}

        <DialogFooter className="border-t border-line px-5 py-3">
          {step === "edit" ? (
            <>
              <span className="mr-auto self-center text-2xs text-fg-subtle">{changes.length ? `${changes.length} ${changes.length === 1 ? "valore cambiato" : "valori cambiati"}` : "Nessun valore cambiato"}</span>
              <Button variant="ghost" onClick={onClose}>
                Annulla
              </Button>
              <Button variant="outline" disabled={!changes.length || anyInvalid || !reasonOk} onClick={() => setStep("review")} title={!reasonOk && changes.length ? "Scrivi un motivo di almeno 5 caratteri" : undefined}>
                Rivedi
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" className="mr-auto" onClick={() => setStep("edit")}>
                Indietro
              </Button>
              <Button data-action="confirm-limits" disabled={!!block || send.isPending} onClick={submit}>
                Conferma e applica
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Change({ k, before, after }: { k: string; before: unknown; after: unknown }) {
  const b = toNum(before);
  const a = toNum(after);
  return (
    <span className="num inline-flex items-center gap-1 whitespace-nowrap rounded-tag bg-hover px-1.5 py-0.5 text-2xs text-fg-muted">
      {isLimit(k) ? LIMIT_META[k].label : k} {fmtLimit(k, b)} <ArrowRight className="size-2.5" aria-hidden /> <span className="text-fg">{fmtLimit(k, a)}</span>
    </span>
  );
}

function HistoryList() {
  const q = useRiskHistory();
  const now = useNow(60_000);
  let body: ReactNode;
  if (q.isPending) body = <Bones rows={2} className="px-4" />;
  else if (q.isError) body = <p className="px-4 text-xs text-down">Storico non disponibile: {q.error.message}</p>;
  else if (q.data.source === "unavailable") body = <Unavailable className="mx-4">{q.data.note}</Unavailable>;
  else if (!q.data.data.length) body = <p className="px-4 text-xs text-fg-subtle">Nessuna modifica: valgono i default di configurazione.</p>;
  else
    body = (
      <ol className="space-y-px px-1.5">
        {q.data.data.map((h) => (
          <li key={h.version} className="flex gap-3 rounded-item px-2.5 py-2">
            <AuthorChip actor={h.actor} size="sm" className="mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                <span className="font-medium text-fg">Versione {h.version}</span>
                <span className="num text-2xs text-fg-subtle" title={fmtDateTime(h.ts)}>
                  {fmtAge(parseTs(h.ts), now)} fa
                </span>
              </p>
              <p className="mt-0.5 text-xs text-fg-muted">«{h.reason}»</p>
              <p className="mt-1.5 flex flex-wrap gap-1">
                {Object.keys(h.after).map((k) => (
                  <Change key={k} k={k} before={(h.before as Record<string, unknown>)[k]} after={(h.after as Record<string, unknown>)[k]} />
                ))}
              </p>
            </div>
          </li>
        ))}
      </ol>
    );
  return (
    <section aria-label="Storico delle modifiche" className="pb-3 pt-2">
      <h3 className="flex h-9 items-center gap-1.5 px-4 text-xs font-semibold text-fg">
        <History className="size-3.5 text-fg-subtle" aria-hidden /> Storico delle modifiche
      </h3>
      {body}
    </section>
  );
}

export function RiskPanel({ q, mobile, before }: { q: { data?: Sourced<RiskLimitsRead>; isPending: boolean; error: Error | null }; mobile: boolean; before?: ReactNode }) {
  const [editing, setEditing] = useState(false);
  const block = useCapitalBlock();
  const now = useNow(60_000);
  const data = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const live = q.data?.source === "runtime";
  const breaches = data?.usage.filter((u) => u.status === "breach").length ?? 0;
  const editBlock = !live ? "Il Runtime non espone ancora risk_limits" : block;

  return (
    <div>
      {before}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 pb-1 pt-2">
        <p className="text-2xs text-fg-subtle">
          {data && live ? (
            <>
              Versione {data.version}
              {data.updated_ts && (
                <>
                  {" "}· modificata {data.updated_by ? <>da <AuthorChip actor={data.updated_by} size="xs" label /></> : ""} {fmtAge(parseTs(data.updated_ts), now)} fa
                </>
              )}
            </>
          ) : (
            "Limiti deterministici: il Risk Gate li applica a ogni ordine, degli agenti e tuo."
          )}
        </p>
        <Button size="sm" variant="outline" className="ml-auto" disabled={!data || !!editBlock} onClick={() => setEditing(true)} title={editBlock ?? undefined}>
          <Pencil /> Modifica vincoli
        </Button>
      </div>
      {breaches > 0 && (
        <p role="status" className="mx-4 mt-1.5 rounded-control bg-down-soft px-3 py-2 text-xs text-fg">
          <span className="font-medium text-down">{breaches === 1 ? "Un vincolo è oltre la soglia." : `${breaches} vincoli sono oltre la soglia.`}</span> Le posizioni esistenti non vengono chiuse: il Risk Gate blocca solo i nuovi ordini che peggiorano lo sforamento.
        </p>
      )}
      {q.isPending ? (
        <Bones rows={6} className="p-4" />
      ) : q.error ? (
        <p className="px-4 py-6 text-xs text-down">Vincoli non disponibili: {q.error.message}</p>
      ) : data ? (
        <div className="pt-1.5">
          <LimitsTable data={data} mobile={mobile} />
        </div>
      ) : null}
      <SourceNote sourced={q.data} className="px-4 pb-1 pt-2" />
      <div className="mx-4 mt-2 border-t border-line/70" />
      <HistoryList />
      {editing && data && <EditDialog data={data} onClose={() => setEditing(false)} />}
    </div>
  );
}
