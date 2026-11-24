import { Gavel, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { author, tickerAgentId } from "@/lib/authors";
import { CommandRefused, useCommand } from "@/lib/runtime/hooks";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { DECIDE_LABEL, fmtFraction, fmtRR, fmtScore } from "./labels";
import { DirectionTag } from "./parts";
import type { DecideAction } from "./types";

export type DecidableProposal = {
  id: number;
  ticker: string;
  agent?: string | null;
  direction: string | null;
  conviction: number | null;
  sizing_fraction: number | null;
  risk_reward: number | null;
};

const ACTIONS: DecideAction[] = ["accept", "defer", "reject", "ask"];

const HINT: Record<DecideAction, string> = {
  accept: "Genera la Bozza deterministica, che passa dal Risk Gate e poi dalla coda di approvazione.",
  defer: "La proposta torna all'agente del ticker con una data di verifica.",
  reject: "La proposta si chiude; l'agente del ticker la registra nella scheda.",
  ask: "Le domande tornano all'agente del ticker, che risponde nella sua chat.",
};

const PLACEHOLDER: Record<DecideAction, string> = {
  accept: "Perché entrare adesso, ed eventuale motivo del ridimensionamento",
  defer: "Cosa aspettare prima di riconsiderarla",
  reject: "Perché la tesi non regge",
  ask: "Le domande per l'agente del ticker",
};

const isoDay = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

function onRadioKeys(e: KeyboardEvent<HTMLElement>) {
  const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"];
  if (!keys.includes(e.key)) return;
  const radios = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]:not(:disabled)'));
  const i = radios.indexOf(document.activeElement as HTMLButtonElement);
  if (i < 0) return;
  e.preventDefault();
  const next = radios[(i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + radios.length) % radios.length];
  next.focus();
  next.click();
}

/**
 * Luca decides a ticker's proposal in the PM's place (`decide_proposal`, `confirm: true`): same path as the PM,
 * so an acceptance still goes through the deterministic draft and the sovereign Risk Gate. Refusals stay
 * inside the dialog, verbatim.
 */
export function DecideProposal({ proposal, trigger }: { proposal: DecidableProposal; trigger: ReactNode }) {
  const { writable, halted } = useShell();
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<DecideAction>("accept");
  const [reason, setReason] = useState("");
  const [sizing, setSizing] = useState("");
  const [checkDate, setCheckDate] = useState(isoDay(2));
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const decide = useCommand("decide_proposal", { invalidate: [["proposals"], ["dossier"], ["dossiers"], ["dossier_history"], ["office", "agents"]], toastRefusal: false });

  useEffect(() => {
    if (!open) return;
    setAction("accept");
    setReason("");
    setSizing(proposal.sizing_fraction !== null ? String(+(proposal.sizing_fraction * 100).toFixed(2)).replace(".", ",") : "");
    setCheckDate(isoDay(2));
    setRefusal(null);
  }, [open, proposal.sizing_fraction]);

  const sizingNum = sizing.trim() === "" ? null : Number(sizing.replace(",", "."));
  const sizingValid = sizingNum === null || (Number.isFinite(sizingNum) && sizingNum > 0 && sizingNum <= 100);
  const resized = action === "accept" && sizingNum !== null && proposal.sizing_fraction !== null && Math.abs(sizingNum / 100 - proposal.sizing_fraction) > 1e-6;
  const acceptBlocked = action === "accept" && halted;
  const canSubmit = writable && !acceptBlocked && reason.trim().length > 0 && sizingValid && (action !== "defer" || !!checkDate) && !decide.isPending;
  const agentId = proposal.agent ?? tickerAgentId(proposal.ticker);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setRefusal(null);
    decide.mutate(
      {
        proposal_id: proposal.id,
        action,
        reason: reason.trim(),
        confirm: true,
        ...(resized && sizingNum !== null ? { sizing_fraction: sizingNum / 100 } : {}),
        ...(action === "defer" ? { next_check_date: checkDate } : {}),
      },
      {
        onSuccess: () => {
          toast.success(`${DECIDE_LABEL[action]}: proposta su ${proposal.ticker}`, {
            description: action === "accept" ? "La Bozza passa ora dal Risk Gate." : "L'agente del ticker la riceve al prossimo turno.",
          });
          setOpen(false);
        },
        onError: (err) => {
          if (err instanceof CommandRefused) setRefusal(err.reasons.length ? err.reasons : ["Nessuna ragione indicata"]);
        },
      },
    );
  };

  const triggerEl = writable ? (
    <DialogTrigger render={<span className="inline-flex">{trigger}</span>} />
  ) : (
    <Tooltip>
      <TooltipTrigger
        render={
          <span tabIndex={0} className="inline-flex">
            {trigger}
          </span>
        }
      />
      <TooltipContent>Runtime irraggiungibile: comandi sospesi</TooltipContent>
    </Tooltip>
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {triggerEl}
      <DialogContent className="gap-0 p-0 sm:max-w-[440px]" showCloseButton={false}>
        <form onSubmit={submit}>
          <div className="px-5 pb-3 pt-5">
            <DialogTitle className="flex items-center gap-2 text-base font-semibold tracking-[-0.01em] text-fg">
              <Gavel className="size-4 text-fg-subtle" strokeWidth={1.75} aria-hidden /> Decidi al posto del PM
            </DialogTitle>
            <DialogDescription className="mt-1 text-xs leading-4 text-fg-subtle">
              Stesso percorso del Portfolio Manager. Il Risk Gate resta sovrano: può fermare anche una proposta accettata.
            </DialogDescription>
          </div>

          <Card className="mx-5 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-control border-line-strong/60 bg-ground p-3 text-xs shadow-none">
            <AuthorChip actor={agentId} size="sm" tooltip={author(agentId).name} />
            <span className="text-[13px] font-semibold text-fg">{proposal.ticker}</span>
            <DirectionTag value={proposal.direction} />
            <span className="text-fg-subtle">
              conviction <span className="num text-fg">{fmtScore(proposal.conviction)}</span>
            </span>
            <span className="text-fg-subtle">
              sizing <span className="num text-fg">{fmtFraction(proposal.sizing_fraction)}</span>
            </span>
            <span className="text-fg-subtle">
              R:R <span className={cn("num", proposal.risk_reward !== null && proposal.risk_reward < 1.5 ? "text-warn" : "text-fg")}>{fmtRR(proposal.risk_reward)}</span>
            </span>
          </Card>

          <fieldset className="mt-4 px-5">
            <legend className="mb-1.5 text-2xs text-fg-subtle">Decisione</legend>
            <div role="radiogroup" aria-label="Decisione" className="seg flex w-full" onKeyDown={onRadioKeys}>
              {ACTIONS.map((a) => (
                <button key={a} type="button" role="radio" aria-checked={action === a} tabIndex={action === a ? 0 : -1} onClick={() => setAction(a)} className="seg-item flex-1 justify-center">
                  {DECIDE_LABEL[a]}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-2xs leading-4 text-fg-subtle">{HINT[action]}</p>
          </fieldset>

          {action === "accept" && (
            <label className="block px-5 pt-3">
              <span className="mb-1.5 block text-2xs text-fg-subtle">Sizing (% del capitale)</span>
              <span className="flex items-center gap-2">
                <Input
                  value={sizing}
                  onChange={(e) => setSizing(e.target.value)}
                  inputMode="decimal"
                  aria-invalid={!sizingValid}
                  className="num h-8 w-24 rounded-control border-line-strong bg-ground px-2.5 text-sm text-fg outline-none focus-visible:border-accent-c/70 aria-[invalid=true]:border-warn"
                />
                <span className="text-2xs text-fg-subtle">{resized ? `ridimensionata da ${fmtFraction(proposal.sizing_fraction)}` : "come proposto"}</span>
              </span>
              {!sizingValid && <span className="mt-1 block text-2xs text-warn">Una percentuale tra 0 e 100.</span>}
            </label>
          )}

          {action === "defer" && (
            <label className="block px-5 pt-3">
              <span className="mb-1.5 block text-2xs text-fg-subtle">Riconsiderare il</span>
              <Input
                type="date"
                value={checkDate}
                min={isoDay(1)}
                onChange={(e) => setCheckDate(e.target.value)}
                className="num h-8 rounded-control border-line-strong bg-ground px-2.5 text-sm text-fg outline-none [color-scheme:dark] focus-visible:border-accent-c/70"
              />
            </label>
          )}

          <label className="block px-5 pt-3">
            <span className="mb-1.5 block text-2xs text-fg-subtle">Motivazione</span>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              required
              placeholder={PLACEHOLDER[action]}
              className="block w-full resize-none rounded-control border-line-strong bg-ground px-2.5 py-2 text-sm text-fg outline-none placeholder:text-fg-subtle focus-visible:border-accent-c/70"
            />
            <span className="mt-1 block text-2xs text-fg-subtle">Resta nello storico decisioni della scheda, firmata da te.</span>
          </label>

          {acceptBlocked && <p className="mx-5 mt-3 rounded-item bg-halt-ground px-2.5 py-2 text-xs text-fg">Halt attivo: non si accettano proposte finché il trading è fermo. Rimandare, rifiutare e chiedere restano possibili.</p>}

          {refusal && (
            <div role="alert" className="mx-5 mt-3 rounded-item bg-warn-soft px-2.5 py-2 text-xs leading-4">
              <p className="font-medium text-fg">Il Runtime ha rifiutato la decisione</p>
              <ul className="mt-0.5 text-fg-muted">
                {refusal.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-1.5 px-5 pb-5 pt-4">
            {action === "accept" && (
              <span className="mr-auto inline-flex items-center gap-1 text-2xs text-fg-subtle">
                <ShieldCheck className="size-3.5" strokeWidth={1.75} aria-hidden /> Poi il Risk Gate
              </span>
            )}
            <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={() => setOpen(false)}>
              Annulla
            </Button>
            <Button type="submit" size="sm" disabled={!canSubmit}>
              {decide.isPending ? "Invio…" : DECIDE_LABEL[action]}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
