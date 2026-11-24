import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CircleSlash, Loader2, Plus, RefreshCw, Rss, Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { COMMAND_ENDPOINT, isCommandMissing } from "@/features/news/api";
import { useNewsSources } from "@/features/news/hooks";
import { hostOf, providerLabel, SOURCE_STATUS_LABEL } from "@/features/news/labels";
import type { NewsSource } from "@/features/news/types";
import { RuntimeError } from "@/lib/runtime/client";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import type { CommandName, CommandPayloads } from "@/lib/runtime/types";
import { fmtAge, parseTs } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { Notice, ReadError } from "./parts";

type Outcome = { tone: "ok" | "warn"; text: string; reasons?: string[] } | null;

/** Runs a source command and phrases the outcome inline, next to the control that caused it. */
function useSourceCommand() {
  const { client } = useRuntime();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const run = async <N extends CommandName>(name: N, payload: CommandPayloads[N], key: string, success: string): Promise<boolean> => {
    setBusy(key);
    setOutcome(null);
    try {
      const res = await client.command(name, payload);
      if (!res.ok) {
        setOutcome({ tone: "warn", text: "Il Runtime ha rifiutato il comando", reasons: res.reasons.length ? res.reasons : ["Nessuna ragione indicata"] });
        return false;
      }
      setOutcome({ tone: "ok", text: success });
      return true;
    } catch (err) {
      if (isCommandMissing(err)) setOutcome({ tone: "warn", text: `Il Runtime non espone ancora ${COMMAND_ENDPOINT(name)}` });
      else if (err instanceof RuntimeError && err.unreachable) setOutcome({ tone: "warn", text: "Runtime irraggiungibile: il comando non è stato inviato" });
      else setOutcome({ tone: "warn", text: err instanceof Error ? err.message : String(err) });
      return false;
    } finally {
      setBusy(null);
      qc.invalidateQueries({ queryKey: ["news_sources"] });
    }
  };
  return { run, busy, outcome };
}

function StatusWord({ s }: { s: NewsSource }) {
  if (!s.enabled) return <span className="inline-flex items-center gap-1 text-2xs text-fg-subtle"><CircleSlash className="size-3" /> Disattivata</span>;
  const Icon = s.status === "ok" ? Check : s.status === "error" ? AlertTriangle : CircleSlash;
  return (
    <span className={cn("inline-flex items-center gap-1 text-2xs", s.status === "error" ? "rounded-tag bg-warn-soft px-1 text-warn" : "text-fg-subtle")}>
      <Icon className="size-3" /> {SOURCE_STATUS_LABEL[s.status]}
    </span>
  );
}

function Switch({ on, label, disabled, onChange }: { on: boolean; label: string; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cn("relative h-5 w-8 shrink-0 rounded-item transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring/60 disabled:opacity-40", on ? "bg-accent-strong" : "bg-line-strong")}
    >
      <span className={cn("absolute left-0 top-0.5 size-4 rounded-tag bg-fg shadow-[0_1px_2px_oklch(0_0_0/0.4)] transition-transform duration-150", on ? "translate-x-3.5" : "translate-x-0.5")} />
    </button>
  );
}

function SourceRow({ s, now, cmd, writable }: { s: NewsSource; now: number; cmd: ReturnType<typeof useSourceCommand>; writable: boolean }) {
  const [confirm, setConfirm] = useState(false);
  const host = hostOf(s.url);
  return (
    <li data-source={s.id} className="rounded-item px-3 py-2.5 hover:bg-hover/50">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-fg">{s.name}</span>
            <StatusWord s={s} />
          </p>
          <p className="mt-0.5 truncate text-2xs text-fg-subtle">
            {providerLabel(s.provider)}
            {host && <> · {host}</>}
            {" · "}
            <span className="num">{s.items_24h}</span> nelle ultime 24 h
            {s.last_fetch_ts && <> · letta <span className="num">{fmtAge(parseTs(s.last_fetch_ts), now)}</span> fa</>}
          </p>
          {s.last_error && <p className={cn("mt-1 text-xs leading-4", s.status === "error" ? "text-warn" : "text-fg-muted")}>{s.last_error}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`Aggiorna ${s.name} ora`}
                disabled={!writable || !s.enabled || cmd.busy !== null}
                onClick={() => cmd.run("refresh_news", { source_id: s.id }, `refresh-${s.id}`, `Aggiornamento di ${s.name} avviato`)}
                className="grid size-7 place-items-center rounded-item text-fg-subtle transition-colors hover:bg-hover hover:text-fg disabled:opacity-35"
              >
                <RefreshCw className={cn("size-3.5", cmd.busy === `refresh-${s.id}` && "animate-spin")} />
              </button>
            </TooltipTrigger>
            <TooltipContent>Aggiorna ora</TooltipContent>
          </Tooltip>
          <Switch
            on={s.enabled}
            label={`${s.enabled ? "Disattiva" : "Attiva"} ${s.name}`}
            disabled={!writable || cmd.busy !== null}
            onChange={(v) => cmd.run("set_news_source_enabled", { source_id: s.id, enabled: v }, `enable-${s.id}`, `${s.name} ${v ? "attivata" : "disattivata"}`)}
          />
        </div>
      </div>
      {s.provider === "rss" && (
        <div className="mt-1.5 flex items-center gap-1.5">
          {confirm ? (
            <>
              <span className="text-2xs text-fg-muted">Togliere il feed? Le notizie già arrivate restano nell'archivio.</span>
              <Button
                variant="destructive"
                size="xs"
                disabled={!writable || cmd.busy !== null}
                onClick={async () => {
                  await cmd.run("remove_news_source", { source_id: s.id }, `remove-${s.id}`, `${s.name} tolta`);
                  setConfirm(false);
                }}
              >
                Togli
              </Button>
              <Button variant="ghost" size="xs" onClick={() => setConfirm(false)}>
                Annulla
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="xs" disabled={!writable} onClick={() => setConfirm(true)} className="-ml-2 text-fg-subtle">
              <Trash2 /> Togli il feed
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function AddFeed({ cmd, writable }: { cmd: ReturnType<typeof useSourceCommand>; writable: boolean }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const valid = /^https?:\/\/[^\s]+\.[^\s]+/i.test(url.trim());
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || !writable) return;
    const ok = await cmd.run("add_news_source", { provider: "rss", name: name.trim() || hostOf(url.trim()) || url.trim(), url: url.trim() }, "add", "Feed aggiunto: la prima lettura arriva al prossimo ciclo");
    if (ok) {
      setName("");
      setUrl("");
    }
  };
  const field = "h-8 w-full rounded-control border border-line-strong bg-[oklch(0.205_0.008_260)] px-2.5 text-xs text-fg outline-none placeholder:text-fg-subtle focus:border-accent-c/70";
  return (
    <form onSubmit={submit} className="space-y-2 rounded-control bg-[oklch(0_0_0/0.18)] p-3" aria-label="Aggiungi un feed RSS">
      <p className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
        <Rss className="size-3.5 text-fg-subtle" /> Aggiungi un feed RSS o Atom
      </p>
      <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://esempio.it/feed.xml" aria-label="Indirizzo del feed" inputMode="url" className={field} />
      <div className="flex gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome (facoltativo)" aria-label="Nome del feed" className={field} />
        <Button type="submit" size="sm" disabled={!valid || !writable || cmd.busy !== null} className="h-8 shrink-0">
          {cmd.busy === "add" ? <Loader2 className="animate-spin" /> : <Plus />} Aggiungi
        </Button>
      </div>
      {url && !valid && <p className="text-2xs text-fg-muted">Solo indirizzi http o https completi.</p>}
    </form>
  );
}

/** Fonti: a right sheet, occasional configuration rather than reading. */
export function SourcesSheet({ trigger }: { trigger: (problems: number) => ReactNode }) {
  const q = useNewsSources();
  const now = useNow(30_000);
  const { writable } = useShell();
  const cmd = useSourceCommand();
  const list = q.data?.state === "ok" ? q.data.data : null;
  const problems = list?.filter((s) => s.enabled && s.status !== "ok").length ?? 0;

  let body: ReactNode;
  if (q.isPending) body = <div aria-busy className="m-3 h-40 animate-pulse rounded-control bg-hover/60" />;
  else if (q.isError) body = <ReadError error={q.error} what="le fonti" />;
  else if (q.data.state === "unavailable")
    body = (
      <Notice
        title="Lo stato delle fonti non è ancora esposto"
        detail={
          <>
            Comparirà quando il Runtime esporrà <code className="text-fg">{q.data.endpoint}</code>.
          </>
        }
      />
    );
  else body = <ul className="space-y-0.5 px-1.5">{(list ?? []).map((s) => <SourceRow key={s.id} s={s} now={now} cmd={cmd} writable={writable} />)}</ul>;

  return (
    <Sheet>
      <SheetTrigger asChild>{trigger(problems)}</SheetTrigger>
      <SheetContent side="right" className="w-full max-w-[440px] gap-0 rounded-l-tile border-0 bg-ground p-0 sm:max-w-[440px] [&>button]:hidden">
        <div className="flex h-14 shrink-0 items-center gap-2 px-4">
          <SheetTitle className="text-[15px] font-semibold text-fg">Fonti</SheetTitle>
          <SheetDescription className="sr-only">Stato delle fonti di notizie, feed RSS, attivazione e aggiornamento</SheetDescription>
          {list && <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">{list.length}</span>}
          <Button variant="ghost" size="sm" className="ml-auto" disabled={!writable || cmd.busy !== null || !list} onClick={() => cmd.run("refresh_news", { source_id: null }, "refresh-all", "Aggiornamento di tutte le fonti avviato")}>
            <RefreshCw className={cn(cmd.busy === "refresh-all" && "animate-spin")} /> Aggiorna tutte
          </Button>
        </div>
        <p className="px-4 pb-2 text-xs leading-[1.1rem] text-fg-muted">Le stesse fonti per te e per gli agenti: una sola ingestione nel Runtime, ogni notizia porta fonte e provider.</p>
        {cmd.outcome && (
          <div role={cmd.outcome.tone === "warn" ? "alert" : "status"} className={cn("mx-3 mb-2 rounded-item px-3 py-2 text-xs leading-4", cmd.outcome.tone === "warn" ? "bg-warn-soft" : "bg-hover")}>
            <p className="font-medium text-fg">{cmd.outcome.text}</p>
            {cmd.outcome.reasons && (
              <ul className="mt-0.5 text-fg-muted">
                {cmd.outcome.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto pb-3">{body}</div>
        <div className="shrink-0 p-3 pt-0">
          <AddFeed cmd={cmd} writable={writable} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
