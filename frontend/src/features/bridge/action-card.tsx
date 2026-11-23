import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, CircleSlash, Loader2, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { author } from "@/lib/authors";
import { fmtMoney, fmtPrice, fmtQty, fmtWhen, toNum } from "@/lib/format";
import { RuntimeError } from "@/lib/runtime/client";
import { CommandRefused } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import type { BridgeAction } from "./types";

// Capital actions the Bridge may only propose (handoff-backend.md §3). Luca confirms; the Runtime reruns the
// original command from its own handler with every check (Halt, Risk Gate, limits, current state).

const str = (v: unknown) => (v === null || v === undefined || v === "" ? null : String(v));

/** The command in words, from its payload. */
export function actionTitle(a: BridgeAction): string {
  const p = a.payload;
  const t = str(p.ticker)?.toUpperCase();
  switch (a.command) {
    case "approve_order":
      return `Approva l'ordine #${str(p.order_id) ?? "?"}`;
    case "reject_order":
      return `Rifiuta l'ordine #${str(p.order_id) ?? "?"}`;
    case "close_position":
      return toNum(p.qty) === null ? `Chiudi la posizione ${t ?? ""}`.trim() : `Riduci ${t ?? "la posizione"} di ${fmtQty(p.qty)} azioni`;
    case "modify_exit":
      return `Modifica stop e target di ${t ?? "una posizione"}`;
    case "decide_proposal": {
      const verb = { accept: "Accetta", defer: "Rimanda", reject: "Rifiuta", ask: "Chiedi chiarimenti su" }[String(p.action)] ?? "Decidi";
      return `${verb} la proposta #${str(p.proposal_id) ?? "?"}`;
    }
    case "halt":
      return "Ferma il trading (Halt)";
    case "resume":
      return "Riprendi il trading";
    case "update_risk_limits":
      return "Cambia i vincoli di rischio";
    default:
      return a.summary || a.command;
  }
}

/** The primary's label: the verb of what will happen. */
function confirmLabel(a: BridgeAction): string {
  switch (a.command) {
    case "approve_order":
      return "Conferma e approva";
    case "reject_order":
      return "Conferma il rifiuto";
    case "close_position":
      return toNum(a.payload.qty) === null ? "Conferma chiusura" : "Conferma riduzione";
    case "modify_exit":
      return "Conferma modifica";
    case "decide_proposal":
      return "Conferma decisione";
    case "halt":
      return "Conferma Halt";
    case "resume":
      return "Conferma ripresa";
    case "update_risk_limits":
      return "Conferma e applica";
    default:
      return "Conferma";
  }
}

/** Commands that would send or change orders: Halt suspends them, as in the Portafoglio. */
const ORDER_COMMANDS = new Set(["approve_order", "close_position", "modify_exit", "decide_proposal"]);

const LABEL: Record<string, string> = {
  order_id: "Ordine",
  ticker: "Ticker",
  qty: "Quantità",
  stop_price: "Stop",
  target_price: "Target",
  proposal_id: "Proposta",
  action: "Decisione",
  reason: "Motivo",
  cancel_open: "Annulla ordini aperti",
  sizing_fraction: "Sizing",
  next_check_date: "Ricontrolla il",
  quantity: "Quantità",
  price: "Prezzo",
  value: "Controvalore",
  realized_pnl: "P&L realizzato",
  risk_amount: "Rischio",
  new_risk: "Nuovo rischio",
  risk_reward: "R:R",
  rr: "R:R",
  remaining_qty: "Restano",
};

const DECISION: Record<string, string> = { accept: "Accetta", defer: "Rimanda", reject: "Rifiuta", ask: "Chiedi" };

function fmtValue(key: string, v: unknown): string {
  if (v === null || v === undefined) return key === "qty" ? "tutta la posizione" : "—";
  if (typeof v === "boolean") return v ? "sì" : "no";
  if (key === "action") return DECISION[String(v)] ?? String(v);
  if (key.endsWith("_fraction") || key === "fraction") return `${((toNum(v) ?? 0) * 100).toLocaleString("it-IT", { maximumFractionDigits: 2 })}%`;
  if (/pnl|value|amount|risk$|new_risk/.test(key)) return fmtMoney(v, { sign: /pnl/.test(key) });
  if (/price|^stop|^target/.test(key)) return `$${fmtPrice(v)}`;
  if (key === "rr" || key === "risk_reward") return (toNum(v) ?? 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (/qty|quantity/.test(key)) return fmtQty(v);
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${LABEL[k] ?? k.replace(/_/g, " ")} ${fmtValue(k, x)}`).join(" · ");
  return String(v);
}

function Fields({ data, className }: { data: Record<string, unknown>; className?: string }) {
  const rows = Object.entries(data).filter(([k]) => k !== "confirm" && k !== "dry_run");
  if (!rows.length) return null;
  return (
    <dl className={cn("grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs", className)}>
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-subtle">{LABEL[k] ?? k.replace(/_/g, " ")}</dt>
          <dd className={cn("num min-w-0 text-fg", k === "reason" && "whitespace-pre-wrap text-pretty")}>{fmtValue(k, v)}</dd>
        </div>
      ))}
    </dl>
  );
}

const STATUS: Record<BridgeAction["status"], { label: string; cls: string }> = {
  pending: { label: "Da confermare", cls: "bg-warn-soft text-warn" },
  confirmed: { label: "In esecuzione", cls: "bg-accent-soft text-accent-c" },
  executed: { label: "Eseguita", cls: "bg-up-soft text-up" },
  failed: { label: "Rifiutata", cls: "bg-down-soft text-down" },
  dismissed: { label: "Annullata", cls: "bg-hover text-fg-muted" },
};

/** A capital action the Bridge proposes: what it does, the Runtime's preview, and Luca's explicit confirmation. */
export function ActionCard({ action, compact = false }: { action: BridgeAction; compact?: boolean }) {
  const { client } = useRuntime();
  const qc = useQueryClient();
  const { writable, halted } = useShell();
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const decide = useMutation({
    mutationFn: async (decision: "confirm" | "dismiss") => {
      const res = await client.command("bridge_action_decide", { action_id: action.id, decision, confirm: decision === "confirm" });
      if (!res.ok) throw new CommandRefused(res.reasons);
      return res;
    },
    onMutate: () => setRefusal(null),
    onError: (err) =>
      setRefusal(
        err instanceof CommandRefused
          ? err.reasons.length
            ? err.reasons
            : ["Nessuna ragione indicata"]
          : err instanceof RuntimeError && err.unreachable
            ? ["Runtime irraggiungibile: la decisione non è stata inviata."]
            : err instanceof RuntimeError && err.status === 404
              ? ["Il Runtime non espone ancora il comando bridge_action_decide."]
              : [err instanceof Error ? err.message : String(err)],
      ),
    onSettled: () => {
      for (const k of [["bridge"], ["orders"], ["portfolio"], ["pf"], ["proposals"], ["health"]]) qc.invalidateQueries({ queryKey: k });
    },
  });

  const s = STATUS[action.status];
  const open = action.status === "pending";
  const gateNo = action.preview?.ok === false;
  const haltBlocks = halted && ORDER_COMMANDS.has(action.command);
  const why = !writable ? "Runtime irraggiungibile" : haltBlocks ? "Halt attivo: nessun ordine viene inviato" : gateNo ? "Il Risk Gate la rifiuterebbe: leggi i motivi sopra" : null;
  const destructive = action.command === "halt";
  const decidedBy = action.decided_by ? author(action.decided_by).short : null;

  return (
    <section
      aria-label={`Azione proposta: ${actionTitle(action)}`}
      data-action-status={action.status}
      className={cn(
        "mt-2 max-w-[60ch] rounded-control bg-raised shadow-[inset_0_0_0_1px_oklch(1_0_0/0.05),0_1px_2px_oklch(0_0_0/0.35)]",
        action.status === "dismissed" && "opacity-70",
      )}
    >
      <header className="flex items-start gap-2 px-3 pt-2.5">
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-semibold leading-5 text-fg">{actionTitle(action)}</h3>
          {action.summary && <p className="mt-0.5 text-xs leading-[1.1rem] text-fg-muted">{action.summary}</p>}
        </div>
        <span className={cn("num mt-0.5 inline-flex h-5 shrink-0 items-center gap-1 rounded-tag px-1.5 text-2xs font-medium", s.cls)}>
          {action.status === "confirmed" && <Loader2 className="size-3 animate-spin" aria-hidden />}
          {s.label}
        </span>
      </header>

      <div className={cn("grid items-start gap-3 px-3 pb-3 pt-2", !compact && "sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]")}>
        <Fields data={action.payload} />
        {action.preview && (
          <div className={cn("rounded-item px-2.5 py-2", action.preview.ok ? "bg-[oklch(0_0_0/0.22)]" : "bg-down-soft")}>
            <p className="flex items-center gap-1.5 text-2xs font-medium text-fg">
              {action.preview.ok ? <ShieldCheck className="size-3.5 text-fg-muted" aria-hidden /> : <ShieldAlert className="size-3.5 text-down" aria-hidden />}
              {action.preview.ok ? "Anteprima del Runtime · Risk Gate: passa" : "Anteprima del Runtime · Risk Gate: la rifiuterebbe"}
            </p>
            {action.preview.reasons.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs leading-[1.1rem] text-fg-muted">
                {action.preview.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            {action.preview.detail && <Fields data={action.preview.detail} className="mt-1.5" />}
          </div>
        )}
      </div>

      {(action.status === "executed" || action.status === "failed" || action.status === "dismissed") && (
        <div className={cn("mx-3 mb-3 rounded-item px-2.5 py-2 text-xs", action.status === "failed" ? "bg-down-soft" : "bg-[oklch(0_0_0/0.22)]")}>
          <p className="flex items-center gap-1.5 font-medium text-fg">
            {action.status === "executed" ? <Check className="size-3.5 text-up" aria-hidden /> : action.status === "failed" ? <Ban className="size-3.5 text-down" aria-hidden /> : <CircleSlash className="size-3.5 text-fg-subtle" aria-hidden />}
            {action.status === "executed" ? "Eseguita dal Runtime" : action.status === "failed" ? "Il Runtime l'ha rifiutata" : "Annullata, non eseguita"}
            {(decidedBy || action.decided_ts) && (
              <span className="num ml-auto font-normal text-fg-subtle">
                {decidedBy}
                {decidedBy && action.decided_ts ? " · " : ""}
                {action.decided_ts ? fmtWhen(action.decided_ts) : ""}
              </span>
            )}
          </p>
          {action.result_reasons.length > 0 && (
            <ul className="mt-1 space-y-0.5 leading-[1.1rem] text-fg-muted">
              {action.result_reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {open && (
        <footer className="px-3 pb-3">
          {refusal && (
            <div role="alert" className="mb-2 rounded-item bg-warn-soft px-2.5 py-2 text-xs leading-4">
              <p className="flex items-center gap-1.5 font-medium text-fg">
                <TriangleAlert className="size-3.5 text-warn" aria-hidden /> Il Runtime non ha eseguito l'azione
              </p>
              <ul className="mt-0.5 text-fg-muted">
                {refusal.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Tooltip open={why ? undefined : false}>
              <TooltipTrigger asChild>
                <span tabIndex={why ? 0 : -1}>
                  <Button
                    size="sm"
                    variant={destructive ? "destructive" : "default"}
                    disabled={!!why || decide.isPending}
                    onClick={() => decide.mutate("confirm")}
                    data-action="confirm-action"
                  >
                    {decide.isPending && decide.variables === "confirm" && <Loader2 className="animate-spin" />}
                    {confirmLabel(action)}
                  </Button>
                </span>
              </TooltipTrigger>
              {why && <TooltipContent>{why}</TooltipContent>}
            </Tooltip>
            <Button size="sm" variant="ghost" disabled={!writable || decide.isPending} onClick={() => decide.mutate("dismiss")} data-action="dismiss-action">
              Annulla
            </Button>
            <span className="min-w-0 flex-1 text-2xs leading-4 text-fg-subtle">
              {why && why !== "Il Risk Gate la rifiuterebbe: leggi i motivi sopra" ? why : "Il Runtime ricontrolla Halt, Risk Gate e stato attuale prima di eseguire."}
            </span>
          </div>
        </footer>
      )}
    </section>
  );
}
