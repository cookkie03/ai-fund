import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, Navigate, NavLink, useParams } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { useAgentConfigs, useRuntimeHealth, useSecrets, useSettings } from "@/features/settings/hooks";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { AgentsSection } from "./agents";
import { DataSection, dbState, HealthSection } from "./data";
import { DraftBar, DraftProvider, PendingRestartBanner, ReviewSheet, SettingsHistory, SettingsPanels, useDraftCounts } from "./draft";
import { agentAuthor } from "./parts";
import { since } from "./parts";
import { SecretsSection } from "./secrets";
import { ELSEWHERE, isSection, SECTIONS, sectionOfKey, type SectionId } from "./sections";

type Hint = { text: string; tone?: "warn" | "down" };

/** One line of state per section for the index: what needs a look, in words. */
function useHints(): Partial<Record<SectionId, Hint>> {
  const settings = useSettings();
  const agents = useAgentConfigs();
  const secrets = useSecrets();
  const health = useRuntimeHealth();
  const out: Partial<Record<SectionId, Hint>> = {};
  const s = settings.data?.source === "runtime" ? settings.data.data : null;
  const pending = (s?.pending_restart ?? []).map(sectionOfKey);
  const pendingIn = (id: SectionId) => pending.filter((p) => p === id).length;

  const a = agents.data?.source === "runtime" ? agents.data.data : null;
  const over = a?.filter((x) => x.today_cost !== null && x.daily_budget_usd !== null && x.today_cost > x.daily_budget_usd).length ?? 0;
  if (over) out.agenti = { text: `${over} oltre il budget`, tone: "down" };
  else if (pendingIn("agenti")) out.agenti = { text: `${pendingIn("agenti")} in attesa di riavvio`, tone: "warn" };
  else if (a) out.agenti = { text: `${a.length} agenti` };

  const k = secrets.data?.source === "runtime" ? secrets.data.data : null;
  if (k) {
    const missing = k.filter((x) => !x.set).length;
    const failed = k.filter((x) => x.test && !x.test.ok).length;
    out.chiavi = failed ? { text: `${failed} prova fallita${missing ? ` · ${missing} mancante` : ""}`, tone: "down" } : missing ? { text: `${missing} ${missing === 1 ? "mancante" : "mancanti"}`, tone: "warn" } : { text: "Tutte impostate" };
  }

  if (pendingIn("mercato")) out.mercato = { text: `${pendingIn("mercato")} in attesa di riavvio`, tone: "warn" };

  const h = health.data?.source === "runtime" ? health.data.data : null;
  const d = dbState(h);
  if (d?.status === "breach") out.dati = { text: "Database oltre la soglia", tone: "down" };
  else if (d?.status === "near") out.dati = { text: "Database vicino alla soglia", tone: "warn" };
  else if (pendingIn("dati")) out.dati = { text: `${pendingIn("dati")} in attesa di riavvio`, tone: "warn" };

  if (h) {
    const errs = h.jobs.filter((j) => j.last_status === "error").length;
    out.salute = errs ? { text: `${errs} job in errore`, tone: "down" } : !h.broker.ok || !h.llm.ok ? { text: !h.broker.ok ? "Broker non raggiungibile" : "Provider LLM non raggiungibile", tone: "down" } : { text: "Tutto regolare" };
  }
  return out;
}

function SectionIndex({ active, mobile }: { active: SectionId | null; mobile: boolean }) {
  const hints = useHints();
  const drafts = useDraftCounts();
  return (
    <nav aria-label="Sezioni di Configurazioni" className={cn("rounded-tile bg-ground p-1.5", !mobile && "sticky top-0")}>
      <ul className="space-y-px">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const hint = hints[s.id];
          const n = drafts[s.id];
          return (
            <li key={s.id}>
              <NavLink
                to={`/configurazioni/${s.id}`}
                aria-current={active === s.id ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-2.5 rounded-item px-2.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60",
                  mobile ? "py-3" : "py-2",
                  active === s.id ? "bg-selected shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]" : "hover:bg-hover",
                )}
              >
                <Icon className={cn("size-4 shrink-0", active === s.id ? "text-fg" : "text-fg-subtle group-hover:text-fg-muted")} strokeWidth={1.75} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className={cn("block truncate text-[13px]", active === s.id ? "font-medium text-fg" : "text-fg-muted group-hover:text-fg")}>{s.label}</span>
                  {hint && <span className={cn("num block truncate text-2xs", hint.tone === "down" ? "text-down" : hint.tone === "warn" ? "text-warn" : "text-fg-subtle")}>{hint.text}</span>}
                </span>
                {n ? (
                  <span className="num rounded-tag bg-accent-soft px-1 text-[10px] leading-4 text-accent-c" title={`${n} ${n === 1 ? "modifica" : "modifiche"} in bozza`}>
                    {n}
                  </span>
                ) : null}
                {mobile && <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />}
              </NavLink>
            </li>
          );
        })}
      </ul>
      <p className="px-2.5 pb-1 pt-4 text-2xs font-medium text-fg-subtle">Altrove</p>
      <ul className="space-y-px">
        {ELSEWHERE.map((e) => {
          const Icon = e.icon;
          return (
            <li key={e.label}>
              <Link to={e.to} className={cn("group flex items-center gap-2.5 rounded-item px-2.5 outline-none transition-colors hover:bg-hover focus-visible:ring-2 focus-visible:ring-ring/60", mobile ? "py-3" : "py-2")}>
                <Icon className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-fg-muted group-hover:text-fg">{e.label}</span>
                  <span className="block truncate text-2xs text-fg-subtle">in {e.page}</span>
                </span>
                <ArrowUpRight className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function SectionBody({ id, agent, mobile }: { id: SectionId; agent: string | null; mobile: boolean }) {
  const settings = useSettings();
  switch (id) {
    case "agenti":
      return <AgentsSection agent={agent} mobile={mobile} />;
    case "chiavi":
      return <SecretsSection />;
    case "mercato":
      return (
        <>
          <SettingsPanels section="mercato" q={settings} />
          <SettingsHistory section="mercato" />
        </>
      );
    case "dati":
      return <DataSection />;
    case "salute":
      return <HealthSection mobile={mobile} />;
  }
}

function Header({ children }: { children?: ReactNode }) {
  const settings = useSettings();
  const { health } = useRuntime();
  const now = useNow(60_000);
  const s = settings.data?.source === "runtime" ? settings.data.data : null;
  return (
    <div className="flex shrink-0 flex-wrap items-end gap-x-4 gap-y-1 px-2 pb-3 pt-1 md:px-1">
      <div className="min-w-0">
        {children ?? <h1 className="text-base font-semibold tracking-[-0.01em] text-fg">Configurazioni</h1>}
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-fg-subtle">
          {s ? (
            <span className="inline-flex items-center gap-1.5">
              Impostazioni versione <span className="num text-fg-muted">{s.version}</span>
              {s.updated_ts && (
                <>
                  · {s.updated_by && <AuthorChip actor={s.updated_by} size="xs" />} <span className="num">{since(s.updated_ts, now)}</span>
                </>
              )}
            </span>
          ) : (
            <span>Come lavora l'ufficio: agenti, chiavi, orari, archivio e salute del Runtime.</span>
          )}
          {health?.account_label && (
            <span>
              Conto <span className="text-fg-muted">{health.account_label}</span>
            </span>
          )}
          {import.meta.env.VITE_SETTINGS_FIXTURES === "1" && (
            <span data-sample className="rounded-tag bg-warn-soft px-1.5 py-px font-medium text-warn" title="COCKPIT_SETTINGS_FIXTURES: valori sintetici del dev server, non la configurazione del Runtime">
              Dati di esempio
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

function Page() {
  const params = useParams();
  const mobile = !useMediaQuery("(min-width: 768px)");
  const section = isSection(params.section) ? params.section : null;
  const agent = section === "agenti" ? params.agent ?? null : null;

  useEffect(() => {
    const label = SECTIONS.find((s) => s.id === section)?.label;
    document.title = label ? `${label} · Configurazioni` : "Configurazioni";
  }, [section]);

  if (params.section && !section) return <Navigate to="/configurazioni" replace />;

  if (mobile) {
    if (!section) {
      return (
        <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
          <Header />
          <PendingRestartBanner />
          <div className="mt-2.5">
            <SectionIndex active={null} mobile />
          </div>
          <DraftBar />
          <ReviewSheet />
        </div>
      );
    }
    const meta = SECTIONS.find((s) => s.id === section)!;
    const back = agent ? { to: "/configurazioni/agenti", label: "Agenti" } : { to: "/configurazioni", label: "Configurazioni" };
    return (
      <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto px-2 pb-24">
        <Header>
          <Link to={back.to} className="-ml-1 inline-flex h-7 items-center gap-0.5 rounded-item pr-2 text-xs text-fg-muted hover:text-fg">
            <ChevronLeft className="size-4" aria-hidden /> {back.label}
          </Link>
          <h1 className="mt-0.5 text-base font-semibold tracking-[-0.01em] text-fg">{agent ? agentAuthor(agent).name : meta.label}</h1>
        </Header>
        <div key={`${section}-${agent}`} className="section-in space-y-2.5">
          <PendingRestartBanner />
          <SectionBody id={section} agent={agent} mobile />
        </div>
        <DraftBar />
        <ReviewSheet />
      </div>
    );
  }

  if (!section) return <Navigate to="/configurazioni/agenti" replace />;
  const meta = SECTIONS.find((s) => s.id === section)!;

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pr-2.5">
      <Header />
      <div className="grid min-h-0 flex-1 grid-cols-[232px_minmax(0,1fr)] items-start gap-2.5">
        <SectionIndex active={section} mobile={false} />
        <div className="flex min-h-full min-w-0 max-w-[1120px] flex-col">
          <div key={section} className="section-in flex-1 space-y-2.5">
            <div className="px-1 pb-0.5">
              <h2 className="sr-only">{meta.label}</h2>
              <p className="text-xs text-fg-muted">{meta.summary}</p>
            </div>
            <PendingRestartBanner />
            <SectionBody id={section} agent={agent} mobile={false} />
          </div>
          <DraftBar />
        </div>
      </div>
      <ReviewSheet />
    </div>
  );
}

/**
 * Configurazioni read like a ledger: an index of sections on the left (and links to what lives in other pages),
 * the section on the right. Settings are edited in place as a draft, reviewed against the Runtime's dry run,
 * then confirmed with a reason; every version stays in the history.
 */
export function ConfigurazioniPage() {
  const settings = useSettings();
  const s = settings.data?.source === "runtime" ? settings.data.data : null;
  return (
    <DraftProvider settings={s}>
      <Page />
    </DraftProvider>
  );
}
