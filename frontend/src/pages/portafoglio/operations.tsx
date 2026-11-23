import { ShieldCheck } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { usePortfolioTrades } from "@/features/portfolio/hooks";
import type { PortfolioTrade, RiskLimitsRead } from "@/features/portfolio/types";
import { fmtDateTime, fmtPrice, fmtQty, fmtWhen } from "@/lib/format";
import { EXIT_LABEL, orderBucket, orderFigures } from "@/lib/orders";
import { useOrders } from "@/lib/runtime/hooks";
import type { Order } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { ApproveDialog, RejectDialog, Side, Signature, StatusBadge } from "@/pages/terminal/orders-dock";
import { onRadioKeys } from "@/pages/ufficio/parts";
import { useShell } from "@/shell/shell-state";
import { Bones, fmtDuration, fmtFrac, fmtLimit, fmtMoney, fmtSignedRatio, tone } from "./parts";

function Section({ title, meta, end, children }: { title: string; meta?: ReactNode; end?: ReactNode; children: ReactNode }) {
  return (
    <section className="pt-1">
      <header className="flex h-9 items-center gap-2 px-4">
        <h3 className="text-xs font-semibold text-fg">{title}</h3>
        {meta !== undefined && <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-muted">{meta}</span>}
        {end && <div className="ml-auto flex items-center gap-1">{end}</div>}
      </header>
      {children}
    </section>
  );
}

function Th({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <th scope="col" className={cn("h-7 whitespace-nowrap px-2.5 text-2xs font-medium text-fg-subtle", right ? "text-right" : "text-left", className)}>{children}</th>;
}

function Td({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <td className={cn("h-9 whitespace-nowrap px-2.5 text-xs transition-colors", right && "num text-right", className)}>{children}</td>;
}

/** The Risk Gate's limits in one quiet line, wherever orders can be approved. */
function GateLine({ limits }: { limits: RiskLimitsRead | null }) {
  if (!limits) return null;
  const L = limits.limits;
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 pb-2 text-2xs text-fg-subtle">
      <span className="inline-flex items-center gap-1 text-fg-muted">
        <ShieldCheck className="size-3" aria-hidden /> Risk Gate
      </span>
      <span>rischio ≤ {fmtLimit("max_risk_per_trade_fraction", L.max_risk_per_trade_fraction)}</span>
      <span>posizione ≤ {fmtLimit("max_position_fraction", L.max_position_fraction)}</span>
      <span>settore ≤ {fmtLimit("max_sector_fraction", L.max_sector_fraction)}</span>
      <span>R:R ≥ {fmtLimit("min_risk_reward_ratio", L.min_risk_reward_ratio)}</span>
      <span>riserva ≥ {fmtLimit("min_cash_reserve_fraction", L.min_cash_reserve_fraction)}</span>
    </p>
  );
}

function OrderRows({ orders, pending, mobile }: { orders: Order[]; pending: boolean; mobile: boolean }) {
  const { writable, halted } = useShell();
  const [approving, setApproving] = useState<Order | null>(null);
  const [rejecting, setRejecting] = useState<Order | null>(null);
  const actions = (o: Order) => (
    <span className="inline-flex gap-1.5">
      <Button size="sm" variant="ghost" className="h-6 px-2" disabled={!writable} onClick={() => setRejecting(o)}>
        Rifiuta
      </Button>
      <Button data-action="approve" size="sm" className="h-6 px-2.5" disabled={!writable || halted} onClick={() => setApproving(o)} title={halted ? "Halt attivo" : undefined}>
        Approva
      </Button>
    </span>
  );
  return (
    <>
      {mobile ? (
        <ul className="space-y-px px-1.5 pb-1">
          {orders.map((o) => {
            const f = orderFigures(o);
            return (
              <li key={o.id} className="rounded-item px-2.5 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-fg">{o.ticker}</span>
                  <Side side={o.side} />
                  <span className="ml-auto">
                    <StatusBadge order={o} />
                  </span>
                </div>
                <p className="num mt-1 text-2xs text-fg-subtle">
                  {fmtQty(f.qty)} @ {fmtPrice(f.entry)} · stop {fmtPrice(f.stop)} · target {fmtPrice(f.tp)} · R:R {f.rr === null ? "—" : f.rr.toFixed(2).replace(".", ",")}
                </p>
                {pending && <div className="mt-2 flex justify-end">{actions(o)}</div>}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="tile-table w-full min-w-[920px] border-separate border-spacing-0 px-1.5">
            <thead>
              <tr>
                <Th>Ticker</Th>
                <Th>Lato</Th>
                <Th right>Qtà</Th>
                <Th right>Entry</Th>
                <Th right>Stop</Th>
                <Th right>Target</Th>
                <Th right>R:R</Th>
                <Th right>Rischio</Th>
                <Th right>Nozionale</Th>
                <Th>Stato</Th>
                <Th>Firma</Th>
                <Th right>Creato</Th>
                <Th right className="pr-3">{pending ? "Azioni" : "ID"}</Th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const f = orderFigures(o);
                return (
                  <tr key={o.id} className="hover:[&>td]:bg-hover">
                    <Td className="font-semibold text-fg">{o.ticker}</Td>
                    <Td>
                      <Side side={o.side} />
                    </Td>
                    <Td right>{fmtQty(f.qty)}</Td>
                    <Td right>{fmtPrice(f.entry)}</Td>
                    <Td right className="text-down/90">{fmtPrice(f.stop)}</Td>
                    <Td right className="text-up/90">{fmtPrice(f.tp)}</Td>
                    <Td right>{f.rr === null ? "—" : f.rr.toFixed(2).replace(".", ",")}</Td>
                    <Td right>{fmtMoney(f.risk)}</Td>
                    <Td right>{fmtMoney(f.notional, { decimals: 0 })}</Td>
                    <Td>
                      <StatusBadge order={o} />
                    </Td>
                    <Td>
                      <Signature order={o} />
                    </Td>
                    <Td right className="text-fg-muted">{fmtWhen(o.created_ts)}</Td>
                    <Td right className="pr-3">{pending ? actions(o) : <span className="text-fg-subtle">#{o.id}</span>}</Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {approving && <ApproveDialog order={approving} onClose={() => setApproving(null)} />}
      {rejecting && <RejectDialog order={rejecting} onClose={() => setRejecting(null)} />}
    </>
  );
}

type Outcome = "all" | "win" | "loss";

function TradesHistory({ trades, mobile }: { trades: PortfolioTrade[]; mobile: boolean }) {
  const [outcome, setOutcome] = useState<Outcome>("all");
  const closed = trades.filter((t) => t.closed_ts);
  const rows = closed.filter((t) => outcome === "all" || (outcome === "win" ? (t.pnl ?? 0) > 0 : (t.pnl ?? 0) < 0));
  const sum = rows.reduce((a, t) => a + (t.pnl ?? 0), 0);
  const filter = (
    <div role="radiogroup" aria-label="Esito" className="seg" onKeyDown={onRadioKeys}>
      {(["all", "win", "loss"] as const).map((o) => (
        <button key={o} type="button" role="radio" aria-checked={outcome === o} tabIndex={outcome === o ? 0 : -1} onClick={() => setOutcome(o)} className="seg-item">
          {o === "all" ? "Tutti" : o === "win" ? "Vinti" : "Persi"}
        </button>
      ))}
    </div>
  );
  return (
    <Section
      title="Trade chiusi"
      meta={closed.length}
      end={
        <>
          <span className={cn("num mr-2 text-2xs", tone(sum))}>{fmtMoney(sum, { sign: true })}</span>
          {filter}
        </>
      }
    >
      {rows.length === 0 ? (
        <p className="px-4 pb-4 text-xs text-fg-subtle">{closed.length ? "Nessun trade con questo esito." : "Nessun trade chiuso finora."}</p>
      ) : mobile ? (
        <ul className="space-y-px px-1.5 pb-2">
          {rows.map((t) => (
            <li key={t.id} className="flex items-center gap-3 rounded-item px-2.5 py-2">
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-fg">{t.ticker}</span>
                  <span className="text-2xs text-fg-subtle">{t.exit_reason ? (EXIT_LABEL[t.exit_reason] ?? t.exit_reason) : ""}</span>
                </span>
                <span className="num block text-2xs text-fg-subtle">
                  {fmtPrice(t.entry_price)} → {fmtPrice(t.exit_price)} · {fmtDuration(t.duration_s)}
                </span>
              </span>
              <span className="text-right">
                <span className={cn("num block text-xs", tone(t.pnl))}>{fmtMoney(t.pnl, { sign: true, decimals: 0 })}</span>
                <span className={cn("num block text-2xs", tone(t.r_multiple))}>{t.r_multiple === null ? "—" : `${fmtSignedRatio(t.r_multiple)} R`}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="tile-table w-full min-w-[920px] border-separate border-spacing-0 px-1.5 pb-2">
            <thead>
              <tr>
                <Th>Ticker</Th>
                <Th right>Qtà</Th>
                <Th right>Entrata</Th>
                <Th right>Uscita</Th>
                <Th>Motivo</Th>
                <Th right>PnL</Th>
                <Th right>PnL %</Th>
                <Th right>R</Th>
                <Th right>Durata</Th>
                <Th>Proposto da</Th>
                <Th right className="pr-3">Chiuso</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className="hover:[&>td]:bg-hover">
                  <Td className="font-semibold text-fg">{t.ticker}</Td>
                  <Td right>{fmtQty(t.qty)}</Td>
                  <Td right className="text-fg-muted">{fmtPrice(t.entry_price)}</Td>
                  <Td right>{fmtPrice(t.exit_price)}</Td>
                  <Td className="text-fg-muted">{t.exit_reason ? (EXIT_LABEL[t.exit_reason] ?? t.exit_reason) : "—"}</Td>
                  <Td right className={tone(t.pnl)}>{fmtMoney(t.pnl, { sign: true })}</Td>
                  <Td right className={tone(t.pnl)}>{t.exit_price !== null && t.entry_price ? fmtFrac(t.exit_price / t.entry_price - 1, { sign: true }) : "—"}</Td>
                  <Td right className={tone(t.r_multiple)}>{t.r_multiple === null ? "—" : fmtSignedRatio(t.r_multiple)}</Td>
                  <Td right className="text-fg-muted">{fmtDuration(t.duration_s)}</Td>
                  <Td>{t.proposed_by ? <AuthorChip actor={t.proposed_by} size="xs" label /> : <span className="text-fg-subtle">—</span>}</Td>
                  <Td right className="pr-3 text-fg-muted" >
                    <span title={fmtDateTime(t.closed_ts)}>{fmtWhen(t.closed_ts)}</span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

/** Orders waiting on Luca first (as in the Terminale), then orders live at the broker, then closed trades. */
export function OperationsPanel({ limits, mobile }: { limits: RiskLimitsRead | null; mobile: boolean }) {
  const orders = useOrders();
  const trades = usePortfolioTrades();
  const groups = useMemo(() => {
    const g = { pending: [] as Order[], open: [] as Order[] };
    for (const o of orders.data ?? []) {
      const b = orderBucket(o);
      if (b === "pending" || b === "open") g[b].push(o);
    }
    return g;
  }, [orders.data]);

  return (
    <div className="pb-2">
      <Section title="Da approvare" meta={orders.isPending ? undefined : groups.pending.length}>
        <GateLine limits={limits} />
        {orders.isPending ? (
          <Bones rows={2} className="px-4 pb-3" />
        ) : orders.isError ? (
          <p className="px-4 pb-3 text-xs text-down">Ordini non disponibili: {orders.error.message}</p>
        ) : groups.pending.length === 0 ? (
          <p className="px-4 pb-3 text-xs text-fg-subtle">Nessun ordine da approvare. Gli ordini attendono qui solo negli account in modalità manuale.</p>
        ) : (
          <OrderRows orders={groups.pending} pending mobile={mobile} />
        )}
      </Section>
      {groups.open.length > 0 && (
        <Section title="Ordini aperti" meta={groups.open.length}>
          <OrderRows orders={groups.open} pending={false} mobile={mobile} />
        </Section>
      )}
      {trades.isPending ? (
        <Bones rows={4} className="px-4 py-3" />
      ) : trades.isError ? (
        <p className="px-4 py-3 text-xs text-down">Trade non disponibili: {trades.error.message}</p>
      ) : (
        <>
          <TradesHistory trades={trades.data.trades} mobile={mobile} />
          {!trades.data.enriched && (
            <p className="px-4 pb-2 text-2xs text-fg-subtle">R multiplo calcolato dallo stop d'ingresso; agente proponente in arrivo quando /v1/read/trades aggiunge proposed_by.</p>
          )}
        </>
      )}
    </div>
  );
}
