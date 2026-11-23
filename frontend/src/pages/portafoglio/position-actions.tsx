import { Check, MessageSquareText, MoreHorizontal, Plug, ShieldCheck, ShieldX, SlidersHorizontal, SquareMinus } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { isCommandMissing } from "@/features/portfolio/api";
import { commandErrorText, useClosePosition, useModifyExit } from "@/features/portfolio/hooks";
import type { ClosePreview, ExitPreview, GateOutcome, PortfolioPosition } from "@/features/portfolio/types";
import { fmtPrice, fmtQty, toNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { onRadioKeys } from "@/pages/ufficio/parts";
import { useShell } from "@/shell/shell-state";
import { fmtFrac, fmtMoney, fmtRatio, tone } from "./parts";

export type ActionKind = "close" | "exit";

/** Why capital actions are off right now, or null when they are allowed. */
export function useCapitalBlock(): string | null {
  const { writable, halted } = useShell();
  if (!writable) return "Runtime irraggiungibile";
  if (halted) return "Halt attivo";
  return null;
}

/** The agents Luca can ask about a position: PM decides, Risk Analyst weighs exposure. Opens the ticker topic. */
export const ASK_AGENTS = ["portfolio_manager", "risk_analyst"] as const;
export const askHref = (agent: string, ticker: string) => `/ufficio/${agent}?chat=${encodeURIComponent(ticker)}`;

export function RowActions({ p, onAction }: { p: PortfolioPosition; onAction: (kind: ActionKind, p: PortfolioPosition) => void }) {
  const block = useCapitalBlock();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={`Azioni su ${p.ticker}`} className="text-fg-subtle data-[state=open]:bg-hover data-[state=open]:text-fg">
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">{p.ticker}{block ? ` · ${block}: azioni di capitale sospese` : ""}</DropdownMenuLabel>
        <DropdownMenuItem disabled={!!block} onSelect={() => onAction("close", p)}>
          <SquareMinus /> Chiudi o riduci…
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!!block} onSelect={() => onAction("exit", p)}>
          <SlidersHorizontal /> Modifica stop e target…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {ASK_AGENTS.map((a) => (
          <DropdownMenuItem key={a} asChild>
            <Link to={askHref(a, p.ticker)}>
              <AuthorChip actor={a} size="xs" /> Chiedi a {a === "portfolio_manager" ? "Portfolio Manager" : "Risk Analyst"}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="text-2xs text-fg-subtle">{label}</span>
      <span className="mt-1 block">{children}</span>
      {hint && <span className="mt-1 block text-2xs text-fg-subtle">{hint}</span>}
    </label>
  );
}

const inputCls =
  "num h-8 w-full rounded-control border border-line-strong bg-ground px-2.5 text-sm text-fg outline-none transition-colors placeholder:text-fg-subtle focus:border-accent-c disabled:opacity-50";

function GateBox({ gate, refusal }: { gate: GateOutcome | null; refusal: string[] | null }) {
  if (refusal) {
    return (
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
    );
  }
  if (!gate) return null;
  return gate.ok ? (
    <p className="flex items-center gap-1.5 text-xs text-fg-muted">
      <ShieldCheck className="size-3.5 text-up" /> Il Risk Gate accetta l'anteprima. Ricontrolla tutto all'invio.
    </p>
  ) : (
    <div className="rounded-control border border-[oklch(0.67_0.195_20/0.4)] bg-down-soft px-3 py-2.5 text-xs">
      <p className="flex items-center gap-1.5 font-medium text-down">
        <ShieldX className="size-3.5" /> Il Risk Gate lo rifiuterebbe
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-fg">
        {(gate.reasons.length ? gate.reasons : ["Nessuna ragione indicata"]).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

function Missing({ name }: { name: string }) {
  return (
    <div className="flex items-start gap-2 rounded-control bg-[oklch(0_0_0/0.2)] px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
      <Plug className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      <span>
        Il Runtime non espone ancora <span className="num text-fg">{name}</span>: anteprima e invio arrivano con il backend del Portafoglio. Nel frattempo puoi chiedere al PM di farlo.
      </span>
    </div>
  );
}

function PreviewGrid({ items }: { items: [string, ReactNode, string?][] }) {
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-control bg-line sm:grid-cols-4">
      {items.map(([k, v, cls]) => (
        <div key={k} className="bg-[oklch(0.215_0.008_260)] px-3 py-2">
          <dt className="text-2xs text-fg-subtle">{k}</dt>
          <dd className={cn("num mt-0.5 text-[13px] text-fg", cls)}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Debounced dry run: the preview follows the form without a button. */
function usePreview<P, T>(payload: P | null, run: (p: P) => Promise<{ ok: boolean; data: T | null; reasons?: string[] }>) {
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean; reasons: string[] | null }>({ data: null, error: null, loading: false, reasons: null });
  const key = JSON.stringify(payload);
  useEffect(() => {
    if (!payload) {
      setState({ data: null, error: null, loading: false, reasons: null });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      run(payload).then(
        (res) => live && setState({ data: res.data, error: null, loading: false, reasons: res.ok ? null : (res.reasons ?? []) }),
        (error) => live && setState({ data: null, error, loading: false, reasons: null }),
      );
    }, 350);
    return () => {
      live = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

export function CloseDialog({ p, onClose }: { p: PortfolioPosition; onClose: () => void }) {
  const block = useCapitalBlock();
  const send = useClosePosition();
  const [mode, setMode] = useState<"all" | "part">("all");
  const [qtyText, setQtyText] = useState(String(Math.max(1, Math.floor(p.qty / 2))));
  const [type, setType] = useState<"market" | "limit">("market");
  const [limitText, setLimitText] = useState(p.current_price !== null ? p.current_price.toFixed(2).replace(".", ",") : "");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const qty = mode === "all" ? null : toNum(qtyText.replace(",", "."));
  const limit = type === "limit" ? toNum(limitText.replace(",", ".")) : null;
  const qtyValid = mode === "all" || (qty !== null && qty > 0 && qty <= p.qty && Number.isInteger(qty));
  const limitValid = type === "market" || (limit !== null && limit > 0);
  const payload = qtyValid && limitValid ? { ticker: p.ticker, qty, order_type: type, limit_price: limit, dry_run: true, confirm: true as const } : null;
  const preview = usePreview<NonNullable<typeof payload>, ClosePreview>(payload, (x) => send.mutateAsync(x));
  const missing = isCommandMissing(preview.error);
  const pv = preview.data;
  const shownQty = pv?.qty ?? qty ?? p.qty;

  const submit = () => {
    if (!payload) return;
    setRefusal(null);
    send.mutate(
      { ...payload, dry_run: false },
      {
        onSuccess: (res) => {
          if (res.ok) onClose();
          else setRefusal(res.reasons);
        },
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[520px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">{mode === "all" ? `Chiudere ${p.ticker}?` : `Ridurre ${p.ticker}?`}</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">
            {fmtQty(p.qty)} azioni a {fmtPrice(p.avg_entry_price)} di media, ultimo {fmtPrice(p.current_price)}. L'ordine passa dal flusso ordini e dal Risk Gate come una vendita del PM.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-5 py-4">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <span className="text-2xs text-fg-subtle">Quantità</span>
              <div role="radiogroup" aria-label="Quantità" className="seg mt-1 flex" onKeyDown={onRadioKeys}>
                {(["all", "part"] as const).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={mode === m} tabIndex={mode === m ? 0 : -1} onClick={() => setMode(m)} className="seg-item">
                    {m === "all" ? "Tutta" : "Parziale"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-2xs text-fg-subtle">Ordine</span>
              <div role="radiogroup" aria-label="Tipo d'ordine" className="seg mt-1 flex" onKeyDown={onRadioKeys}>
                {(["market", "limit"] as const).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={type === m} tabIndex={type === m ? 0 : -1} onClick={() => setType(m)} className="seg-item">
                    {m === "market" ? "A mercato" : "Limite"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {(mode === "part" || type === "limit") && (
            <div className="grid grid-cols-2 gap-3">
              {mode === "part" ? (
                <Field
                  label={`Azioni da vendere (su ${fmtQty(p.qty)})`}
                  hint={
                    <span className="flex gap-1">
                      {[0.25, 0.5, 0.75].map((f) => (
                        <button key={f} type="button" onClick={() => setQtyText(String(Math.max(1, Math.round(p.qty * f))))} className="num h-5 rounded-tag bg-hover px-1.5 text-2xs text-fg-muted hover:text-fg">
                          {f * 100}%
                        </button>
                      ))}
                    </span>
                  }
                >
                  <input inputMode="numeric" value={qtyText} onChange={(e) => setQtyText(e.target.value)} aria-invalid={!qtyValid} className={cn(inputCls, !qtyValid && "border-down")} />
                </Field>
              ) : (
                <span />
              )}
              {type === "limit" && (
                <Field label="Prezzo limite">
                  <input inputMode="decimal" value={limitText} onChange={(e) => setLimitText(e.target.value)} aria-invalid={!limitValid} className={cn(inputCls, !limitValid && "border-down")} />
                </Field>
              )}
            </div>
          )}

          {missing ? (
            <Missing name="close_position" />
          ) : preview.error ? (
            <p className="text-xs text-down">Anteprima non riuscita: {commandErrorText(preview.error, "close_position")}</p>
          ) : (
            <div className={cn("space-y-3 transition-opacity duration-150", preview.loading && "opacity-60")} aria-busy={preview.loading}>
              <PreviewGrid
                items={[
                  ["Vendi", fmtQty(shownQty)],
                  ["Prezzo stimato", fmtPrice(pv?.est_price ?? (type === "limit" ? limit : p.current_price))],
                  ["Valore stimato", fmtMoney(pv?.est_value ?? null, { decimals: 0 })],
                  ["PnL realizzato", fmtMoney(pv?.realized_pnl ?? null, { sign: true }), tone(pv?.realized_pnl)],
                ]}
              />
              <p className="num text-2xs text-fg-subtle">
                {pv?.remaining_qty !== null && pv?.remaining_qty !== undefined
                  ? pv.remaining_qty > 0
                    ? `Restano ${fmtQty(pv.remaining_qty)} azioni; lo stop residuo segue la quantità rimasta.`
                    : "La posizione si chiude: stop e target protettivi vengono annullati."
                  : "Anteprima dal Runtime, senza effetti."}
              </p>
              <GateBox gate={pv?.gate ?? null} refusal={refusal ?? preview.reasons} />
            </div>
          )}
          {block && <p className="text-xs text-warn">{block}: la chiusura non può partire ora.</p>}
        </div>

        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>
            {refusal ? "Chiudi" : "Annulla"}
          </Button>
          <Button data-action="confirm-close" disabled={!payload || missing || !!block || send.isPending || preview.loading || pv?.gate?.ok === false} onClick={submit}>
            {mode === "all" ? `Chiudi ${p.ticker}` : `Vendi ${qty !== null ? fmtQty(qty) : ""} azioni`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ExitDialog({ p, equity, onClose }: { p: PortfolioPosition; equity: number | null; onClose: () => void }) {
  const block = useCapitalBlock();
  const send = useModifyExit();
  const [stopText, setStopText] = useState(p.stop_price !== null ? p.stop_price.toFixed(2).replace(".", ",") : "");
  const [targetText, setTargetText] = useState(p.target_price !== null ? p.target_price.toFixed(2).replace(".", ",") : "");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const stop = toNum(stopText.replace(",", "."));
  const target = toNum(targetText.replace(",", "."));
  const px = p.current_price;
  const stopChanged = stop !== null && stop !== p.stop_price;
  const targetChanged = target !== null && target !== p.target_price;
  const loosens = stopChanged && p.stop_price !== null && stop !== null && stop < p.stop_price;
  const valid = (stop === null || px === null || stop < px) && (target === null || px === null || target > px);
  const payload = (stopChanged || targetChanged) && valid ? { ticker: p.ticker, stop_price: stopChanged ? stop : null, target_price: targetChanged ? target : null, dry_run: true, confirm: true as const } : null;
  const preview = usePreview<NonNullable<typeof payload>, ExitPreview>(payload, (x) => send.mutateAsync(x));
  const missing = isCommandMissing(preview.error);
  const pv = preview.data;

  // Local figures so the effect is readable before the Runtime answers; the Runtime's preview wins.
  const local = useMemo(() => {
    if (px === null) return null;
    const risk = stop !== null ? Math.max(0, (px - stop) * p.qty) : null;
    const rr = stop !== null && target !== null && px > stop ? (target - px) / (px - stop) : null;
    return { risk, frac: risk !== null && equity ? risk / equity : null, rr };
  }, [px, stop, target, p.qty, equity]);
  const riskAfter = pv?.open_risk ?? local?.risk ?? null;
  const fracAfter = pv?.open_risk_fraction ?? local?.frac ?? null;

  const submit = () => {
    if (!payload) return;
    setRefusal(null);
    send.mutate(
      { ...payload, dry_run: false },
      {
        onSuccess: (res) => {
          if (res.ok) onClose();
          else setRefusal(res.reasons);
        },
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="gap-0 border-line-strong bg-raised p-0 sm:max-w-[520px]">
        <DialogHeader className="border-b border-line px-5 py-4 text-left">
          <DialogTitle className="text-base">Stop e target di {p.ticker}</DialogTitle>
          <DialogDescription className="text-xs text-fg-muted">
            Ultimo {fmtPrice(px)} · {fmtQty(p.qty)} azioni. Stringere lo stop è sempre consentito; allontanarlo aumenta il rischio e passa dal Risk Gate.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-5 py-4">
          <div className="grid grid-cols-2 gap-3">
            <Field
              label={`Stop (ora ${fmtPrice(p.stop_price)})`}
              hint={stopChanged ? <span className={loosens ? "text-warn" : "text-fg-muted"}>{loosens ? "Allarga lo stop: più rischio" : "Stringe lo stop"}</span> : undefined}
            >
              <input inputMode="decimal" value={stopText} onChange={(e) => setStopText(e.target.value)} className={cn(inputCls, "text-down", px !== null && stop !== null && stop >= px && "border-down")} />
            </Field>
            <Field label={`Target (ora ${fmtPrice(p.target_price)})`}>
              <input inputMode="decimal" value={targetText} onChange={(e) => setTargetText(e.target.value)} className={cn(inputCls, "text-up", px !== null && target !== null && target <= px && "border-down")} />
            </Field>
          </div>
          {!valid && <p className="text-xs text-down">Lo stop va sotto il prezzo corrente e il target sopra.</p>}

          {missing ? (
            <Missing name="modify_exit" />
          ) : preview.error ? (
            <p className="text-xs text-down">Anteprima non riuscita: {commandErrorText(preview.error, "modify_exit")}</p>
          ) : (
            <div className={cn("space-y-3 transition-opacity duration-150", preview.loading && "opacity-60")}>
              <PreviewGrid
                items={[
                  ["Rischio aperto ora", fmtMoney(pv?.open_risk_before ?? p.open_risk, { decimals: 0 })],
                  ["Dopo la modifica", fmtMoney(riskAfter, { decimals: 0 }), riskAfter !== null && p.open_risk !== null && riskAfter > p.open_risk ? "text-warn" : undefined],
                  ["% dell'equity", fmtFrac(fracAfter)],
                  ["R:R residuo", fmtRatio(local?.rr ?? null)],
                ]}
              />
              {!payload && valid && <p className="text-2xs text-fg-subtle">Modifica stop o target per vedere l'anteprima del Runtime.</p>}
              <GateBox gate={pv?.gate ?? null} refusal={refusal ?? preview.reasons} />
            </div>
          )}
          {block && <p className="text-xs text-warn">{block}: la modifica non può partire ora.</p>}
        </div>
        <DialogFooter className="border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>
            {refusal ? "Chiudi" : "Annulla"}
          </Button>
          <Button data-action="confirm-exit" disabled={!payload || missing || !!block || send.isPending || preview.loading || pv?.gate?.ok === false} onClick={submit}>
            <Check /> Applica
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AskLinks({ ticker, className }: { ticker: string; className?: string }) {
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {ASK_AGENTS.map((a) => (
        <Button key={a} asChild variant="outline" size="sm">
          <Link to={askHref(a, ticker)}>
            <MessageSquareText /> Chiedi a {a === "portfolio_manager" ? "PM" : "Risk Analyst"}
          </Link>
        </Button>
      ))}
    </div>
  );
}
