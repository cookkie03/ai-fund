import { ArrowDown, ArrowUp, ChevronRight, SlidersHorizontal, SquareMinus } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { PortfolioPosition, RiskLimitsRead, Sourced } from "@/features/portfolio/types";
import { fmtPrice, fmtQty } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Bones, fmtFrac, fmtMoney, SourceNote, statusFor, StatusWord, tone } from "./parts";
import { AskLinks, CloseDialog, ExitDialog, RowActions, useCapitalBlock, type ActionKind } from "./position-actions";

type SortKey = "ticker" | "market_value" | "weight" | "unrealized_pnl" | "unrealized_pnl_fraction" | "open_risk" | "days_held";

const COLS: { key: SortKey | null; label: string; right?: boolean; hint?: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: null, label: "Settore" },
  { key: null, label: "Qtà", right: true },
  { key: null, label: "Medio", right: true, hint: "Prezzo medio di carico" },
  { key: null, label: "Ultimo", right: true },
  { key: "market_value", label: "Valore", right: true },
  { key: "weight", label: "Peso", right: true, hint: "Valore in % dell'equity, contro il peso massimo per posizione" },
  { key: "unrealized_pnl", label: "PnL", right: true },
  { key: "unrealized_pnl_fraction", label: "PnL %", right: true },
  { key: null, label: "Stop", right: true },
  { key: null, label: "Target", right: true },
  { key: "open_risk", label: "Rischio allo stop", right: true, hint: "Perdita se il prezzo tocca lo stop, in $ e in % dell'equity" },
  { key: "days_held", label: "Giorni", right: true },
  { key: null, label: "Proposto da" },
];

function Th({ col, sort, onSort }: { col: (typeof COLS)[number]; sort: { key: SortKey; dir: 1 | -1 }; onSort: (k: SortKey) => void }) {
  const active = col.key && sort.key === col.key;
  const Arrow = sort.dir === 1 ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
      title={col.hint}
      className={cn("sticky top-0 z-[1] h-8 whitespace-nowrap bg-ground px-2.5 text-2xs font-medium text-fg-subtle", col.right ? "text-right" : "text-left")}
    >
      {col.key ? (
        <button type="button" onClick={() => onSort(col.key!)} className={cn("inline-flex items-center gap-1 rounded-tag hover:text-fg", active && "text-fg")}>
          {col.label}
          {active && <Arrow className="size-3" aria-hidden />}
        </button>
      ) : (
        col.label
      )}
    </th>
  );
}

function Td({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <td className={cn("h-9 whitespace-nowrap px-2.5 text-xs transition-colors", right && "num text-right", className)}>{children}</td>;
}

function Agent({ actor }: { actor: string | null }) {
  if (!actor) return <span className="text-fg-subtle">—</span>;
  return <AuthorChip actor={actor} size="xs" label />;
}

function useSorted(rows: PortfolioPosition[]) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "weight", dir: -1 });
  const sorted = useMemo(() => {
    const v = (p: PortfolioPosition) => p[sort.key];
    return [...rows].sort((a, b) => {
      const x = v(a);
      const y = v(b);
      if (typeof x === "string" || typeof y === "string") return String(x).localeCompare(String(y)) * sort.dir;
      return ((x ?? -Infinity) - (y ?? -Infinity)) * sort.dir;
    });
  }, [rows, sort]);
  const onSort = (key: SortKey) => setSort((s) => ({ key, dir: s.key === key ? ((s.dir * -1) as 1 | -1) : key === "ticker" ? 1 : -1 }));
  return { sorted, sort, onSort };
}

function PositionsTable({ rows, limits, onAction }: { rows: PortfolioPosition[]; limits: RiskLimitsRead | null; onAction: (k: ActionKind, p: PortfolioPosition) => void }) {
  const { sorted, sort, onSort } = useSorted(rows);
  const maxW = limits?.limits.max_position_fraction ?? null;
  const maxR = limits?.limits.max_risk_per_trade_fraction ?? null;
  const total = rows.reduce(
    (a, p) => ({ value: a.value + (p.market_value ?? 0), pnl: a.pnl + (p.unrealized_pnl ?? 0), risk: a.risk + (p.open_risk ?? 0), w: a.w + (p.weight ?? 0), rf: a.rf + (p.open_risk_fraction ?? 0) }),
    { value: 0, pnl: 0, risk: 0, w: 0, rf: 0 },
  );
  return (
    <table className="tile-table w-full min-w-[1180px] border-separate border-spacing-0 px-1.5">
      <thead>
        <tr>
          {COLS.map((c) => (
            <Th key={c.label} col={c} sort={sort} onSort={onSort} />
          ))}
          <th scope="col" className="sticky top-0 z-[1] h-8 w-10 bg-ground pr-2">
            <span className="sr-only">Azioni</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((p) => {
          const wStatus = statusFor(p.weight, maxW);
          const rStatus = statusFor(p.open_risk_fraction, maxR);
          return (
            <tr key={p.ticker} className="group hover:[&>td]:bg-hover">
              <Td className="font-semibold text-fg">
                {p.ticker}
                {p.side === "short" && <Badge variant="destructive" className="ml-1.5 h-4 px-1 text-[10px] leading-none uppercase">short</Badge>}
              </Td>
              <Td className="text-fg-muted">{p.sector ?? <span className="text-fg-subtle">—</span>}</Td>
              <Td right>{fmtQty(p.qty)}</Td>
              <Td right className="text-fg-muted">{fmtPrice(p.avg_entry_price)}</Td>
              <Td right>{fmtPrice(p.current_price)}</Td>
              <Td right>{fmtMoney(p.market_value, { decimals: 0 })}</Td>
              <Td right>
                <span className={cn(wStatus === "breach" ? "text-down" : wStatus === "near" ? "text-warn" : "")} title={maxW !== null ? `Peso massimo ${fmtFrac(maxW, { decimals: 0 })}` : undefined}>
                  {fmtFrac(p.weight, { decimals: 1 })}
                </span>
              </Td>
              <Td right className={tone(p.unrealized_pnl)}>{fmtMoney(p.unrealized_pnl, { sign: true })}</Td>
              <Td right className={tone(p.unrealized_pnl_fraction)}>{fmtFrac(p.unrealized_pnl_fraction, { sign: true })}</Td>
              <Td right className="text-down/90">{fmtPrice(p.stop_price)}</Td>
              <Td right className="text-up/90">{fmtPrice(p.target_price)}</Td>
              <Td right>
                {p.open_risk === null ? (
                  <span className="text-fg-subtle" title="Stop non noto">—</span>
                ) : (
                  <span className="inline-flex items-baseline gap-1.5">
                    {fmtMoney(p.open_risk, { decimals: 0 })}
                    <span className={cn("text-2xs", rStatus === "breach" ? "text-down" : rStatus === "near" ? "text-warn" : "text-fg-subtle")}>{fmtFrac(p.open_risk_fraction)}</span>
                  </span>
                )}
              </Td>
              <Td right className="text-fg-muted">{p.days_held ?? "—"}</Td>
              <Td>
                <Agent actor={p.proposed_by} />
              </Td>
              <Td className="pr-2 text-right">
                <RowActions p={p} onAction={onAction} />
              </Td>
            </tr>
          );
        })}
      </tbody>
      <tfoot>
        <tr className="text-fg">
          <td className="h-9 px-2.5 text-xs font-medium">Totale</td>
          <td colSpan={4} />
          <td className="num h-9 px-2.5 text-right text-xs font-medium">{fmtMoney(total.value, { decimals: 0 })}</td>
          <td className="num h-9 px-2.5 text-right text-xs text-fg-muted">{fmtFrac(total.w, { decimals: 1 })}</td>
          <td className={cn("num h-9 px-2.5 text-right text-xs font-medium", tone(total.pnl))}>{fmtMoney(total.pnl, { sign: true })}</td>
          <td colSpan={3} />
          <td className="num h-9 px-2.5 text-right text-xs">
            {fmtMoney(total.risk, { decimals: 0 })} <span className="text-2xs text-fg-subtle">{fmtFrac(total.rf)}</span>
          </td>
          <td colSpan={3} />
        </tr>
      </tfoot>
    </table>
  );
}

function MobileList({ rows, onOpen }: { rows: PortfolioPosition[]; onOpen: (p: PortfolioPosition) => void }) {
  const sorted = [...rows].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0));
  return (
    <ul className="space-y-px p-1.5">
      {sorted.map((p) => (
        <li key={p.ticker}>
          <button type="button" onClick={() => onOpen(p)} className="flex min-h-[60px] w-full items-center gap-3 rounded-item px-2.5 py-2 text-left transition-colors active:bg-hover">
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-2">
                <span className="text-[13px] font-semibold text-fg">{p.ticker}</span>
                <span className="num text-2xs text-fg-subtle">{fmtFrac(p.weight, { decimals: 1 })}</span>
              </span>
              <span className="num mt-0.5 block truncate text-2xs text-fg-subtle">
                {fmtQty(p.qty)} × {fmtPrice(p.current_price)}
                {p.sector ? ` · ${p.sector}` : ""}
              </span>
            </span>
            <span className="shrink-0 text-right">
              <span className="num block text-xs text-fg">{fmtMoney(p.market_value, { decimals: 0 })}</span>
              <span className={cn("num block text-2xs", tone(p.unrealized_pnl))}>
                {fmtMoney(p.unrealized_pnl, { sign: true, decimals: 0 })} · {fmtFrac(p.unrealized_pnl_fraction, { sign: true, decimals: 1 })}
              </span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  );
}

function DetailSheet({ p, limits, onClose, onAction }: { p: PortfolioPosition; limits: RiskLimitsRead | null; onClose: () => void; onAction: (k: ActionKind, p: PortfolioPosition) => void }) {
  const block = useCapitalBlock();
  const rStatus = statusFor(p.open_risk_fraction, limits?.limits.max_risk_per_trade_fraction ?? null);
  const items: [string, ReactNode, string?][] = [
    ["Quantità", fmtQty(p.qty)],
    ["Prezzo medio", fmtPrice(p.avg_entry_price)],
    ["Ultimo", fmtPrice(p.current_price)],
    ["Valore", fmtMoney(p.market_value, { decimals: 0 })],
    ["PnL", fmtMoney(p.unrealized_pnl, { sign: true }), tone(p.unrealized_pnl)],
    ["PnL %", fmtFrac(p.unrealized_pnl_fraction, { sign: true }), tone(p.unrealized_pnl_fraction)],
    ["Stop", fmtPrice(p.stop_price), "text-down"],
    ["Target", fmtPrice(p.target_price), "text-up"],
    ["Rischio allo stop", p.open_risk === null ? "—" : `${fmtMoney(p.open_risk, { decimals: 0 })} · ${fmtFrac(p.open_risk_fraction)}`],
    ["Peso", fmtFrac(p.weight, { decimals: 1 })],
    ["Settore", p.sector ?? "—"],
    ["Giorni in posizione", p.days_held ?? "—"],
  ];
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="bottom" className="max-h-[88vh] gap-0 overflow-y-auto rounded-t-tile border-line-strong bg-raised p-0">
        <SheetHeader className="px-4 pb-2 pt-4 text-left">
          <SheetTitle className="flex items-center gap-2 text-base">
            {p.ticker}
            {rStatus !== "ok" && <StatusWord status={rStatus} />}
          </SheetTitle>
          <SheetDescription className="flex items-center gap-1.5 text-xs text-fg-muted">
            Proposto da <Agent actor={p.proposed_by} />
          </SheetDescription>
        </SheetHeader>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3">
          {items.map(([k, v, cls]) => (
            <div key={k}>
              <dt className="text-2xs text-fg-subtle">{k}</dt>
              <dd className={cn("num mt-0.5 text-[13px] text-fg", cls)}>{v}</dd>
            </div>
          ))}
        </dl>
        <div className="space-y-2 border-t border-line px-4 py-3 pb-[max(env(safe-area-inset-bottom),12px)]">
          {block && <p className="text-xs text-warn">{block}: azioni di capitale sospese.</p>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" disabled={!!block} onClick={() => onAction("exit", p)}>
              <SlidersHorizontal /> Stop e target
            </Button>
            <Button variant="outline" disabled={!!block} onClick={() => onAction("close", p)}>
              <SquareMinus /> Chiudi o riduci
            </Button>
          </div>
          <AskLinks ticker={p.ticker} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function PositionsPanel({
  q,
  limits,
  equity,
  cash,
  mobile,
}: {
  q: { data?: Sourced<PortfolioPosition[]>; isPending: boolean; error: Error | null };
  limits: RiskLimitsRead | null;
  equity: number | null;
  cash: number | null;
  mobile: boolean;
}) {
  const [action, setAction] = useState<{ kind: ActionKind; p: PortfolioPosition } | null>(null);
  const [detail, setDetail] = useState<PortfolioPosition | null>(null);
  const rows = q.data && q.data.source !== "unavailable" ? q.data.data : [];
  const onAction = (kind: ActionKind, p: PortfolioPosition) => {
    setDetail(null);
    setAction({ kind, p });
  };

  let body: ReactNode;
  if (q.isPending) body = <Bones rows={5} className="p-3" />;
  else if (q.error) body = <p className="px-4 py-6 text-center text-xs text-down">Posizioni non disponibili: {q.error.message}</p>;
  else if (!rows.length)
    body = (
      <div className="px-6 py-10 text-center">
        <p className="text-sm text-fg">Nessuna posizione aperta</p>
        <p className="mt-1 text-xs text-fg-subtle">Il conto è tutto in cassa{cash !== null ? ` (${fmtMoney(cash, { decimals: 0 })})` : ""}. Le posizioni compaiono qui quando un ordine viene eseguito.</p>
      </div>
    );
  else body = mobile ? <MobileList rows={rows} onOpen={setDetail} /> : <PositionsTable rows={rows} limits={limits} onAction={onAction} />;

  return (
    <>
      <div className={cn(!mobile && "overflow-x-auto")}>{body}</div>
      <SourceNote sourced={q.data} className="px-4 pb-3 pt-1" />
      {detail && <DetailSheet p={detail} limits={limits} onClose={() => setDetail(null)} onAction={onAction} />}
      {action?.kind === "close" && <CloseDialog p={action.p} onClose={() => setAction(null)} />}
      {action?.kind === "exit" && <ExitDialog p={action.p} equity={equity} onClose={() => setAction(null)} />}
    </>
  );
}
