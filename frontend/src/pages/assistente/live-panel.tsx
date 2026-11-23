import { OctagonPause, PanelRightClose, Play } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { IconButton } from "@/components/tile";
import { actionTitle } from "@/features/bridge/action-card";
import { useBridgeActions, useRuntimeDown } from "@/features/bridge/hooks";
import { useBridge } from "@/features/bridge/state";
import { useProposals } from "@/features/dossier/hooks";
import { useOfficeAgents } from "@/features/office/hooks";
import { useSummary } from "@/features/portfolio/hooks";
import { author } from "@/lib/authors";
import { fmtAge, fmtMoney, fmtPct, parseTs } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { StatusDot, useFreshness } from "@/shell/status";

function Section({ title, to, toLabel, children }: { title: string; to?: string; toLabel?: string; children: ReactNode }) {
  return (
    <section className="px-4 py-3" aria-label={title}>
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className="text-2xs font-medium text-fg-subtle">{title}</h3>
        {to && (
          <Link to={to} className="-my-1 ml-auto inline-flex h-6 items-center rounded-item px-1.5 text-2xs text-fg-subtle underline-offset-4 hover:text-fg hover:underline">
            {toLabel}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function Line({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5 text-xs">
      <span className="text-fg-muted">{label}</span>
      <span className="ml-auto flex items-baseline gap-1.5 text-right">
        {hint && <span className="num text-2xs text-fg-subtle">{hint}</span>}
        <span className="num text-fg">{value}</span>
      </span>
    </div>
  );
}

const Quiet = ({ children }: { children: ReactNode }) => <p className="text-xs leading-relaxed text-fg-subtle">{children}</p>;

function Portfolio() {
  const down = useRuntimeDown();
  const q = useSummary();
  if (q.isPending && down) return <Quiet>Runtime irraggiungibile.</Quiet>;
  if (q.isPending) return <span className="block h-10 animate-pulse rounded-item bg-hover" />;
  if (q.isError) return <Quiet>Portafoglio non disponibile: {q.error.message}</Quiet>;
  if (q.data.source === "unavailable") return <Quiet>{q.data.note}</Quiet>;
  const s = q.data.data;
  if (!s) return <Quiet>Nessuno snapshot del portafoglio ancora.</Quiet>;
  const dc = s.day_change;
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="num text-[15px] font-semibold tracking-[-0.01em] text-fg">{fmtMoney(s.equity)}</span>
        {dc !== null && (
          <span className={cn("num rounded-tag px-1.5 text-2xs font-medium leading-5", dc > 0 ? "bg-up-soft text-up" : dc < 0 ? "bg-down-soft text-down" : "bg-hover text-fg-muted")}>
            {fmtMoney(dc, { sign: true })}
            {s.day_change_fraction !== null && ` · ${fmtPct(s.day_change_fraction * 100)}`}
          </span>
        )}
      </div>
      <div className="mt-1.5">
        <Line label="P&L non realizzato" value={<span className={s.unrealized_pnl > 0 ? "text-up" : s.unrealized_pnl < 0 ? "text-down" : ""}>{fmtMoney(s.unrealized_pnl, { sign: true })}</span>} />
        <Line label="Cassa" value={fmtMoney(s.cash)} hint={s.equity > 0 ? fmtPct((s.cash / s.equity) * 100, { sign: false }) : undefined} />
        <Line label="Posizioni" value={s.positions_count} />
      </div>
      {q.data.source === "derived" && <p className="mt-1 text-2xs leading-4 text-fg-subtle">{q.data.note}</p>}
    </div>
  );
}

function Office() {
  const down = useRuntimeDown();
  const agents = useOfficeAgents();
  const proposals = useProposals({ status: "pending" });
  const now = useNow(60_000);
  let working: ReactNode;
  if (agents.isPending && down) working = <Quiet>Runtime irraggiungibile.</Quiet>;
  else if (agents.isPending) working = <span className="block h-8 animate-pulse rounded-item bg-hover" />;
  else if (agents.isError) working = <Quiet>Agenti non disponibili: {agents.error.message}</Quiet>;
  else if (agents.data.source === "unavailable") working = <Quiet>{agents.data.note}</Quiet>;
  else {
    const list = agents.data.data.filter((a) => a.status === "working");
    const waiting = agents.data.data.filter((a) => a.status === "waiting").length;
    working =
      agents.data.source === "derived" ? (
        <Quiet>Lo stato degli agenti arriva con GET /v1/read/agents.</Quiet>
      ) : (
        <>
          {list.length === 0 ? (
            <Quiet>Nessun agente al lavoro{waiting ? `, ${waiting === 1 ? "1 agente" : `${waiting} agenti`} in attesa` : ""}.</Quiet>
          ) : (
            <ul className="space-y-0.5">
              {list.slice(0, 6).map((a) => (
                <li key={a.name}>
                  <Link to={`/ufficio/${encodeURIComponent(a.name)}`} className="-mx-1.5 flex items-center gap-2 rounded-item px-1.5 py-1 text-xs transition-colors hover:bg-hover">
                    <AuthorChip actor={a.name} size="xs" />
                    <span className="shrink-0 text-fg">{author(a.name).short}</span>
                    <span className="min-w-0 truncate text-fg-subtle">{a.current?.label ?? (a.current?.ticker ? `su ${a.current.ticker}` : "")}</span>
                  </Link>
                </li>
              ))}
              {list.length > 6 && <li className="pl-6 text-2xs text-fg-subtle">e altri {list.length - 6}</li>}
            </ul>
          )}
          {list.length > 0 && waiting > 0 && <p className="mt-1 text-2xs text-fg-subtle">{waiting === 1 ? "1 agente in attesa" : `${waiting} agenti in attesa`}</p>}
        </>
      );
  }
  let queue: ReactNode = null;
  if (proposals.data?.state === "ok") {
    const rows = [...proposals.data.data].sort((a, b) => (parseTs(a.submitted_ts) ?? 0) - (parseTs(b.submitted_ts) ?? 0));
    queue = (
      <div className="mt-3">
        <p className="mb-1 flex items-baseline text-xs text-fg-muted">
          In attesa del PM
          <span className={cn("num ml-auto", rows.length ? "font-semibold text-warn" : "text-fg")}>{rows.length}</span>
        </p>
        {rows.slice(0, 3).map((p) => (
          <Link key={p.id} to={`/ticker/${p.ticker}`} className="-mx-1.5 flex items-center gap-2 rounded-item px-1.5 py-1 text-xs transition-colors hover:bg-hover">
            <span className="font-medium text-fg">{p.ticker}</span>
            {p.direction && <span className="text-fg-subtle">{p.direction}</span>}
            <span className="num ml-auto text-2xs text-fg-subtle">da {fmtAge(parseTs(p.submitted_ts), now)}</span>
          </Link>
        ))}
      </div>
    );
  } else if (proposals.data?.state === "unavailable") {
    queue = <p className="mt-2 text-2xs leading-4 text-fg-subtle">Proposte in attesa: il Runtime non espone {proposals.data.endpoint}.</p>;
  }
  return (
    <>
      {working}
      {queue}
    </>
  );
}

function BridgeActions() {
  const down = useRuntimeDown();
  const q = useBridgeActions("pending");
  const { select, currentId } = useBridge();
  if (q.isPending && down) return <Quiet>Runtime irraggiungibile.</Quiet>;
  if (q.isPending) return <span className="block h-6 animate-pulse rounded-item bg-hover" />;
  if (q.isError) return <Quiet>Azioni non disponibili: {q.error.message}</Quiet>;
  if (q.data.state !== "ok") return <Quiet>Non disponibile: il Runtime non espone ancora {q.data.state === "unavailable" ? q.data.endpoint : "GET /v1/read/bridge_actions"}.</Quiet>;
  const rows = q.data.data;
  if (!rows.length) return <Quiet>Nessuna azione da confermare.</Quiet>;
  return (
    <ul className="space-y-0.5">
      {rows.map((a) => (
        <li key={a.id}>
          <button
            type="button"
            onClick={() => a.conversation_id !== null && select(a.conversation_id)}
            aria-current={a.conversation_id === currentId ? "true" : undefined}
            className="-mx-1.5 flex w-[calc(100%+12px)] items-center gap-2 rounded-item px-1.5 py-1 text-left text-xs transition-colors hover:bg-hover"
          >
            <span className="size-1.5 shrink-0 rounded-full bg-warn" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-fg">{actionTitle(a)}</span>
            <span className="shrink-0 text-2xs text-fg-subtle">Apri</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function System() {
  const { health, connection, target } = useRuntime();
  const { state } = useFreshness();
  const now = useNow(1000);
  const label = state === "live" ? "Live" : state === "stale" ? `Dati vecchi · ${fmtAge(connection.lastSyncAt, now)}` : state === "down" ? "Runtime irraggiungibile" : "Connessione…";
  return (
    <div>
      <div className={cn("flex items-center gap-2 rounded-item px-2 py-1.5 text-xs", health?.halted ? "bg-halt-ground text-fg" : "bg-[oklch(0_0_0/0.2)] text-fg-muted")}>
        {health?.halted ? <OctagonPause className="size-3.5 text-down" aria-hidden /> : <Play className="size-3.5 text-fg-subtle" aria-hidden />}
        <span className={health?.halted ? "font-medium" : ""}>{!health ? "Stato del trading sconosciuto" : health.halted ? "Halt attivo: nessun ordine al broker" : "Trading attivo"}</span>
      </div>
      <div className="mt-2">
        <Line label="Runtime" value={<span className="inline-flex items-center gap-1.5"><StatusDot state={state} />{label}</span>} />
        <Line label="Account" value={health?.account_label ?? target.label ?? target.id} />
        <Line label="Stream broker" value={!health ? "—" : !health.broker_configured ? "non configurato" : health.broker_stream_connected ? "connesso" : "disconnesso"} />
      </div>
    </div>
  );
}

/** The right tile: the state of the desk while Luca talks to the Bridge, from the reads the other pages use. */
export function LivePanel({ onHide, className, style }: { onHide?: () => void; className?: string; style?: CSSProperties }) {
  return (
    <aside aria-label="Stato vivo" data-region="live" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <header className="flex h-11 shrink-0 items-center gap-2 pl-4 pr-2">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Stato vivo</h2>
        {onHide && (
          <div className="ml-auto">
            <IconButton icon={PanelRightClose} label="Nascondi lo stato vivo" shortcut="Ctrl/⌘ Alt B" onClick={onHide} />
          </div>
        )}
      </header>
      <div className="min-h-0 flex-1 divide-y divide-line/60 overflow-y-auto pb-2">
        <Section title="Portafoglio" to="/portafoglio" toLabel="Apri">
          <Portfolio />
        </Section>
        <Section title="Azioni del Bridge da confermare">
          <BridgeActions />
        </Section>
        <Section title="Ufficio" to="/ufficio" toLabel="Apri">
          <Office />
        </Section>
        <Section title="Sistema">
          <System />
        </Section>
      </div>
    </aside>
  );
}
