import { ChevronRight, Crosshair, MessageSquarePlus, PanelRightClose, RefreshCw, Trash2 } from "lucide-react";
import { useState, type CSSProperties, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { PanelTab, PanelTabContent, PanelTabs, PanelTabsList } from "@/components/panel-tabs";
import { IconButton } from "@/components/tile";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AGENTS, AGENT_IDS, author } from "@/lib/authors";
import { fmtPrice, fmtWhen } from "@/lib/format";
import { useCommand, useCycles, useTickerState, useWatchlist } from "@/lib/runtime/hooks";
import type { Suggestion } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { PANEL_SHORTCUT } from "@/shell/shell-state";
import { useShell } from "@/shell/shell-state";
import { KIND_LABEL, type ChartDrawing } from "@/features/chart/chart-state";

const DIRECTION: Record<string, { label: string; tone: string }> = {
  buy: { label: "Compra", tone: "text-up" },
  sell: { label: "Vendi", tone: "text-down" },
  hold: { label: "Mantieni", tone: "text-fg-muted" },
  defer: { label: "Rinvia", tone: "text-warn" },
};

const COEFF_LABEL: Record<string, string> = {
  k_entry: "k entry",
  risk_fraction: "Rischio",
  k_stop: "k stop",
  k_tp: "k target",
  k_trail_act: "k trail att.",
  k_trail: "k trail",
  atr: "ATR",
};

function Section({ title, children, end }: { title: string; children: ReactNode; end?: ReactNode }) {
  return (
    <section className="mx-1.5 rounded-control px-2.5 py-3 [&+&]:border-t [&+&]:border-line/70">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-2xs font-medium text-fg-subtle">{title}</h3>
        {end && <div className="ml-auto">{end}</div>}
      </div>
      {children}
    </section>
  );
}

function Conviction({ s }: { s: Suggestion }) {
  const d = DIRECTION[s.direction] ?? { label: s.direction, tone: "text-fg-muted" };
  return (
    <span className="flex items-center gap-2">
      <span className={cn("w-14 text-xs font-medium", d.tone)}>{d.label}</span>
      <span className="num w-7 text-right text-xs text-fg-muted">{s.conviction.toFixed(2).replace(".", ",")}</span>
    </span>
  );
}

function AgentsTab({ ticker }: { ticker: string }) {
  const state = useTickerState(ticker);
  const cycles = useCycles(ticker);
  const watched = (useWatchlist().data ?? []).some((w) => w.ticker === ticker);
  const { messageAgent, writable } = useShell();
  const [open, setOpen] = useState<string | null>(null);
  const enqueue = useCommand("enqueue_task", { invalidate: [["cycles"]] });

  if (state.isPending) {
    return (
      <div className="space-y-3 p-3" aria-busy>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-9 animate-pulse rounded-item bg-hover" />
        ))}
      </div>
    );
  }
  if (state.isError) return <p className="p-3 text-xs text-down">Stato del ticker non disponibile: {state.error.message}</p>;

  const s = state.data ?? {};
  const agents = Array.from(new Set([...Object.keys(s.suggestions ?? {}), ...Object.keys(s.analyses ?? {})]));
  const openCycle = (cycles.data ?? []).find((c) => c.status === "open");
  const decision = s.decision;

  const requestAnalysis = (agent: string) =>
    enqueue.mutate(
      { agent, ticker, reason: `Richiesta di Luca dal Terminale: rivedere ${ticker}` },
      { onSuccess: () => undefined },
    );

  return (
    <div>
      <Section
        title="Decisione del PM"
        end={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 px-1.5 text-2xs" disabled={!writable}>
                <RefreshCw className="size-3" /> Chiedi analisi
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 border-line-strong bg-raised">
              <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">Accoda un task su {ticker} (enqueue_task)</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {AGENT_IDS.map((id) => (
                <DropdownMenuItem key={id} onSelect={() => requestAnalysis(id)} className="gap-2 text-xs">
                  <AuthorChip actor={id} size="xs" tooltip={AGENTS[id].name} /> {AGENTS[id].name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        }
      >
        {decision ? (
          <div className="text-xs">
            <div className="flex items-center gap-2">
              <AuthorChip actor="portfolio_manager" size="xs" />
              <span className={cn("font-semibold", (DIRECTION[decision.action] ?? DIRECTION.hold).tone)}>{(DIRECTION[decision.action] ?? { label: decision.action }).label}</span>
              <span className="num ml-auto text-2xs text-fg-subtle">{fmtWhen(decision.decided_ts)}</span>
            </div>
            <p className="mt-1.5 text-pretty leading-relaxed text-fg-muted">{decision.reason}</p>
          </div>
        ) : (
          <p className="text-xs text-fg-subtle">Nessuna decisione in corso su {ticker}.</p>
        )}
        {openCycle && (
          <p className="mt-2.5 flex items-center gap-1.5 text-2xs text-accent-c">
            <span className="size-1.5 rounded-full bg-accent-c" style={{ animation: "status-pulse 1.6s ease-in-out infinite" }} aria-hidden />
            Ciclo #{openCycle.id} in corso da {fmtWhen(openCycle.opened_ts)}
          </p>
        )}
      </Section>

      <Section title={`Agenti su ${ticker}`}>
        {agents.length === 0 ? (
          <p className="text-xs leading-relaxed text-fg-subtle">Nessun agente ha ancora scritto su {ticker}.{" "}
            {watched ? "Il prossimo ciclo lo prenderà in carico, oppure chiedi un'analisi ora." : "Chiedi un'analisi o aggiungilo alla watchlist perché i cicli lo seguano."}
          </p>
        ) : (
          <ul className="-mx-1.5 space-y-0.5">
            {agents.map((id) => {
              const sug = s.suggestions?.[id];
              const text = s.analyses?.[id];
              const expanded = open === id;
              return (
                <li key={id} className="rounded-item">
                  <div className="group flex items-center gap-2 rounded-item px-1.5 py-1 hover:bg-hover">
                    <button
                      type="button"
                      onClick={() => setOpen(expanded ? null : id)}
                      aria-expanded={expanded}
                      disabled={!text}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default"
                    >
                      <ChevronRight className={cn("size-3 shrink-0 text-fg-faint transition-transform duration-150", expanded && "rotate-90", !text && "opacity-0")} />
                      <AuthorChip actor={id} size="xs" label />
                    </button>
                    {sug ? <Conviction s={sug} /> : <span className="text-2xs text-fg-subtle">solo analisi</span>}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={() => messageAgent(id, `[${ticker}]`)}
                          className="grid size-6 place-items-center rounded-item text-fg-subtle opacity-0 hover:bg-raised hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
                          aria-label={`Scrivi a ${AGENTS[id]?.name ?? id}`}
                        >
                          <MessageSquarePlus className="size-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>Scrivi a {AGENTS[id]?.short ?? id}</TooltipContent>
                    </Tooltip>
                  </div>
                  {expanded && text && <p className="mb-1.5 ml-[30px] mr-1.5 mt-0.5 text-xs leading-relaxed text-fg-muted">{text}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {s.coefficients && Object.keys(s.coefficients).length > 0 && (
        <Section title="Coefficienti dell'ordine">
          <dl className="grid grid-cols-3 gap-x-3 gap-y-2">
            {Object.entries(s.coefficients).map(([k, v]) => (
              <div key={k}>
                <dt className="text-2xs text-fg-subtle">{COEFF_LABEL[k] ?? k}</dt>
                <dd className="num text-xs text-fg">{k === "risk_fraction" ? `${(v * 100).toFixed(2).replace(".", ",")}%` : String(v).replace(".", ",")}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-pretty text-xs leading-relaxed text-fg-subtle">Entry, stop e target si calcolano da questi coefficienti e dall'ATR: il Tecnico fissa stop e target, il Rischio entry e frazione di rischio.</p>
        </Section>
      )}

      <Section title="Ultimi cicli">
        {cycles.isPending ? (
          <div className="h-8 animate-pulse rounded-item bg-hover" />
        ) : (cycles.data ?? []).length === 0 ? (
          <p className="text-xs text-fg-subtle">Nessun ciclo su {ticker}.</p>
        ) : (
          <ul className="space-y-1">
            {(cycles.data ?? []).slice(0, 5).map((c) => (
              <li key={c.id} className="flex items-center gap-2 text-xs">
                <span className="num w-9 text-fg-subtle">#{c.id}</span>
                <span className={cn(c.status === "open" ? "text-accent-c" : "text-fg-muted")}>{c.status === "open" ? "In corso" : c.outcome ? `Esito: ${(DIRECTION[c.outcome] ?? { label: c.outcome }).label}` : "Chiuso"}</span>
                <span className="num ml-auto text-2xs text-fg-subtle">{fmtWhen(c.opened_ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function DrawingsTab({
  drawings,
  onFocus,
  onStrike,
}: {
  drawings: ChartDrawing[];
  onFocus: (id: string) => void;
  onStrike: (id: string) => void;
}) {
  const { writable } = useShell();
  const active = drawings.filter((d) => d.status === "active");
  const struck = drawings.filter((d) => d.status === "struck");
  if (!drawings.length) {
    return (
      <p className="p-3 text-xs leading-relaxed text-fg-subtle">
        Nessun disegno su questo ticker. Usa gli strumenti sopra il grafico: le tue linee le leggono anche gli agenti, e qui compaiono i livelli che tracciano loro.
      </p>
    );
  }
  const row = (d: ChartDrawing) => {
    const a = author(d.author);
    const mine = a.kind === "human";
    return (
      <li key={d.id} className={cn("group flex items-start gap-2 rounded-item px-1.5 py-1.5 hover:bg-hover", d.status === "struck" && "opacity-55")}>
        <AuthorChip author={a} size="xs" className="mt-0.5" />
        <button type="button" onClick={() => d.status === "active" && onFocus(d.id)} className="min-w-0 flex-1 text-left" disabled={d.status !== "active"}>
          <span className={cn("block truncate text-xs text-fg", d.status === "struck" && "line-through")}>{d.text || KIND_LABEL[d.kind] || d.kind}</span>
          <span className="num block truncate text-2xs text-fg-subtle">
            {KIND_LABEL[d.kind] ?? d.kind} · {d.points.map((p) => fmtPrice(p.price)).join(" → ")}
          </span>
          {d.status === "struck" && <span className="block text-2xs text-fg-subtle">Rimosso da {author(d.struckBy).name}</span>}
        </button>
        <span className="num shrink-0 pt-0.5 text-2xs text-fg-subtle">{fmtWhen(d.updatedAt)}</span>
        {d.status === "active" && (
          <span className="flex shrink-0 gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
            <button type="button" onClick={() => onFocus(d.id)} className="grid size-6 place-items-center rounded-item text-fg-subtle hover:bg-raised hover:text-fg" aria-label="Mostra sul grafico">
              <Crosshair className="size-3.5" />
            </button>
            {mine && (
              <button type="button" disabled={!writable} onClick={() => onStrike(d.id)} className="grid size-6 place-items-center rounded-item text-fg-subtle hover:bg-raised hover:text-down disabled:hidden" aria-label="Rimuovi il disegno">
                <Trash2 className="size-3.5" />
              </button>
            )}
          </span>
        )}
      </li>
    );
  };
  return (
    <div className="px-1.5 py-2">
      <ul>{active.map(row)}</ul>
      {struck.length > 0 && (
        <>
          <h3 className="mb-1 mt-3 px-1.5 text-2xs font-medium text-fg-subtle">Rimossi</h3>
          <ul>{struck.map(row)}</ul>
        </>
      )}
      <p className="mt-3 px-1.5 text-2xs leading-relaxed text-fg-subtle">I disegni degli agenti sono bloccati: puoi nasconderli dal grafico, non spostarli.</p>
    </div>
  );
}

export function ActivityPanel({
  ticker,
  drawings,
  onFocusDrawing,
  onStrike,
  onCollapse,
  className,
  style,
}: {
  ticker: string | null;
  drawings: ChartDrawing[];
  onFocusDrawing: (id: string) => void;
  onStrike: (id: string) => void;
  onCollapse?: () => void;
  className?: string;
  style?: CSSProperties;
}) {
  const [tab, setTab] = useState("agents");
  return (
    <aside data-region="activity" aria-label="Attività sullo strumento" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <PanelTabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <PanelTabsList
          end={
            onCollapse && (
              <IconButton icon={PanelRightClose} label="Nascondi attività" shortcut={PANEL_SHORTCUT.right} onClick={onCollapse} />
            )
          }
        >
          <PanelTab value="agents">Agenti</PanelTab>
          <PanelTab value="drawings" count={drawings.filter((d) => d.status === "active").length}>
            Disegni
          </PanelTab>
        </PanelTabsList>
        <PanelTabContent value="agents" className="overflow-y-auto">
          {ticker ? <AgentsTab ticker={ticker} /> : <p className="p-3 text-xs text-fg-subtle">Seleziona un ticker.</p>}
        </PanelTabContent>
        <PanelTabContent value="drawings" className="overflow-y-auto">
          <DrawingsTab drawings={drawings} onFocus={onFocusDrawing} onStrike={onStrike} />
        </PanelTabContent>
      </PanelTabs>
    </aside>
  );
}
