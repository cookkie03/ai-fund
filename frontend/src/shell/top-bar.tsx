import { Check, ChevronsUpDown, OctagonPause, Play, PanelRight, PanelRightClose } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fmtMoney, fmtPct, parseTs } from "@/lib/format";
import { marketSession } from "@/lib/market";
import { useCommand, useEquityHistory, usePortfolio } from "@/lib/runtime/hooks";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "./shell-state";
import { RuntimeStatus } from "./status";

function AccountSwitcher() {
  const { targets, target, selectTarget, health } = useRuntime();
  const label = health?.account_label ?? target.label ?? target.id;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="group inline-flex h-7 min-w-0 items-center gap-2 rounded-md px-2 text-sm transition-colors hover:bg-hover focus-visible:outline-2">
        <span className="hidden text-xs text-fg-subtle sm:inline">Account</span>
        <span className="truncate font-medium text-fg">{label}</span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-fg-subtle" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64 border-line-strong bg-raised">
        <DropdownMenuLabel className="text-xs font-normal text-fg-subtle">Un Runtime per account broker</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {targets.map((t) => (
          <DropdownMenuItem key={t.id} onSelect={() => selectTarget(t.id)} className="gap-2">
            <Check className={cn("size-4", t.id === target.id ? "opacity-100" : "opacity-0")} />
            <span className="truncate">{t.id === target.id ? label : (t.label ?? t.id)}</span>
            <span className="ml-auto truncate text-xs text-fg-subtle">{t.url || "locale"}</span>
          </DropdownMenuItem>
        ))}
        {targets.length === 1 && (
          <p className="px-2 pb-1.5 pt-1 text-xs leading-relaxed text-fg-subtle">Altri account: aggiungili in VITE_COCKPIT_RUNTIMES.</p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MarketClock() {
  const now = useNow(15_000);
  const m = marketSession(now);
  return (
    <Tooltip>
      <TooltipTrigger className="hidden h-7 items-center gap-2 rounded-md px-2 text-xs text-fg-muted lg:inline-flex">
        <span className={cn("size-1.5 rounded-full", m.session === "open" ? "bg-up" : m.session === "closed" ? "bg-fg-faint" : "bg-warn")} aria-hidden />
        <span className="text-fg">NYSE {m.label.toLowerCase()}</span>
        <span className="num text-fg-subtle">{m.clock} ET</span>
      </TooltipTrigger>
      <TooltipContent>{m.nextLabel} · festività non considerate</TooltipContent>
    </Tooltip>
  );
}

const nyDay = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
const nyDate = (ms: number) => nyDay.format(new Date(ms));

function EquityReadout() {
  const portfolio = usePortfolio();
  const history = useEquityHistory();
  const figures = useMemo(() => {
    const snap = portfolio.data;
    if (!snap) return null;
    // Day P&L against the last equity recorded on an earlier New York trading date.
    const day = nyDate(parseTs(snap.ts) ?? Date.now());
    const prev = (history.data ?? []).filter((p) => nyDate(parseTs(p.ts) ?? 0) < day).at(-1);
    const pnl = prev ? snap.equity - prev.equity : null;
    return { equity: snap.equity, pnl, pct: prev && prev.equity ? (pnl! / prev.equity) * 100 : null };
  }, [portfolio.data, history.data]);

  if (portfolio.isPending) return <span className="h-4 w-36 animate-pulse rounded bg-hover" aria-label="Caricamento equity" />;
  if (!figures) return <span className="text-xs text-fg-subtle">Nessuno snapshot del portafoglio</span>;
  const tone = figures.pnl === null ? "text-fg-muted" : figures.pnl >= 0 ? "text-up" : "text-down";
  return (
    <div className="flex items-baseline gap-3 text-xs">
      <span className="hidden text-fg-subtle md:inline">Equity</span>
      <span className="num text-sm font-medium text-fg">{fmtMoney(figures.equity)}</span>
      <span className={cn("num hidden sm:inline", tone)}>
        {fmtMoney(figures.pnl, { sign: true })} <span className="opacity-80">{fmtPct(figures.pct)}</span>
      </span>
      <span className="hidden text-fg-subtle lg:inline">oggi</span>
    </div>
  );
}

function HaltControl() {
  const { halted, writable } = useShell();
  const [open, setOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(true);
  const halt = useCommand("halt", { success: "Halt attivato: nessun ordine verrà inviato", invalidate: [["health"], ["orders"]] });
  const resume = useCommand("resume", { success: "Trading ripreso", invalidate: [["health"]] });
  const busy = halt.isPending || resume.isPending;

  return (
    <>
      {halted ? (
        <Button size="sm" onClick={() => setOpen(true)} disabled={!writable} className="bg-fg text-ground hover:bg-white">
          <Play className="size-3.5" /> Riprendi
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setOpen(true)}
          disabled={!writable}
          className="border-[oklch(0.67_0.195_20/0.5)] text-down hover:border-down hover:bg-down-soft hover:text-down"
        >
          <OctagonPause className="size-3.5" /> Halt
        </Button>
      )}
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent className="border-line-strong bg-raised sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{halted ? "Riprendere il trading?" : "Fermare il trading?"}</AlertDialogTitle>
            <AlertDialogDescription className="text-fg-muted">
              {halted
                ? "Il Risk Gate torna ad accettare ordini. Gli agenti riprendono a proporre e inviare ordini secondo la modalità dell'account."
                : "Halt blocca ogni nuovo ordine verso il broker. Gli agenti continuano ad analizzare e a scrivere, ma nessun ordine parte finché non riprendi."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {!halted && (
            <label className="flex cursor-pointer items-start gap-2.5 rounded-md border border-line px-3 py-2.5 text-sm">
              <input type="checkbox" checked={cancelOpen} onChange={(e) => setCancelOpen(e.target.checked)} className="mt-0.5 accent-[var(--down)]" />
              <span>
                Annulla anche gli ordini aperti
                <span className="block text-xs text-fg-subtle">Inviati, in coda o aperti presso il broker.</span>
              </span>
            </label>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              className={halted ? "" : "bg-[oklch(0.56_0.19_22)] text-white hover:bg-[oklch(0.6_0.19_22)]"}
              onClick={(e) => {
                e.preventDefault();
                const done = { onSuccess: () => setOpen(false) };
                if (halted) resume.mutate({ confirm: true }, done);
                else halt.mutate({ confirm: true, cancel_open: cancelOpen }, done);
              }}
            >
              {halted ? "Riprendi il trading" : "Attiva Halt"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export function TopBar() {
  const { halted, bridgeOpen, setBridgeOpen } = useShell();
  return (
    <header
      className={cn(
        "flex h-11 shrink-0 items-center gap-1 border-b px-2 transition-colors duration-200",
        halted ? "border-[oklch(0.58_0.2_25/0.55)] bg-halt-ground" : "border-line bg-panel",
      )}
    >
      <AccountSwitcher />
      <span className="mx-1 h-4 w-px bg-line" aria-hidden />
      <div className="sm:hidden">
        <RuntimeStatus compact />
      </div>
      <div className="hidden sm:block">
        <RuntimeStatus />
      </div>
      <MarketClock />
      {halted && (
        <span className="ml-2 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-semibold text-[oklch(0.86_0.08_25)]">
          <OctagonPause className="size-3.5" /> Halt attivo
        </span>
      )}
      <div className="ml-auto flex items-center gap-3">
        <EquityReadout />
        <span className="hidden h-4 w-px bg-line md:block" aria-hidden />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setBridgeOpen(!bridgeOpen)}
              aria-pressed={bridgeOpen}
              aria-label={bridgeOpen ? "Chiudi il Bridge" : "Apri il Bridge"}
              className={cn(bridgeOpen && "bg-hover text-fg")}
            >
              {bridgeOpen ? <PanelRightClose /> : <PanelRight />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Bridge e messaggi agli agenti</TooltipContent>
        </Tooltip>
        <HaltControl />
      </div>
    </header>
  );
}
