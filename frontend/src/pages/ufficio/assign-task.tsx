import { ListPlus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AGENTS, AGENT_IDS } from "@/lib/authors";
import { CommandRefused, useCommand } from "@/lib/runtime/hooks";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { onRadioKeys } from "./parts";

const TICKER = /^[A-Z][A-Z0-9.]{0,6}$/;

/**
 * Assign a task to an agent on a ticker (`enqueue_task`). The agent picks it up on its next turn;
 * the Runtime may refuse it, and its reasons stay inside the form that caused them.
 */
export function AssignTask({ agent: initialAgent, ticker: initialTicker, trigger, align = "end" }: { agent?: string; ticker?: string | null; trigger?: ReactNode; align?: "start" | "end" }) {
  const { writable } = useShell();
  const [open, setOpen] = useState(false);
  const [agent, setAgent] = useState(initialAgent ?? "portfolio_manager");
  const [ticker, setTicker] = useState(initialTicker ?? "");
  const [reason, setReason] = useState("");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const tickerRef = useRef<HTMLInputElement>(null);
  const enqueue = useCommand("enqueue_task", { invalidate: [["office", "agents"]], toastRefusal: false });

  useEffect(() => {
    if (!open) return;
    setAgent(initialAgent ?? "portfolio_manager");
    setTicker(initialTicker ?? "");
    setReason("");
    setRefusal(null);
  }, [open, initialAgent, initialTicker]);

  const symbol = ticker.trim().toUpperCase();
  const valid = TICKER.test(symbol);
  const canSubmit = writable && valid && !enqueue.isPending;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setRefusal(null);
    enqueue.mutate(
      { agent, ticker: symbol, reason: reason.trim() || `Richiesta di Luca dall'Ufficio: analizzare ${symbol}` },
      {
        onSuccess: () => {
          toast.success(`Task accodato a ${AGENTS[agent]?.short ?? agent} su ${symbol}`);
          setOpen(false);
        },
        onError: (err) => {
          if (err instanceof CommandRefused) setRefusal(err.reasons.length ? err.reasons : ["Nessuna ragione indicata"]);
        },
      },
    );
  };

  const button = trigger ?? (
    <Button variant="ghost" size="sm" disabled={!writable} data-action="assign-task">
      <ListPlus className="size-3.5" /> Assegna task
    </Button>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {writable ? (
        <PopoverTrigger asChild>{button}</PopoverTrigger>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0}>{button}</span>
          </TooltipTrigger>
          <TooltipContent>Runtime irraggiungibile: comandi sospesi</TooltipContent>
        </Tooltip>
      )}
      <PopoverContent
        align={align}
        className="w-[320px] p-0"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          tickerRef.current?.focus();
        }}
      >
        <form onSubmit={submit} className="flex flex-col">
          <div className="px-4 pb-2 pt-3.5">
            <h3 className="text-[13px] font-semibold text-fg">Assegna un task</h3>
            <p className="mt-0.5 text-2xs leading-4 text-fg-subtle">L'agente lo prende al prossimo turno e lo pesa come la richiesta di un collega.</p>
          </div>

          <fieldset className="px-4 py-2">
            <legend className="mb-1.5 text-2xs text-fg-subtle">Agente</legend>
            <div role="radiogroup" aria-label="Agente" className="flex flex-wrap gap-1" onKeyDown={onRadioKeys}>
              {AGENT_IDS.map((id) => (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={agent === id}
                      tabIndex={agent === id ? 0 : -1}
                      aria-label={AGENTS[id].name}
                      onClick={() => setAgent(id)}
                      className={cn(
                        "grid size-8 place-items-center rounded-item transition-[background-color,box-shadow,transform] duration-150 active:scale-[0.94]",
                        agent === id ? "bg-selected shadow-[inset_0_0_0_1px_var(--line-strong)]" : "hover:bg-hover",
                      )}
                    >
                      <AuthorChip actor={id} size="sm" tooltip={AGENTS[id].name} />
                    </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-fg">{AGENTS[agent]?.name ?? agent}</p>
          </fieldset>

          <label className="block px-4 py-2">
            <span className="mb-1.5 block text-2xs text-fg-subtle">Ticker</span>
            <input
              ref={tickerRef}
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="NVDA"
              autoComplete="off"
              spellCheck={false}
              aria-invalid={ticker.length > 0 && !valid}
              className="num h-8 w-full rounded-control border border-line-strong bg-ground px-2.5 text-sm uppercase text-fg outline-none placeholder:normal-case placeholder:text-fg-subtle focus:border-accent-c/70 aria-[invalid=true]:border-warn"
            />
            {ticker.length > 0 && !valid && <span className="mt-1 block text-2xs text-warn">Un simbolo USA, per esempio AAPL o BRK.B.</span>}
          </label>

          <label className="block px-4 py-2">
            <span className="mb-1.5 block text-2xs text-fg-subtle">Cosa deve fare</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="Rivedi i livelli dopo la trimestrale"
              className="block w-full resize-none rounded-control border border-line-strong bg-ground px-2.5 py-2 text-sm text-fg outline-none placeholder:text-fg-subtle focus:border-accent-c/70"
            />
          </label>

          {refusal && (
            <div role="alert" className="mx-4 mb-1 mt-1 rounded-item bg-warn-soft px-2.5 py-2 text-xs leading-4">
              <p className="font-medium text-fg">Il Runtime ha rifiutato il task</p>
              <ul className="mt-0.5 text-fg-muted">
                {refusal.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-end gap-1.5 px-4 pb-3.5 pt-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Annulla
            </Button>
            <Button type="submit" size="sm" disabled={!canSubmit}>
              {enqueue.isPending ? "Invio…" : "Accoda task"}
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
