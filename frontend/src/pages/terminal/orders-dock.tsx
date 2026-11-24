import { Check, ChevronRight, CircleAlert, PanelBottomClose, ShieldCheck, ShieldX, X } from "lucide-react";
import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PanelTab, PanelTabContent, PanelTabs, PanelTabsList } from "@/components/panel-tabs";
import { IconButton } from "@/components/tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fmtMoney, fmtPrice, fmtQty, fmtWhen, toNum } from "@/lib/format";
import { EXIT_LABEL, RISK_LIMITS, STATUS_LABEL, orderBucket, orderFigures } from "@/lib/orders";
import { CommandRefused, useCommand, useOrders, usePortfolio, useTrades } from "@/lib/runtime/hooks";
import type { Order, Trade } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { PANEL_SHORTCUT, useShell } from "@/shell/shell-state";

type Scope = "ticker" | "all";

/** Who signed the order: the PM drafts every order; Luca approves it, or the account approves on its own. */
export function Signature({ order }: { order: Order }) {
  const a = order.approval_status;
  return (
    <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <AuthorChip actor="portfolio_manager" size="xs" tooltip="Bozza del Portfolio Manager" />
      {a === "approved" && (
        <>
          <ChevronRight className="size-3 text-fg-faint" aria-hidden />
          <AuthorChip actor="cockpit" size="xs" tooltip="Approvato da Luca" />
        </>
      )}
      {a === "rejected" && (
        <>
          <ChevronRight className="size-3 text-fg-faint" aria-hidden />
          <AuthorChip actor="cockpit" size="xs" tooltip="Rifiutato da Luca" />
        </>
      )}
      {a === "auto" && <span className="text-2xs text-fg-subtle" title="Approvazione automatica dell'account">auto</span>}
    </span>
  );
}

function Th({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return (
    <TableHead scope="col" className={cn("sticky top-0 z-[1] h-7 whitespace-nowrap bg-ground px-2.5 text-2xs font-medium text-fg-subtle border-none", right ? "text-right" : "text-left", className)}>
      {children}
    </TableHead>
  );
}

function Td({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <TableCell className={cn("h-8 whitespace-nowrap px-2.5 text-xs border-none", right && "num text-right", className)}>{children}</TableCell>;
}

export function Side({ side }: { side: string }) {
  const buy = side.toLowerCase() === "buy";
  return <span className={cn("text-xs font-semibold", buy ? "text-up" : "text-down")}>{buy ? "Acquisto" : "Vendita"}</span>;
}

export function StatusBadge({ order }: { order: Order }) {
  const s = order.approval_status === "pending" && order.status === "pending" ? "pending" : order.status;
  const tone =
    s === "pending"
      ? "text-warn bg-warn-soft border-transparent"
      : s === "filled"
        ? "text-up bg-up-soft border-transparent"
        : s === "rejected"
          ? "text-down bg-down-soft border-transparent"
          : ["cancelled", "canceled", "expired"].includes(s)
            ? "text-fg-subtle bg-hover border-transparent"
            : "text-accent-c bg-accent-soft border-transparent";
  return (
    <Badge variant="outline" className={cn("h-5 px-1.5 text-2xs font-medium rounded-tag", tone)}>
      {s === "pending" ? "Da approvare" : (STATUS_LABEL[s] ?? s)}
    </Badge>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-24 items-center justify-center px-6 text-center text-xs leading-relaxed text-fg-subtle">{children}</div>;
}

function TableSkeleton() {
  return (
    <div className="space-y-2 p-3" aria-busy>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-6 animate-pulse rounded-item bg-hover" />
      ))}
    </div>
  );
}

type GateCheck = { label: string; detail: string; pass: boolean | null };

/** The checks the deterministic Risk Gate runs, previewed on the figures the cockpit can see. */
function gateChecks(o: Order, equity: number | null): GateCheck[] {
  const f = orderFigures(o);
  const checks: GateCheck[] = [
    { label: `R:R ≥ ${RISK_LIMITS.minRR}`, detail: f.rr === null ? "non calcolabile" : f.rr.toFixed(2).replace(".", ","), pass: f.rr === null ? null : f.rr >= RISK_LIMITS.minRR },
  ];
  if (equity) {
    const riskPct = f.risk !== null ? (f.risk / equity) * 100 : null;
    const posPct = f.notional !== null ? (f.notional / equity) * 100 : null;
    checks.push({
      label: `Rischio per trade ≤ ${RISK_LIMITS.tradeRiskPct}%`,
      detail: riskPct === null ? "—" : `${riskPct.toFixed(2).replace(".", ",")}% · ${fmtMoney(f.risk)}`,
      pass: riskPct === null ? null : riskPct <= RISK_LIMITS.tradeRiskPct + 1e-9,
    });
    checks.push({
      label: `Posizione ≤ ${RISK_LIMITS.positionPct}%`,
      detail: posPct === null ? "—" : `${posPct.toFixed(1).replace(".", ",")}% · ${fmtMoney(f.notional, { decimals: 0 })}`,
      pass: posPct === null ? null : posPct <= RISK_LIMITS.positionPct + 1e-9,
    });
  }
  return checks;
}

export function ApproveDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const portfolio = usePortfolio();
  const { halted } = useShell();
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const approve = useCommand("approve_order", { success: `Ordine #${order.id} approvato`, invalidate: [["orders"], ["inbox"], ["trades"]] });
  const f = orderFigures(order);
  const checks = gateChecks(order, portfolio.data?.equity ?? null);
  const failing = checks.some((c) => c.pass === false);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[460px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">
            Approvare <Side side={order.side} /> {order.ticker}?
          </DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">
            Ordine #{order.id} · bracket con stop e target. Il Risk Gate ricontrolla tutto al momento dell'invio e può ancora rifiutarlo.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-3 gap-px border-b border-line bg-line text-xs">
          {[
            ["Quantità", fmtQty(f.qty)],
            ["Entry limite", fmtPrice(f.entry)],
            ["Nozionale", fmtMoney(f.notional, { decimals: 0 })],
            ["Stop", fmtPrice(f.stop)],
            ["Target", fmtPrice(f.tp)],
            ["Rischio", fmtMoney(f.risk)],
          ].map(([k, v]) => (
            <div key={k} className="bg-raised px-4 py-2.5">
              <dt className="text-2xs text-fg-subtle">{k}</dt>
              <dd className={cn("num mt-0.5 text-sm text-fg", k === "Stop" && "text-down", k === "Target" && "text-up")}>{v}</dd>
            </div>
          ))}
        </dl>
        <div className="px-5 py-3.5">
          <h3 className="flex items-center gap-1.5 text-xs font-medium text-fg">
            <ShieldCheck className="size-3.5 text-fg-subtle" /> Anteprima del Risk Gate
          </h3>
          <ul className="mt-2 space-y-1.5">
            {checks.map((c) => (
              <li key={c.label} className="flex items-center gap-2 text-xs">
                {c.pass === null ? <CircleAlert className="size-3.5 text-fg-subtle" /> : c.pass ? <Check className="size-3.5 text-up" /> : <X className="size-3.5 text-down" />}
                <span className="text-fg-muted">{c.label}</span>
                <span className={cn("num ml-auto", c.pass === false ? "text-down" : "text-fg")}>{c.detail}</span>
              </li>
            ))}
            <li className="pt-0.5 text-2xs leading-relaxed text-fg-subtle">
              Settore ≤ {RISK_LIMITS.sectorPct}%, massimo {RISK_LIMITS.maxPositions} posizioni, riserva di cassa {RISK_LIMITS.cashReservePct}% ed embargo utili di{" "}
              {RISK_LIMITS.earningsEmbargoDays} giorni li verifica solo il Runtime.
            </li>
          </ul>
          {refusal && (
            <Alert variant="destructive" className="mt-3">
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
          {halted && <p className="mt-3 text-xs text-warn">Halt attivo: l'ordine non può partire finché non riprendi il trading.</p>}
        </div>
        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>
            {refusal ? "Chiudi" : "Annulla"}
          </Button>
          <Button
            disabled={approve.isPending || halted}
            onClick={() =>
              approve.mutate(
                { order_id: order.id, confirm: true },
                {
                  onSuccess: onClose,
                  onError: (err) => {
                    if (err instanceof CommandRefused) setRefusal(err.reasons);
                  },
                },
              )
            }
          >
            {failing ? "Approva comunque" : "Approva e invia"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RejectDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const reject = useCommand("reject_order", { success: `Ordine #${order.id} rifiutato`, invalidate: [["orders"], ["inbox"]] });
  const presets = ["Rischio troppo alto per ora", "Attendo la trimestrale", "Livello di ingresso non convincente"];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="border-line-strong bg-raised sm:max-w-[420px]">
        <DialogHeader className="text-left">
          <DialogTitle className="text-base">Rifiutare l'ordine su {order.ticker}?</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">La ragione arriva al Portfolio Manager, che la pesa nel prossimo ciclo.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-1.5">
          {presets.map((p) => (
            <button key={p} type="button" onClick={() => setReason(p)} className="h-6 rounded-item border border-line px-2 text-2xs text-fg-muted hover:bg-hover hover:text-fg">
              {p}
            </button>
          ))}
        </div>
        <label htmlFor="reject-reason" className="sr-only">
          Ragione del rifiuto
        </label>
        <Textarea
          id="reject-reason"
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Ragione (obbligatoria)"
          className="w-full resize-none rounded-control border-line-strong bg-ground px-2.5 py-2 text-sm text-fg outline-none placeholder:text-fg-subtle focus-visible:border-accent-c"
        />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Annulla
          </Button>
          <Button variant="destructive" disabled={!reason.trim() || reject.isPending} onClick={() => reject.mutate({ order_id: order.id, reason: reason.trim() }, { onSuccess: onClose })}>
            Rifiuta ordine
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OrdersTable({ orders, pending, onSelect, selected }: { orders: Order[]; pending?: boolean; onSelect: (t: string) => void; selected: string | null }) {
  const { writable, halted } = useShell();
  const [approving, setApproving] = useState<Order | null>(null);
  const [rejecting, setRejecting] = useState<Order | null>(null);
  return (
    <>
      <Table className="tile-table w-full border-separate border-spacing-0 px-1.5" containerClassName="overflow-x-auto">
        <TableHeader>
          <TableRow className="border-none hover:bg-transparent">
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
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((o) => {
            const f = orderFigures(o);
            const lowRR = f.rr !== null && f.rr < RISK_LIMITS.minRR;
            return (
              <TableRow
                key={o.id}
                onClick={() => onSelect(o.ticker)}
                className={cn("cursor-pointer transition-colors duration-150 border-none", o.ticker === selected ? "bg-selected/60 hover:bg-selected" : "hover:bg-hover")}
              >
                <Td className="font-semibold text-fg">{o.ticker}</Td>
                <Td>
                  <Side side={o.side} />
                </Td>
                <Td right>{fmtQty(f.qty)}</Td>
                <Td right>{fmtPrice(f.entry)}</Td>
                <Td right className="text-down/90">{fmtPrice(f.stop)}</Td>
                <Td right className="text-up/90">{fmtPrice(f.tp)}</Td>
                <Td right className={lowRR ? "text-warn" : ""}>{f.rr === null ? "—" : f.rr.toFixed(2).replace(".", ",")}</Td>
                <Td right>{fmtMoney(f.risk)}</Td>
                <Td right>{fmtMoney(f.notional, { decimals: 0 })}</Td>
                <Td>
                  <StatusBadge order={o} />
                </Td>
                <Td>
                  <Signature order={o} />
                </Td>
                <Td right className="text-fg-muted">{fmtWhen(o.created_ts)}</Td>
                <Td right className="pr-3">
                  {pending ? (
                    <span className="inline-flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <Button size="sm" variant="ghost" className="h-6 px-2" disabled={!writable} onClick={() => setRejecting(o)}>
                        Rifiuta
                      </Button>
                      <Button data-action="approve" size="sm" className="h-6 px-2.5" disabled={!writable || halted} onClick={() => setApproving(o)} title={halted ? "Halt attivo" : undefined}>
                        Approva
                      </Button>
                    </span>
                  ) : (
                    <span className="text-fg-subtle">#{o.id}</span>
                  )}
                </Td>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {approving && <ApproveDialog order={approving} onClose={() => setApproving(null)} />}
      {rejecting && <RejectDialog order={rejecting} onClose={() => setRejecting(null)} />}
    </>
  );
}

function TradesTable({ trades, prices, onSelect, selected }: { trades: Trade[]; prices: Map<string, number>; onSelect: (t: string) => void; selected: string | null }) {
  return (
    <Table className="tile-table w-full border-separate border-spacing-0 px-1.5" containerClassName="overflow-x-auto">
      <TableHeader>
        <TableRow className="border-none hover:bg-transparent">
          <Th>Ticker</Th>
          <Th>Stato</Th>
          <Th right>Qtà</Th>
          <Th right>Entrata</Th>
          <Th right>Uscita / ultimo</Th>
          <Th right>P&amp;L</Th>
          <Th right>P&amp;L %</Th>
          <Th>Chiusura</Th>
          <Th right>Aperto</Th>
          <Th right className="pr-3">Chiuso</Th>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((t) => {
          const open = !t.closed_ts;
          const exit = open ? (prices.get(t.ticker) ?? null) : t.exit_price;
          const pnl = exit !== null ? (exit - t.entry_price) * t.qty : null;
          const pct = exit !== null ? ((exit - t.entry_price) / t.entry_price) * 100 : null;
          return (
            <TableRow
              key={t.id}
              onClick={() => onSelect(t.ticker)}
              className={cn("cursor-pointer transition-colors duration-150 border-none", t.ticker === selected ? "bg-selected/60 hover:bg-selected" : "hover:bg-hover")}
            >
              <Td className="font-semibold text-fg">{t.ticker}</Td>
              <Td>
                <span className={cn("inline-flex h-5 items-center rounded-tag px-1.5 text-2xs font-medium", open ? "bg-accent-soft text-accent-c" : "bg-hover text-fg-subtle")}>{open ? "Aperto" : "Chiuso"}</span>
              </Td>
              <Td right>{fmtQty(t.qty)}</Td>
              <Td right>{fmtPrice(t.entry_price)}</Td>
              <Td right className={open ? "text-fg-muted" : ""}>{fmtPrice(exit)}</Td>
              <Td right className={pnl === null ? "" : pnl >= 0 ? "text-up" : "text-down"}>{fmtMoney(pnl, { sign: true })}</Td>
              <Td right className={pct === null ? "" : pct >= 0 ? "text-up" : "text-down"}>{pct === null ? "—" : `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(2).replace(".", ",")}%`}</Td>
              <Td className="text-fg-muted">{t.exit_reason ? (EXIT_LABEL[t.exit_reason] ?? t.exit_reason) : open ? "—" : ""}</Td>
              <Td right className="text-fg-muted">{fmtWhen(t.opened_ts)}</Td>
              <Td right className="pr-3 text-fg-muted">{t.closed_ts ? fmtWhen(t.closed_ts) : "—"}</Td>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function OrdersDock({
  selected,
  onSelect,
  onHide,
  className,
  style,
}: {
  selected: string | null;
  onSelect: (t: string) => void;
  onHide?: () => void;
  className?: string;
  style?: CSSProperties;
}) {
  const orders = useOrders();
  const trades = useTrades();
  const portfolio = usePortfolio();
  const [scope, setScope] = useState<Scope>("all");
  const all = orders.data ?? [];
  const inScope = (t: string) => scope === "all" || t === selected;
  const groups = useMemo(() => {
    const g = { pending: [] as Order[], open: [] as Order[], done: [] as Order[] };
    for (const o of all) if (inScope(o.ticker)) g[orderBucket(o)].push(o);
    return g;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, scope, selected]);
  const tradeRows = (trades.data ?? []).filter((t) => inScope(t.ticker));
  const prices = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of portfolio.data?.positions ?? []) {
      const sym = (p.symbol ?? p.ticker ?? "").toUpperCase();
      const px = toNum(p.current_price);
      if (sym && px !== null) m.set(sym, px);
    }
    return m;
  }, [portfolio.data]);
  const pendingAll = all.filter((o) => orderBucket(o) === "pending").length;
  const [tab, setTab] = useState<string | null>(null);
  const activeTab = tab ?? (pendingAll ? "pending" : "open");
  const tickerLabel = selected ?? "ticker";

  const body = (rows: Order[], empty: ReactNode, pending = false) =>
    orders.isPending ? (
      <TableSkeleton />
    ) : orders.isError ? (
      <Empty>
        <span className="text-down">Ordini non disponibili: {orders.error.message}</span>
      </Empty>
    ) : rows.length === 0 ? (
      <Empty>{empty}</Empty>
    ) : (
      <OrdersTable orders={rows} pending={pending} onSelect={onSelect} selected={selected} />
    );

  return (
    <section data-region="dock" aria-label="Ordini e trade" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <PanelTabs value={activeTab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <PanelTabsList
          end={
            <>
            <div role="radiogroup" aria-label="Ambito" className="seg">
              {(["all", "ticker"] as const).map((s) => (
                <button
                  key={s}
                  role="radio"
                  aria-checked={scope === s}
                  onClick={() => setScope(s)}
                  disabled={s === "ticker" && !selected}
                  className="seg-item"
                >
                  {s === "all" ? "Tutti" : tickerLabel}
                </button>
              ))}
            </div>
            {onHide && <IconButton icon={PanelBottomClose} label="Nascondi ordini" shortcut={PANEL_SHORTCUT.bottom} onClick={onHide} />}
            </>
          }
        >
          <PanelTab value="open" count={groups.open.length}>
            Aperti
          </PanelTab>
          <PanelTab value="pending" count={groups.pending.length} tone="warn">
            Pendenti
          </PanelTab>
          <PanelTab value="done" count={groups.done.length}>
            Eseguiti
          </PanelTab>
          <PanelTab value="trades" count={tradeRows.filter((t) => !t.closed_ts).length}>
            Trade
          </PanelTab>
        </PanelTabsList>
        <PanelTabContent value="open" className="overflow-auto">
          {body(groups.open, "Nessun ordine aperto presso il broker.")}
        </PanelTabContent>
        <PanelTabContent value="pending" className="overflow-auto">
          {body(
            groups.pending,
            <>Nessun ordine da approvare. Gli ordini attendono qui solo negli account in modalità manuale.</>,
            true,
          )}
        </PanelTabContent>
        <PanelTabContent value="done" className="overflow-auto">
          {body(groups.done, "Nessun ordine concluso.")}
        </PanelTabContent>
        <PanelTabContent value="trades" className="overflow-auto">
          {trades.isPending ? (
            <TableSkeleton />
          ) : trades.isError ? (
            <Empty>
              <span className="text-down">Trade non disponibili: {trades.error.message}</span>
            </Empty>
          ) : tradeRows.length === 0 ? (
            <Empty>Nessun trade{scope === "ticker" ? ` su ${tickerLabel}` : ""}.</Empty>
          ) : (
            <TradesTable trades={tradeRows} prices={prices} onSelect={onSelect} selected={selected} />
          )}
        </PanelTabContent>
      </PanelTabs>
    </section>
  );
}
