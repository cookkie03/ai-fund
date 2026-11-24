import { Archive, CircleAlert, CircleCheck, CircleX, DatabaseBackup, Loader2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { backupDb, commandFailure } from "@/features/settings/api";
import { useBackups, useRefreshCfg, useRuntimeHealth, useSettings } from "@/features/settings/hooks";
import type { RuntimeHealth } from "@/features/settings/types";
import { fmtAge, fmtDateTime, fmtWhen, parseTs } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { LimitBar, statusFor } from "@/pages/portafoglio/parts";
import { useShell } from "@/shell/shell-state";
import { SettingsHistory, SettingsPanels } from "./draft";
import { Bones, fmtBytes, fmtUptime, Panel, Tag, Unavailable } from "./parts";
import { since } from "./parts";

const MB = 1024 * 1024;

/** DB plus WAL against the alert threshold, on the Portafoglio threshold tick. */
export function dbState(h: RuntimeHealth | null) {
  if (!h || h.db.size_bytes === null) return null;
  const total = h.db.size_bytes + (h.db.wal_bytes ?? 0);
  const limit = h.db.alert_mb !== null ? h.db.alert_mb * MB : null;
  return { total, limit, status: statusFor(total, limit) };
}

function DatabasePanel() {
  const q = useRuntimeHealth();
  const now = useNow(60_000);
  const h = q.data?.source === "runtime" ? q.data.data : null;
  const d = dbState(h);
  return (
    <Panel title="Database" meta={h?.db.path_label ?? undefined}>
      {q.isPending ? (
        <Bones rows={2} className="px-4 pb-4" />
      ) : q.error ? (
        <p role="alert" className="px-4 pb-4 text-xs text-down">Database non disponibile: {q.error.message}</p>
      ) : !h || !d ? (
        <Unavailable className="mx-4 mb-4">{q.data?.source === "unavailable" ? q.data.note : "Il Runtime non riporta la dimensione del database."}</Unavailable>
      ) : (
        <div className="px-4 pb-4">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="num text-[15px] font-semibold text-fg">{fmtBytes(d.total)}</span>
            <span className="num text-2xs text-fg-subtle">
              DB {fmtBytes(h.db.size_bytes)} + WAL {fmtBytes(h.db.wal_bytes)}
              {d.limit !== null && <> · soglia {fmtBytes(d.limit)}</>}
            </span>
            {d.status !== "ok" && (
              <Tag icon={d.status === "breach" ? CircleX : CircleAlert} tone={d.status === "breach" ? "down" : "warn"} className="ml-auto">
                {d.status === "breach" ? "Oltre la soglia" : "Vicino alla soglia"}
              </Tag>
            )}
          </div>
          {d.limit !== null && <LimitBar className="mt-2.5" value={d.total} limit={d.limit} scale={Math.max(d.limit * 1.25, d.total * 1.08)} status={d.status} label={`${fmtBytes(d.total)} su ${fmtBytes(d.limit)}`} />}
          {d.status === "breach" && (
            <p className="mt-2.5 text-xs text-fg-muted">
              Il database ha superato la soglia di avviso. Riduci la retention qui sotto o alza la soglia; la compattazione avviene al prossimo giro del job <span className="font-mono text-[11.5px]">retention</span>.
            </p>
          )}
          <p className="num mt-2 text-2xs text-fg-subtle">
            Ultimo backup {h.db.last_backup_ts ? <span title={fmtDateTime(h.db.last_backup_ts)}>{since(h.db.last_backup_ts, now)}</span> : "mai"}
          </p>
        </div>
      )}
    </Panel>
  );
}

function BackupsPanel() {
  const q = useBackups();
  const { client } = useRuntime();
  const { writable } = useShell();
  const refresh = useRefreshCfg();
  const now = useNow(60_000);
  const [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true);
    try {
      const r = await backupDb(client);
      if (!r.ok) toast.error("Backup rifiutato", { description: r.reasons.join(" · ") || "Nessuna ragione indicata" });
      else toast.success("Backup creato", { description: r.data.name ?? undefined });
    } catch (e) {
      toast.error("Backup non riuscito", { description: commandFailure(e, "backup_db") });
    } finally {
      setBusy(false);
      refresh("backups", "health");
    }
  };
  const list = q.data?.source === "runtime" ? q.data.data : null;
  return (
    <Panel
      title="Backup"
      meta={list ? `${list.length}` : undefined}
      end={
        <Button size="sm" variant="outline" disabled={!writable || busy} onClick={create} title={!writable ? "Runtime irraggiungibile" : undefined}>
          {busy ? <Loader2 className="animate-spin" /> : <DatabaseBackup />} Crea backup
        </Button>
      }
    >
      {q.isPending ? (
        <Bones rows={2} className="px-4 pb-4" />
      ) : q.error ? (
        <p role="alert" className="px-4 pb-4 text-xs text-down">Backup non disponibili: {q.error.message}</p>
      ) : !list ? (
        <Unavailable className="mx-4 mb-4">{q.data?.source === "unavailable" ? q.data.note : null}</Unavailable>
      ) : !list.length ? (
        <p className="px-4 pb-4 text-xs text-fg-subtle">Nessun backup in data/backups/. «Crea backup» ne fa uno ora, a caldo, senza fermare il Runtime.</p>
      ) : (
        <ul className="space-y-px px-1.5 pb-2">
          {list.map((b, i) => (
            <li key={b.name} className={cn("flex items-center gap-3 rounded-item px-2.5 py-2", i === 0 && "row-arrive")}>
              <Archive className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-fg">{b.name}</span>
              <span className="num shrink-0 text-2xs text-fg-subtle">{fmtBytes(b.size_bytes)}</span>
              <span className="num w-20 shrink-0 text-right text-2xs text-fg-muted" title={fmtDateTime(b.ts)}>{since(b.ts, now)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="px-4 pb-3 text-2xs text-fg-subtle">Il ripristino resta manuale: si fa a Runtime fermo, copiando un backup al posto del database (docs/storage.md).</p>
    </Panel>
  );
}

export function DataSection() {
  const settings = useSettings();
  return (
    <>
      <DatabasePanel />
      <SettingsPanels section="dati" q={settings} />
      <BackupsPanel />
      <SettingsHistory section="dati" />
    </>
  );
}

// ---------- Salute del Runtime ----------

function Meter({ label, children, foot }: { label: string; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-2xs text-fg-subtle">{label}</dt>
      <dd className="num mt-0.5 truncate text-[13px] font-medium text-fg">{children}</dd>
      {foot && <dd className="mt-0.5 truncate text-2xs text-fg-subtle">{foot}</dd>}
    </div>
  );
}

function Link2({ ok, label, detail }: { ok: boolean; label: string; detail: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-2xs text-fg-subtle">{label}</dt>
      <dd className={cn("mt-0.5 flex items-center gap-1.5 text-[13px] font-medium", ok ? "text-fg" : "text-down")}>
        {ok ? <CircleCheck className="size-3.5 shrink-0 text-fg-subtle" aria-hidden /> : <CircleX className="size-3.5 shrink-0" aria-hidden />}
        {ok ? "Raggiungibile" : "Non raggiungibile"}
      </dd>
      {detail && <dd className="mt-0.5 truncate text-2xs text-fg-subtle" title={detail}>{detail}</dd>}
    </div>
  );
}

export function HealthSection({ mobile }: { mobile: boolean }) {
  const q = useRuntimeHealth();
  const now = useNow(1000);
  const { connection } = useRuntime();
  const h = q.data?.source === "runtime" ? q.data.data : null;
  const d = dbState(h);
  const live = connection.reachable && q.isSuccess && !q.isRefetchError;
  const uptime = h?.started_ts ? Math.max(0, (now - (parseTs(h.started_ts) ?? now)) / 1000) : h?.uptime_s ?? null;
  const failing = h?.jobs.filter((j) => j.last_status === "error") ?? [];

  if (q.isPending) return <Panel title="Runtime"><Bones rows={3} className="px-4 pb-4" /></Panel>;
  if (q.error) return <Panel title="Runtime"><p role="alert" className="px-4 pb-4 text-xs text-down">Salute non disponibile: {q.error.message}</p></Panel>;
  if (!h) return <Panel title="Runtime"><Unavailable className="mx-4 mb-4">{q.data?.source === "unavailable" ? q.data.note : null} Il punto verde in alto dice solo se il Runtime risponde.</Unavailable></Panel>;

  return (
    <>
      <Panel
        title="Runtime"
        meta={h.version ? `v${h.version}${h.commit ? ` · ${h.commit.slice(0, 7)}` : ""}` : undefined}
        end={
          <span className={cn("inline-flex items-center gap-1.5 pr-2 text-2xs", live ? "text-fg-muted" : "text-warn")}>
            <span aria-hidden className={cn("size-1.5 rounded-full", live ? "bg-fg-muted" : "bg-warn")} />
            {live ? "Dal vivo" : `Fermo da ${fmtAge(q.dataUpdatedAt, now)}`}
          </span>
        }
      >
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 px-4 pb-4 md:grid-cols-3 xl:grid-cols-6">
          <Meter label="Attivo da" foot={h.started_ts ? `avviato ${fmtWhen(h.started_ts, now)}` : undefined}>
            {fmtUptime(uptime)}
          </Meter>
          <Meter label="Client in ascolto" foot="connessioni SSE aperte">{h.sse_clients ?? "—"}</Meter>
          <Meter label="Database" foot={d?.limit ? `soglia ${fmtBytes(d.limit)}` : undefined}>
            <Link to="/configurazioni/dati" className={cn("hover:underline", d?.status === "breach" ? "text-down" : d?.status === "near" ? "text-warn" : "")}>
              {fmtBytes(d?.total)}
            </Link>
          </Meter>
          <Meter label="Job in errore">
            <span className={failing.length ? "text-down" : undefined}>{failing.length}</span>
            <span className="text-fg-subtle"> / {h.jobs.length}</span>
          </Meter>
          <Link2 ok={h.broker.ok} label="Broker" detail={h.broker.detail} />
          <Link2 ok={h.llm.ok} label="Provider LLM" detail={h.llm.detail} />
        </dl>
      </Panel>

      <Panel title="Job dello scheduler" meta={`${h.jobs.length}`}>
        {!h.jobs.length ? (
          <p className="px-4 pb-4 text-xs text-fg-subtle">Nessun job registrato.</p>
        ) : mobile ? (
          <ul className="space-y-px px-1.5 pb-2">
            {h.jobs.map((j) => (
              <li key={j.name} className={cn("rounded-item px-2.5 py-2", j.last_status === "error" && "bg-down-soft/60")}>
                <p className="flex items-center gap-2">
                  <span className="font-mono text-[11.5px] text-fg">{j.name}</span>
                  <span className="ml-auto"><JobStatus s={j.last_status} /></span>
                </p>
                <p className="num mt-0.5 text-2xs text-fg-subtle">
                  ultima {j.last_run_ts ? `${since(j.last_run_ts, now)}` : "mai"} · prossima {j.next_run_ts ? fmtWhen(j.next_run_ts, now) : "—"}
                </p>
                {j.last_error && <p className="mt-1 text-xs text-fg">{j.last_error}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <div className="overflow-x-auto pb-2">
            <table className="w-full min-w-[640px] border-separate border-spacing-0 px-1.5">
              <thead>
                <tr className="text-2xs text-fg-subtle">
                  <th scope="col" className="h-8 px-2.5 text-left font-medium">Job</th>
                  <th scope="col" className="h-8 px-2.5 text-left font-medium">Esito</th>
                  <th scope="col" className="h-8 px-2.5 text-right font-medium">Ultima</th>
                  <th scope="col" className="h-8 px-2.5 text-right font-medium">Prossima</th>
                  <th scope="col" className="h-8 px-2.5 text-left font-medium">Errore</th>
                </tr>
              </thead>
              <tbody>
                {h.jobs.map((j) => (
                  <tr key={j.name} className={cn("[&>td]:transition-colors", j.last_status === "error" ? "[&>td]:bg-down-soft/50" : "hover:[&>td]:bg-hover")}>
                    <td className="h-10 rounded-l-item px-2.5 font-mono text-[11.5px] text-fg">{j.name}</td>
                    <td className="h-10 px-2.5"><JobStatus s={j.last_status} /></td>
                    <td className="num h-10 whitespace-nowrap px-2.5 text-right text-xs text-fg-muted" title={j.last_run_ts ? fmtDateTime(j.last_run_ts) : undefined}>{j.last_run_ts ? `${since(j.last_run_ts, now)}` : "mai"}</td>
                    <td className="num h-10 whitespace-nowrap px-2.5 text-right text-xs text-fg-muted">{j.next_run_ts ? fmtWhen(j.next_run_ts, now) : "—"}</td>
                    <td className="h-10 max-w-[320px] truncate rounded-r-item px-2.5 text-xs text-fg" title={j.last_error ?? undefined}>{j.last_error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Ultimi errori" meta={h.errors.length ? `${h.errors.length}` : undefined}>
        {!h.errors.length ? (
          <p className="flex items-center gap-2 px-4 pb-4 text-xs text-fg-subtle"><CircleCheck className="size-3.5" aria-hidden /> Nessun errore recente.</p>
        ) : (
          <ol className="space-y-px px-1.5 pb-2">
            {h.errors.map((e, i) => (
              <li key={`${e.ts}-${i}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-item px-2.5 py-2 md:grid-cols-[5.5rem_9rem_minmax(0,1fr)]">
                <span className="num text-2xs text-fg-subtle" title={fmtDateTime(e.ts)}>{since(e.ts, now)}</span>
                <span className="truncate font-mono text-[11.5px] text-fg-muted">{e.source}</span>
                <span className="col-span-2 text-xs text-fg md:col-span-1">{e.message}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </>
  );
}

function JobStatus({ s }: { s: "ok" | "error" | null }) {
  if (s === "error") return <Tag icon={CircleX} tone="down">Errore</Tag>;
  if (s === "ok") return <span className="inline-flex items-center gap-1 text-2xs text-fg-subtle"><CircleCheck className="size-3" aria-hidden /> Ok</span>;
  return <span className="text-2xs text-fg-subtle">Mai eseguito</span>;
}
