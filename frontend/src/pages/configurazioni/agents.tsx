import { ArrowUpRight, ChevronRight, Expand } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { useAgentConfigs, useSettings } from "@/features/settings/hooks";
import type { AgentConfig, SettingItem } from "@/features/settings/types";
import { fmtDateTime } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { LimitBar, statusFor } from "@/pages/portafoglio/parts";
import { SettingsHistory, SettingsPanels, SettingsRows } from "./draft";
import { agentAuthor, Bones, optionWord, Panel, Unavailable } from "./parts";
import { since } from "./parts";
import { PromptEditor, PromptVersions } from "./prompt";
import { agentOfKey } from "./sections";

const usd = (v: number | null) => (v === null ? "—" : `$${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}`);

/** Today's spend against the agent's daily budget, on the Portafoglio threshold tick. */
function BudgetBar({ a }: { a: AgentConfig }) {
  if (a.today_cost === null || a.daily_budget_usd === null || a.daily_budget_usd <= 0) return <span className="block h-1.5" />;
  const scale = Math.max(a.daily_budget_usd * 1.15, a.today_cost * 1.05);
  return <LimitBar value={a.today_cost} limit={a.daily_budget_usd} scale={scale} status={statusFor(a.today_cost, a.daily_budget_usd)} height={4} label={`${usd(a.today_cost)} spesi su ${usd(a.daily_budget_usd)}`} />;
}

const officeHref = (agent: string) => (agent === "ticker_agent" ? "/ufficio" : `/ufficio/${agent}`);

function AgentsTable({ agents, selected, mobile }: { agents: AgentConfig[]; selected: string | null; mobile: boolean }) {
  const navigate = useNavigate();
  const now = useNow(60_000);
  const open = (a: string) => navigate(`/configurazioni/agenti/${a}`);
  if (mobile) {
    return (
      <ul className="space-y-px px-1.5 pb-2">
        {agents.map((a) => {
          const au = agentAuthor(a.agent);
          return (
            <li key={a.agent}>
              <Link to={`/configurazioni/agenti/${a.agent}`} className="flex items-center gap-3 rounded-item px-2.5 py-2.5 active:bg-hover">
                <AuthorChip author={au} size="md" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-fg">{au.name}</span>
                  <span className="num block truncate text-2xs text-fg-subtle">
                    {a.model ?? "modello n/d"} · {a.effort ? optionWord(a.effort) : "—"} · prompt v{a.prompt_version ?? "—"}
                  </span>
                  <span className="mt-1.5 flex items-center gap-2">
                    <span className="w-24"><BudgetBar a={a} /></span>
                    <span className="num text-2xs text-fg-subtle">{usd(a.today_cost)} / {usd(a.daily_budget_usd)}</span>
                  </span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
              </Link>
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <div className="overflow-x-auto pb-2">
      <table className="w-full min-w-[780px] border-separate border-spacing-0 px-1.5">
        <thead>
          <tr className="text-2xs text-fg-subtle">
            <th scope="col" className="h-8 px-2.5 text-left font-medium">Agente</th>
            <th scope="col" className="h-8 px-2.5 text-left font-medium">Modello</th>
            <th scope="col" className="h-8 px-2.5 text-left font-medium">Effort</th>
            <th scope="col" className="h-8 px-2.5 text-right font-medium">Oggi / budget</th>
            <th scope="col" className="h-8 w-[16%] px-2.5 text-left font-medium"><span className="sr-only">Spesa sul budget</span></th>
            <th scope="col" className="h-8 px-2.5 text-left font-medium">Prompt</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => {
            const au = agentAuthor(a.agent);
            const sel = a.agent === selected;
            return (
              <tr
                key={a.agent}
                aria-selected={sel}
                onClick={() => open(a.agent)}
                className={cn("cursor-pointer [&>td]:transition-colors", sel ? "[&>td]:bg-selected" : "hover:[&>td]:bg-hover")}
              >
                <td className="h-11 rounded-l-item px-2.5">
                  <Link to={`/configurazioni/agenti/${a.agent}`} onClick={(e) => e.stopPropagation()} className="flex items-center gap-2.5 outline-none focus-visible:underline">
                    <AuthorChip author={au} size="sm" />
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium text-fg">{au.name}</span>
                      {a.role && <span className="block max-w-[260px] truncate text-2xs text-fg-subtle">{a.role}</span>}
                    </span>
                  </Link>
                </td>
                <td className="h-11 px-2.5 font-mono text-[11.5px] text-fg-muted">{a.model ?? "—"}</td>
                <td className="h-11 px-2.5 text-xs text-fg-muted">{a.effort ? optionWord(a.effort) : "—"}</td>
                <td className="num h-11 whitespace-nowrap px-2.5 text-right text-xs">
                  <Link to={officeHref(a.agent)} onClick={(e) => e.stopPropagation()} className="text-fg hover:underline" title="Costi e token nell'Ufficio">
                    {usd(a.today_cost)}
                  </Link>
                  <span className="text-fg-subtle"> / {usd(a.daily_budget_usd)}</span>
                </td>
                <td className="h-11 px-2.5"><BudgetBar a={a} /></td>
                <td className="num h-11 rounded-r-item whitespace-nowrap px-2.5 text-xs text-fg-muted">
                  v{a.prompt_version ?? "—"}
                  {a.prompt_updated_ts && <span className="text-2xs text-fg-subtle" title={fmtDateTime(a.prompt_updated_ts)}> · {since(a.prompt_updated_ts, now)}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const FIELD_ORDER = ["model", "effort", "daily_budget_usd", "endpoint"];

function AgentDetail({ agent, config, items, pending, mobile }: { agent: string; config: AgentConfig | null; items: SettingItem[]; pending: string[]; mobile: boolean }) {
  const au = agentAuthor(agent);
  const navigate = useNavigate();
  const [full, setFull] = useState(false);
  const mine = items.filter((i) => agentOfKey(i.key) === agent).sort((a, b) => FIELD_ORDER.indexOf(a.key.split(".")[2]) - FIELD_ORDER.indexOf(b.key.split(".")[2]));

  if (mobile && full) {
    // Phone: the editor takes the whole screen; the shell's bottom nav stays.
    return (
      <section aria-label={`Prompt di ${au.name}`} className="flex min-h-[calc(100dvh-140px)] flex-col rounded-tile bg-ground">
        <header className="flex h-11 items-center gap-2 pl-4 pr-2">
          <AuthorChip author={au} size="xs" />
          <h2 className="text-[13px] font-semibold text-fg">Prompt di {au.short}</h2>
        </header>
        <PromptEditor agent={agent} name={au.name} fullscreen onExitFullscreen={() => setFull(false)} />
      </section>
    );
  }

  return (
    <>
      <Panel
        title={
          <span className="flex items-center gap-2.5">
            <AuthorChip author={au} size="md" />
            <span>
              <span className="block">{au.name}</span>
              {config?.role && <span className="block text-2xs font-normal text-fg-subtle">{config.role}</span>}
            </span>
          </span>
        }
        aria-label={`Configurazione di ${au.name}`}
        end={
          <Button size="sm" variant="ghost" onClick={() => navigate(officeHref(agent))}>
            Costi e chat nell'Ufficio <ArrowUpRight />
          </Button>
        }
      >
        {mine.length ? (
          <SettingsRows items={mine} pending={pending} />
        ) : (
          <p className="px-4 pb-3 text-xs text-fg-subtle">Nessuna impostazione esposta per questo agente.</p>
        )}
        {config && (
          <p className="num px-4 pb-3 text-2xs text-fg-subtle">
            Oggi {usd(config.today_cost)} su {usd(config.daily_budget_usd)} di budget{config.endpoint ? <> · <span className="font-mono">{config.endpoint}</span></> : null}
          </p>
        )}
      </Panel>
      <Panel
        title="Prompt"
        meta={agent === "ticker_agent" ? "uno solo per tutti gli agenti del ticker" : undefined}
        end={
          mobile ? (
            <Button size="sm" variant="ghost" onClick={() => setFull(true)}>
              <Expand /> Schermo intero
            </Button>
          ) : undefined
        }
      >
        <PromptEditor agent={agent} name={au.name} />
      </Panel>
      <PromptVersions agent={agent} current={config?.prompt_version ?? null} />
    </>
  );
}

export function AgentsSection({ agent, mobile }: { agent: string | null; mobile: boolean }) {
  const agents = useAgentConfigs();
  const settings = useSettings();
  const list = agents.data?.source === "runtime" ? agents.data.data : null;
  const s = settings.data?.source === "runtime" ? settings.data.data : null;
  const items = s?.sections.flatMap((g) => g.items) ?? [];
  // Desktop opens on the first agent; the phone shows the list until one is picked.
  const selected = agent ?? (mobile ? null : list?.[0]?.agent ?? null);
  const config = list?.find((a) => a.agent === selected) ?? null;

  if (mobile && selected) {
    return <AgentDetail key={selected} agent={selected} config={config} items={items} pending={s?.pending_restart ?? []} mobile />;
  }

  const spent = list?.reduce((t, a) => t + (a.today_cost ?? 0), 0) ?? null;
  return (
    <>
      <Panel title="Agenti" meta={list ? `${list.length} · oggi ${usd(spent)}` : undefined}>
        {agents.isPending ? (
          <Bones rows={5} className="px-4 pb-4" />
        ) : agents.error ? (
          <p role="alert" className="px-4 pb-4 text-xs text-down">Agenti non disponibili: {agents.error.message}</p>
        ) : !list ? (
          <Unavailable className="mx-4 mb-4">{agents.data?.source === "unavailable" ? agents.data.note : null}</Unavailable>
        ) : (
          <AgentsTable agents={list} selected={selected} mobile={mobile} />
        )}
      </Panel>
      {selected && !mobile && <AgentDetail key={selected} agent={selected} config={config} items={items} pending={s?.pending_restart ?? []} mobile={false} />}
      {!list && agents.data?.source === "unavailable" && s && (
        // Without agent_configs, the agents' settings still show from /v1/read/settings.
        <SettingsPanels section="agenti" q={settings} exclude={(k) => k.startsWith("budgets.")} />
      )}
      <SettingsPanels section="agenti" q={settings} exclude={(k) => k.startsWith("agents.")} />
      <SettingsHistory section="agenti" />
    </>
  );
}

