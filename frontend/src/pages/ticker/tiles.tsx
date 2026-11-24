import { ArrowUp, CalendarClock, Check, Gavel, Minus, Plus, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { DecideProposal } from "@/features/dossier/decide-proposal";
import { ACTION_LABEL, daysUntil, fmtDate, fmtFraction, fmtRR, fmtScore, sectionLabel, verdictTone } from "@/features/dossier/labels";
import { DirectionTag, ProposalTag, Score } from "@/features/dossier/parts";
import type { DeskFact, Dossier, DossierVersion, Read } from "@/features/dossier/types";
import { AGENT_IDS, author, LUCA } from "@/lib/authors";
import { fmtAge, fmtDateTime, fmtPrice, fmtWhen, parseTs } from "@/lib/format";
import { CommandRefused, useCommand } from "@/lib/runtime/hooks";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { SignatureChip, Signed } from "./author-focus";

/** A dossier section: a tile with an anchor for the phone index. */
export function DossierTile({ id, title, meta, actions, children, className }: { id: string; title: ReactNode; meta?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("scroll-mt-14 flex min-w-0 flex-col rounded-tile bg-ground", className)}>
      <header className="flex min-h-11 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 py-2 pl-4 pr-3">
        <h2 id={`${id}-title`} className="text-[13px] font-semibold tracking-[-0.005em] text-fg">
          {title}
        </h2>
        {meta}
        {actions && <div className="ml-auto flex shrink-0 items-center gap-1">{actions}</div>}
      </header>
      <div className="min-w-0 flex-1 px-4 pb-4">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-fg-subtle">{children}</p>;
}

function Stamp({ by, ts, now }: { by: string; ts: string | null; now: number }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-2xs text-fg-subtle">
      <SignatureChip by={by} size="xs" />
      <span className="truncate">{author(by).short}</span>
      {ts && (
        <time className="num shrink-0" dateTime={ts} title={fmtDateTime(ts)}>
          · {fmtWhen(ts, now)}
        </time>
      )}
    </span>
  );
}

// ——— Tesi ———

export function ThesisTile({ d, className }: { d: Dossier; className?: string }) {
  const now = useNow(60_000);
  const t = d.thesis;
  const check = daysUntil(t?.next_check_date, now);
  return (
    <DossierTile id="tesi" title="Tesi" className={className} meta={t && <Stamp by={t.author} ts={t.ts} now={now} />}>
      {!t ? (
        <Empty>Nessuna tesi ancora: l'agente del ticker la scrive alla fine del ciclo, dopo aver raccolto le analisi degli specialist.</Empty>
      ) : (
        <Signed by={t.author} className="space-y-4">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <span className="flex items-center gap-2">
              <span className="text-2xs text-fg-subtle">Direzione</span>
              <DirectionTag value={t.direction} />
            </span>
            <span className="flex items-center gap-2">
              <span className="text-2xs text-fg-subtle">Conviction</span>
              <Score value={t.conviction} color={author(t.author).color} label="Conviction" />
            </span>
            {t.time_horizon && (
              <span className="flex items-center gap-2">
                <span className="text-2xs text-fg-subtle">Orizzonte</span>
                <span className="text-xs text-fg">{t.time_horizon}</span>
              </span>
            )}
            {t.next_check_date && (
              <span className={cn("flex items-center gap-1.5 text-xs", check !== null && check < 0 ? "text-warn" : "text-fg")}>
                <CalendarClock className="size-3.5 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                Prossima verifica <span className="num">{fmtDate(t.next_check_date, now)}</span>
                {check !== null && <span className="num text-2xs text-fg-subtle">{check === 0 ? "oggi" : check > 0 ? `tra ${check} g` : `scaduta da ${-check} g`}</span>}
              </span>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {(
              [
                ["Pro", t.pro, Plus],
                ["Contro", t.contro, Minus],
              ] as const
            ).map(([label, items, Icon]) => (
              <div key={label}>
                <h3 className="mb-1.5 text-2xs font-medium text-fg-subtle">{label}</h3>
                {items.length ? (
                  <ul className="space-y-1.5">
                    {items.map((p) => (
                      <li key={p} className="flex gap-2 text-[13px] leading-5 text-fg">
                        <Icon className="mt-[3px] size-3.5 shrink-0 text-fg-subtle" strokeWidth={2} aria-hidden />
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>Nessuno indicato.</Empty>
                )}
              </div>
            ))}
          </div>

          {t.catalysts.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-2xs font-medium text-fg-subtle">Catalizzatori</h3>
              <ul className="flex flex-wrap gap-1.5">
                {[...t.catalysts]
                  .sort((a, b) => (Date.parse(a.date ?? "") || Infinity) - (Date.parse(b.date ?? "") || Infinity))
                  .map((c) => {
                    const left = daysUntil(c.date, now);
                    return (
                      <li key={`${c.text}-${c.date}`} className={cn("inline-flex h-7 items-center gap-2 rounded-item bg-[oklch(0_0_0/0.25)] px-2.5 text-xs", left !== null && left < 0 && "opacity-50")}>
                        <span className="num font-medium text-fg">{fmtDate(c.date, now)}</span>
                        <span className="text-fg-muted">{c.text}</span>
                        {left !== null && left >= 0 && <span className="num text-2xs text-fg-subtle">{left === 0 ? "oggi" : `tra ${left} g`}</span>}
                      </li>
                    );
                  })}
              </ul>
            </div>
          )}
        </Signed>
      )}
    </DossierTile>
  );
}

// ——— Proposta e Risk Gate ———

/** Stop, entry, target on one line, with the current price: the trade's geometry at a glance. */
function Ladder({ stop, entry, target, price }: { stop: number; entry: number; target: number; price: number | null }) {
  const lo = Math.min(stop, target, price ?? stop);
  const hi = Math.max(stop, target, price ?? target);
  const pos = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  const long = target >= entry;
  return (
    <div className="pb-5 pt-1" aria-hidden>
      <div className="relative h-1.5 rounded-tag bg-[oklch(0_0_0/0.35)]">
        <span className="absolute inset-y-0 rounded-l-tag bg-down/70" style={{ left: pos(long ? stop : entry), width: `calc(${pos(long ? entry : stop)} - ${pos(long ? stop : entry)})` }} />
        <span className="absolute inset-y-0 rounded-r-tag bg-up/70" style={{ left: pos(long ? entry : target), width: `calc(${pos(long ? target : entry)} - ${pos(long ? entry : target)})` }} />
        <span className="absolute -top-1 h-3.5 w-0.5 -translate-x-1/2 rounded-tag bg-fg" style={{ left: pos(entry) }} />
        {price !== null && <span className="absolute -top-1.5 size-2.5 -translate-x-1/2 rotate-45 bg-accent-c shadow-[0_0_0_2px_var(--ground)]" style={{ left: pos(price) }} />}
      </div>
      <div className="relative mt-1.5 h-3 text-2xs text-fg-subtle">
        {(
          [
            [stop, "stop", ""],
            [entry, "ingresso", "text-fg-muted"],
            [target, "target", ""],
          ] as const
        ).map(([v, label, tone]) => {
          const at = (v - lo) / (hi - lo || 1);
          // Labels at the ends hug the edge instead of spilling out of the tile.
          const shift = at < 0.08 ? "translate-x-0" : at > 0.92 ? "-translate-x-full" : "-translate-x-1/2";
          return (
            <span key={label} className={cn("absolute whitespace-nowrap", shift, tone)} style={{ left: pos(v) }}>
              {label}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function Level({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | "warn" }) {
  return (
    <div className="min-w-0">
      <dt className="text-2xs text-fg-subtle">{label}</dt>
      <dd className={cn("num mt-0.5 text-sm font-medium", tone === "up" ? "text-up" : tone === "down" ? "text-down" : tone === "warn" ? "text-warn" : "text-fg")}>{value}</dd>
    </div>
  );
}

export function ProposalTile({ d, className }: { d: Dossier; className?: string }) {
  const now = useNow(30_000);
  const p = d.proposal;
  const r = d.risk;
  const tone = verdictTone(r?.verdict);
  const failed = r?.guardrails.filter((g) => !g.ok).length ?? 0;
  const submitted = parseTs(p?.submitted_ts);
  return (
    <DossierTile
      id="proposta"
      title="Proposta e Risk Gate"
      className={className}
      meta={
        p && (
          <>
            <ProposalTag status={p.status} />
            {submitted && <span className="num text-2xs text-fg-subtle" title={fmtDateTime(p.submitted_ts)}>inviata {fmtAge(submitted, now)} fa</span>}
          </>
        )
      }
      actions={
        p?.status === "pending" && (
          <DecideProposal
            proposal={{ id: p.id, ticker: d.ticker, agent: null, direction: d.thesis?.direction ?? null, conviction: d.thesis?.conviction ?? null, sizing_fraction: p.sizing_fraction, risk_reward: p.risk_reward }}
            trigger={
              <Button size="sm" className="h-7">
                <Gavel className="size-3.5" /> Decidi
              </Button>
            }
          />
        )
      }
    >
      {!p ? (
        <Empty>{d.thesis ? "L'agente del ticker non ha ancora sottoposto una proposta al PM." : "Nessuna proposta: arriva dopo la tesi, quando l'agente del ticker la sottopone al PM."}</Empty>
      ) : (
        <div className="space-y-4">
          {p.stop_price !== null && p.entry_price !== null && p.target_price !== null && <Ladder stop={p.stop_price} entry={p.entry_price} target={p.target_price} price={d.identity.current_price} />}
          <dl className="grid grid-cols-3 gap-x-4 gap-y-3 sm:grid-cols-5">
            <Level label="Ingresso" value={`$${fmtPrice(p.entry_price)}`} />
            <Level label="Stop" value={`$${fmtPrice(p.stop_price)}`} tone="down" />
            <Level label="Target" value={`$${fmtPrice(p.target_price)}`} tone="up" />
            <Level label="R:R" value={fmtRR(p.risk_reward)} tone={p.risk_reward !== null && p.risk_reward < 1.5 ? "warn" : undefined} />
            <Level label="Sizing" value={fmtFraction(p.sizing_fraction)} />
          </dl>
          {(p.k_entry !== null || p.k_stop !== null || p.k_tp !== null) && (
            <p className="num text-2xs text-fg-subtle">
              Coefficienti: k ingresso {fmtScore(p.k_entry)} · k stop {fmtScore(p.k_stop)} · k target {fmtScore(p.k_tp)}
            </p>
          )}

          <div className="rounded-control bg-[oklch(0_0_0/0.22)] p-1.5">
            {!r ? (
              <p className="px-2 py-1.5 text-xs text-fg-subtle">Il Risk Gate non ha ancora valutato questa proposta.</p>
            ) : (
              <>
                <div className={cn("flex items-start gap-2 rounded-item px-2 py-1.5", tone === "block" && "bg-down-soft")}>
                  {tone === "block" ? <ShieldAlert className="mt-px size-4 shrink-0 text-down" strokeWidth={1.75} aria-hidden /> : <ShieldCheck className={cn("mt-px size-4 shrink-0", tone === "ok" ? "text-up" : "text-fg-subtle")} strokeWidth={1.75} aria-hidden />}
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-fg">
                      {tone === "block" ? "Bloccata dal Risk Gate" : tone === "ok" ? "Il Risk Gate la lascia passare" : `Risk Gate: ${r.verdict}`}
                      {failed > 0 && <span className="num font-normal text-fg-muted"> · {failed === 1 ? "1 regola violata" : `${failed} regole violate`}</span>}
                    </p>
                    {r.rationale && <p className="mt-0.5 text-xs leading-4 text-fg-muted">{r.rationale}</p>}
                  </div>
                </div>
                {r.guardrails.length > 0 && (
                  <ul className="mt-1 space-y-px">
                    {r.guardrails.map((g) => (
                      <li key={g.rule} className="flex min-h-7 items-center gap-2 rounded-item px-2 text-xs">
                        {g.ok ? <Check className="size-3.5 shrink-0 text-fg-subtle" strokeWidth={2} aria-label="rispettata" /> : <X className="size-3.5 shrink-0 text-down" strokeWidth={2.25} aria-label="violata" />}
                        <span className={g.ok ? "text-fg-muted" : "font-medium text-fg"}>{g.rule}</span>
                        {g.detail && <span className={cn("num ml-auto shrink-0 text-right", g.ok ? "text-fg-subtle" : "text-down")}>{g.detail}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </DossierTile>
  );
}

// ——— Analisi degli specialist ———

const SPECIALISTS = AGENT_IDS.filter((a) => a !== "portfolio_manager");

function FactBody({ f, now, lead }: { f: DeskFact; now: number; lead: boolean }) {
  const ref = f.reference_date ? fmtDate(f.reference_date, now) : null;
  const old = f.status !== "active";
  return (
    <Signed by={f.agent} as="li">
      <p className={cn("leading-5", lead ? "text-[13px] text-fg" : "text-xs", f.status === "stale" && "text-fg-muted", f.status === "superseded" && "text-fg-subtle line-through decoration-fg-faint")}>{f.text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-2xs text-fg-subtle">
        <Score value={f.confidence} color={old ? "var(--fg-subtle)" : author(f.agent).color} label="Confidenza" className={old ? "opacity-70" : ""} />
        <time className="num" dateTime={f.ts} title={`Scritta ${fmtDateTime(f.ts)}`}>
          {fmtWhen(f.ts, now)}
        </time>
        {ref && <span className="num">rif. {ref}</span>}
        {f.status === "stale" && <span className="num rounded-tag bg-warn-soft px-1 leading-4 text-warn">Vecchio · {fmtAge(parseTs(f.ts), now)}</span>}
        {f.status === "superseded" && <span className="rounded-tag bg-hover px-1 leading-4 text-fg-subtle">Superato</span>}
      </div>
    </Signed>
  );
}

function DeskTile({ agent, facts, className }: { agent: string; facts: DeskFact[]; className?: string }) {
  const now = useNow(60_000);
  const [showOld, setShowOld] = useState(false);
  const who = author(agent);
  const order = { active: 0, stale: 1, superseded: 2 } as const;
  const sorted = [...facts].sort((a, b) => order[a.status] - order[b.status] || (parseTs(b.ts) ?? 0) - (parseTs(a.ts) ?? 0));
  const lead = sorted[0];
  const rest = sorted.slice(1);
  const superseded = rest.filter((f) => f.status === "superseded");
  const visible = showOld ? rest : rest.filter((f) => f.status !== "superseded");
  const sections = Array.from(new Set(facts.map((f) => f.section).filter(Boolean)));
  return (
    <article aria-label={`Analisi di ${who.name}`} className={cn("flex min-w-0 flex-col rounded-tile bg-ground p-4", className)}>
      <header className="mb-3 flex items-center gap-2">
        <SignatureChip by={agent} size="sm" tooltip={who.name} />
        <h3 className="min-w-0 truncate text-[13px] font-semibold text-fg">{who.short}</h3>
        {sections.length > 0 && <span className="ml-auto truncate text-2xs text-fg-subtle">{sections.map(sectionLabel).join(" · ")}</span>}
      </header>
      {!lead ? (
        <Empty>Nessuna analisi di {who.short} in questa scheda.</Empty>
      ) : (
        <ul className="space-y-3">
          <FactBody f={lead} now={now} lead />
          {visible.map((f, i) => (
            <FactBody key={`${f.ts}-${i}`} f={f} now={now} lead={false} />
          ))}
        </ul>
      )}
      {superseded.length > 0 && (
        <button type="button" onClick={() => setShowOld((v) => !v)} aria-expanded={showOld} className="mt-3 self-start rounded-item text-2xs text-fg-subtle outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60">
          {showOld ? "Nascondi i fatti superati" : superseded.length === 1 ? "Mostra 1 fatto superato" : `Mostra ${superseded.length} fatti superati`}
        </button>
      )}
    </article>
  );
}

export function DesksSection({ d }: { d: Dossier }) {
  const byAgent = useMemo(() => {
    const m = new Map<string, DeskFact[]>();
    for (const f of d.desks) m.set(f.agent, [...(m.get(f.agent) ?? []), f]);
    return m;
  }, [d.desks]);
  const agents = [...SPECIALISTS, ...Array.from(byAgent.keys()).filter((a) => !SPECIALISTS.includes(a))];
  const stale = d.desks.filter((f) => f.status === "stale").length;
  return (
    <section id="analisi" aria-labelledby="analisi-title" className="scroll-mt-14">
      <h2 id="analisi-title" className="sr-only">
        Analisi degli specialist
      </h2>
      {d.desks.length === 0 && (
        <p className="rounded-tile bg-ground px-4 py-3.5 text-xs text-fg-subtle">
          <span className="font-medium text-fg">Analisi degli specialist</span> · nessuna ancora: arrivano quando l'agente del ticker chiama Tecnico, Mercato, Sentiment, Fondamentali e Rischio nel suo ciclo.
        </p>
      )}
      {stale > 0 && (
        <p className="sr-only">
          {stale} fatti vecchi nelle analisi
        </p>
      )}
      <div className={cn("grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-5", d.desks.length === 0 && "hidden")}>
        {agents.map((a) => (
          <DeskTile key={a} agent={a} facts={byAgent.get(a) ?? []} />
        ))}
      </div>
    </section>
  );
}

// ——— Storico decisioni ———

export function DecisionsTile({ d, className }: { d: Dossier; className?: string }) {
  const now = useNow(60_000);
  const rows = [...d.decisions].sort((a, b) => (parseTs(b.ts) ?? 0) - (parseTs(a.ts) ?? 0));
  return (
    <DossierTile id="decisioni" title="Storico decisioni" className={className} meta={rows.length > 0 && <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">{rows.length}</span>}>
      {rows.length === 0 ? (
        <Empty>Nessuna decisione registrata su {d.ticker}.</Empty>
      ) : (
        <ol className="-mx-1.5 space-y-px">
          {rows.map((r, i) => (
            <Signed key={`${r.ts}-${i}`} by={r.actor} as="li" className="flex gap-2.5 rounded-item px-1.5 py-2">
              <SignatureChip by={r.actor} size="sm" className="mt-px" />
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  <span className="font-medium text-fg">{author(r.actor).name}</span>
                  <span className="text-fg-muted">{ACTION_LABEL[r.action] ?? r.action}</span>
                  <time className="num ml-auto text-2xs text-fg-subtle" dateTime={r.ts} title={fmtDateTime(r.ts)}>
                    {fmtWhen(r.ts, now)}
                    {r.cycle_id !== null && ` · ciclo #${r.cycle_id}`}
                  </time>
                </p>
                {r.reason && <p className="mt-0.5 text-[13px] leading-5 text-fg">{r.reason}</p>}
              </div>
            </Signed>
          ))}
        </ol>
      )}
    </DossierTile>
  );
}

// ——— Lezioni ———

const EXIT: Record<string, { label: string; tone: "up" | "down" | "flat" }> = {
  take_profit: { label: "Target", tone: "up" },
  stop_loss: { label: "Stop", tone: "down" },
  manual: { label: "Manuale", tone: "flat" },
  time: { label: "Scadenza", tone: "flat" },
};

export function LessonsTile({ d, className }: { d: Dossier; className?: string }) {
  const now = useNow(60_000);
  return (
    <DossierTile id="lezioni" title="Lezioni dai trade" className={className}>
      {d.lessons.length === 0 ? (
        <Empty>Nessun trade chiuso su {d.ticker}: la prima lezione arriva all'uscita dalla prima posizione.</Empty>
      ) : (
        <ol className="space-y-3">
          {d.lessons.map((l, i) => {
            const e = l.exit_reason ? (EXIT[l.exit_reason] ?? { label: l.exit_reason, tone: "flat" as const }) : null;
            return (
              <Signed key={`${l.ts}-${i}`} by={null} as="li">
                <p className="text-[13px] leading-5 text-fg">{l.text}</p>
                <p className="mt-1 flex items-center gap-2 text-2xs text-fg-subtle">
                  {e && <span className={cn("rounded-tag px-1 leading-4", e.tone === "up" ? "bg-up-soft text-up" : e.tone === "down" ? "bg-down-soft text-down" : "bg-hover text-fg-muted")}>Uscita: {e.label}</span>}
                  <time className="num" dateTime={l.ts}>
                    {fmtDate(l.ts, now)}
                  </time>
                </p>
              </Signed>
            );
          })}
        </ol>
      )}
    </DossierTile>
  );
}

// ——— Note di Luca ———

export function NotesTile({ d, className }: { d: Dossier; className?: string }) {
  const now = useNow(60_000);
  const { writable } = useShell();
  const [text, setText] = useState("");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const add = useCommand("add_dossier_note", { invalidate: [["dossier"], ["dossier_history"]], toastRefusal: false });
  const notes = [...d.notes].sort((a, b) => (parseTs(a.ts) ?? 0) - (parseTs(b.ts) ?? 0));
  const canSend = writable && text.trim().length > 0 && !add.isPending;

  const send = () => {
    if (!canSend) return;
    setRefusal(null);
    add.mutate(
      { ticker: d.ticker, text: text.trim() },
      {
        onSuccess: () => {
          setText("");
          toast.success(`Nota firmata nella scheda di ${d.ticker}`, { description: "Gli agenti la leggono al prossimo ciclo." });
        },
        onError: (err) => {
          if (err instanceof CommandRefused) setRefusal(err.reasons.length ? err.reasons : ["Nessuna ragione indicata"]);
        },
      },
    );
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <DossierTile id="note" title="Note di Luca" className={className} meta={<span className="text-2xs text-fg-subtle">lette dagli agenti come il parere di un collega senior</span>}>
      {notes.length === 0 ? (
        <Empty>Nessuna nota. Quello che scrivi qui entra nella scheda firmato da te; gli agenti possono non essere d'accordo e dire perché.</Empty>
      ) : (
        <ol className="space-y-2">
          {notes.map((n) => {
            const a = author(n.author);
            return (
              <Signed key={n.id} by={n.author} as="li" className="row-arrive rounded-control bg-[oklch(0.82_0.135_72/0.07)] px-3 py-2.5">
                <p className="flex items-center gap-2 text-2xs text-fg-subtle">
                  <SignatureChip by={n.author} size="xs" />
                  <span className="font-medium text-fg">{a.name}</span>
                  {a.kind === "human" && a.channel && <span>via {a.channel}</span>}
                  <time className="num ml-auto" dateTime={n.ts} title={fmtDateTime(n.ts)}>
                    {fmtWhen(n.ts, now)}
                  </time>
                </p>
                <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-5 text-fg">{n.text}</p>
              </Signed>
            );
          })}
        </ol>
      )}

      <div className="mt-3 rounded-control bg-raised p-1.5 shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)] focus-within:shadow-[inset_0_0_0_1px_var(--accent-c)]">
        <label className="sr-only" htmlFor="dossier-note">
          Nota per la scheda di {d.ticker}
        </label>
        <Textarea
          id="dossier-note"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          disabled={!writable}
          placeholder={writable ? `Il tuo parere su ${d.ticker}…` : "Runtime irraggiungibile: le note sono sospese"}
          className="block max-h-40 min-h-12 w-full resize-none border-none bg-transparent px-2 py-1.5 text-[13px] leading-5 text-fg shadow-none outline-none focus-visible:ring-0 placeholder:text-fg-subtle disabled:opacity-60"
        />
        <div className="flex items-center gap-2 px-1 pt-1">
          <AuthorChip author={LUCA} size="xs" />
          <span className="text-2xs text-fg-subtle">Firmata da te</span>
          <span className="ml-auto hidden text-2xs text-fg-subtle sm:inline">
            <kbd className="rounded-tag bg-hover px-1 font-sans">Invio</kbd> firma · <kbd className="rounded-tag bg-hover px-1 font-sans">Maiusc Invio</kbd> a capo
          </span>
          <Button size="xs" onClick={send} disabled={!canSend} aria-label="Firma e aggiungi la nota">
            <ArrowUp /> Firma
          </Button>
        </div>
      </div>
      {refusal && (
        <div role="alert" className="mt-2 rounded-item bg-warn-soft px-2.5 py-2 text-xs leading-4">
          <p className="font-medium text-fg">Il Runtime ha rifiutato la nota</p>
          <ul className="mt-0.5 text-fg-muted">
            {refusal.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </DossierTile>
  );
}

// ——— Versioni ———

export function VersionsTile({ d, history, className }: { d: Dossier; history: Read<DossierVersion[]> | undefined; className?: string }) {
  const now = useNow(60_000);
  const rows = history?.state === "ok" ? history.data : [];
  return (
    <DossierTile id="versioni" title="Versioni" className={className} meta={<span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">v{d.version}</span>}>
      {!history ? (
        <div className="space-y-2" aria-busy aria-label="Caricamento delle versioni">
          {[0, 1, 2].map((i) => (
            <span key={i} className="block h-3 w-3/4 animate-pulse rounded-tag bg-hover" />
          ))}
        </div>
      ) : history.state === "unavailable" ? (
        <Empty>Lo storico comparirà quando il Runtime esporrà {history.endpoint}.</Empty>
      ) : rows.length === 0 ? (
        <Empty>Nessuna versione precedente.</Empty>
      ) : (
        <ol className="-mx-1.5 space-y-px">
          {rows.map((v) => (
            <Signed key={v.version} by={v.author} as="li" className={cn("flex min-h-8 items-center gap-2.5 rounded-item px-1.5 py-1", v.version === d.version && "bg-selected")}>
              <span className="num w-8 shrink-0 text-xs font-medium text-fg">v{v.version}</span>
              <SignatureChip by={v.author} size="xs" />
              <span className="min-w-0 flex-1 truncate text-xs text-fg-muted">
                <span className="text-fg">{author(v.author).short}</span> · {v.sections_changed.map(sectionLabel).join(", ") || "—"}
              </span>
              <time className="num shrink-0 text-2xs text-fg-subtle" dateTime={v.ts} title={fmtDateTime(v.ts)}>
                {fmtWhen(v.ts, now)}
              </time>
            </Signed>
          ))}
        </ol>
      )}
    </DossierTile>
  );
}
