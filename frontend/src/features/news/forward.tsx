import { Forward, Newspaper, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { COCKPIT_TOPIC } from "@/features/office/api";
import { useOfficeAgents } from "@/features/office/hooks";
import { AGENT_IDS, author, tickerAgentId } from "@/lib/authors";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { useNewsItem } from "./hooks";
import { fmtFull, providerLabel } from "./labels";
import type { ForwardTarget, NewsItem } from "./types";

/**
 * Where a forward opens: the recipient's chat in the Ufficio, with the item attached to the composer.
 * A ticker goes to its `ticker:<SYM>` agent; without one, to the PM in the ticker's topic (contract).
 */
export function forwardHref(newsId: number, target: ForwardTarget, tickerAgentExists: boolean): string {
  if ("ticker" in target) {
    const sym = target.ticker.toUpperCase();
    const agent = tickerAgentExists ? tickerAgentId(sym) : "portfolio_manager";
    return `/ufficio/${agent}?chat=${encodeURIComponent(sym)}&news=${newsId}&fwd=${encodeURIComponent(sym)}`;
  }
  return `/ufficio/${target.agent}?chat=${COCKPIT_TOPIC}&news=${newsId}`;
}

/** The forward target a composer URL carries: `fwd=<SYM>` is a ticker forward, otherwise the chat's agent. */
export function targetFromUrl(agent: string, fwd: string | null): ForwardTarget {
  return fwd ? { ticker: fwd.toUpperCase() } : { agent };
}

function useTickerAgents(): { known: boolean; has: (sym: string) => boolean } {
  const q = useOfficeAgents();
  const list = q.data && q.data.source === "runtime" ? q.data.data : null;
  return { known: !!list, has: (sym) => !!list?.some((a) => a.name === tickerAgentId(sym)) };
}

/** Inoltra: pick the colleague, then write the note in their chat with the item attached. */
export function ForwardMenu({ item, className }: { item: NewsItem; className?: string }) {
  const navigate = useNavigate();
  const { writable } = useShell();
  const [open, setOpen] = useState(false);
  const agents = useTickerAgents();
  const go = (t: ForwardTarget, exists = true) => {
    setOpen(false);
    navigate(forwardHref(item.id, t, exists));
  };

  const button = (
    <Button size="sm" disabled={!writable} className={cn("gap-1.5", className)} data-action="forward">
      <Forward className="size-3.5" /> Inoltra
    </Button>
  );
  if (!writable)
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>{button}</span>
        </TooltipTrigger>
        <TooltipContent>Runtime irraggiungibile: inoltro sospeso</TooltipContent>
      </Tooltip>
    );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{button}</PopoverTrigger>
      <PopoverContent align="start" className="w-[min(300px,calc(100vw-16px))] p-1.5">
        <p className="px-2 pb-1.5 pt-1 text-2xs text-fg-subtle">Inoltra a… si apre la sua chat con la notizia allegata: scrivi lì il tuo parere.</p>
        {item.tickers.length > 0 && (
          <div role="group" aria-label="Agenti del ticker">
            <p className="px-2 pb-1 pt-1.5 text-2xs font-medium text-fg-subtle">Agenti del ticker</p>
            {item.tickers.slice(0, 6).map((sym) => {
              const exists = !agents.known || agents.has(sym);
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => go({ ticker: sym }, exists)}
                  className="flex h-9 w-full items-center gap-2.5 rounded-item px-2 text-left text-[13px] text-fg outline-none transition-colors hover:bg-hover focus-visible:bg-hover"
                >
                  <AuthorChip actor={exists ? tickerAgentId(sym) : "portfolio_manager"} size="xs" tooltip={exists ? `Agente ${sym}` : "Portfolio Manager"} />
                  <span className="min-w-0 flex-1 truncate">{exists ? `Agente ${sym}` : `${sym} · al PM`}</span>
                  {!exists && <span className="shrink-0 text-2xs text-fg-subtle">nessun agente {sym}</span>}
                </button>
              );
            })}
          </div>
        )}
        <div role="group" aria-label="Ufficio">
          <p className="px-2 pb-1 pt-1.5 text-2xs font-medium text-fg-subtle">Ufficio</p>
          {AGENT_IDS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => go({ agent: id })}
              className="flex h-9 w-full items-center gap-2.5 rounded-item px-2 text-left text-[13px] text-fg outline-none transition-colors hover:bg-hover focus-visible:bg-hover"
            >
              <AuthorChip actor={id} size="xs" />
              <span className="min-w-0 flex-1 truncate">{author(id).name}</span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** The item riding on the composer: what the recipient will receive above Luca's note. */
export function NewsAttachment({ newsId, onRemove }: { newsId: number; onRemove: () => void }) {
  const q = useNewsItem(newsId);
  const n = q.data?.state === "ok" ? q.data.data : null;
  return (
    <div data-part="news-attachment" className="row-arrive mx-2 mt-2 flex items-start gap-2.5 rounded-item bg-[oklch(0_0_0/0.25)] px-2.5 py-2">
      <Newspaper className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
      <div className="min-w-0 flex-1">
        {q.isPending ? (
          <span className="block h-3 w-3/4 animate-pulse rounded-tag bg-hover" />
        ) : n ? (
          <>
            <p className="line-clamp-2 text-[13px] font-medium leading-[1.15rem] text-fg">{n.headline}</p>
            <p className="mt-0.5 truncate text-2xs text-fg-subtle">
              {n.source} · {providerLabel(n.provider)} · <span className="num">{fmtFull(n.published_ts)}</span>
              {n.tickers.length > 0 && <> · {n.tickers.slice(0, 4).join(" ")}</>}
            </p>
          </>
        ) : (
          <p className="text-xs text-fg-muted">
            Notizia n. <span className="num">{newsId}</span>
            {q.data?.state === "unavailable" ? ` · dettaglio in attesa di ${q.data.endpoint}` : q.data?.state === "missing" ? " · non più nell'archivio" : ""}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Togli la notizia allegata"
        className="grid size-6 shrink-0 place-items-center rounded-item text-fg-subtle outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
