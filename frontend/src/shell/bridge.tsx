import { Check, ChevronDown, Maximize2, SquarePen, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AuthorChip } from "@/components/author-chip";
import { IconButton } from "@/components/tile";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { BridgeComposer } from "@/features/bridge/composer";
import { FallbackThread } from "@/features/bridge/fallback";
import { useConversation, useConversations } from "@/features/bridge/hooks";
import { useBridge, useOpenInAssistente } from "@/features/bridge/state";
import { Thread, turnOf } from "@/features/bridge/thread";
import { BRIDGE } from "@/lib/authors";
import { fmtWhen } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useShell } from "./shell-state";

/** Pick another conversation, start a new one, or open the current one full size in the Assistente. */
function ConversationSwitcher() {
  const { currentId, select, live } = useBridge();
  const list = useConversations();
  const current = useConversation(currentId);
  const rows = list.data?.state === "ok" ? list.data.data.slice(0, 8) : [];
  const title = currentId === null ? "Nuova conversazione" : current.data?.state === "ok" ? current.data.data.title || "Conversazione" : "…";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="group inline-flex h-7 min-w-0 items-center gap-1 rounded-control px-1.5 text-left transition-colors hover:bg-hover" aria-label="Cambia conversazione">
        <span className="min-w-0 truncate text-[13px] font-semibold text-fg">{title}</span>
        <ChevronDown className="size-3.5 shrink-0 text-fg-subtle" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuItem onSelect={() => select(null)} className="gap-2">
          <SquarePen className="size-3.5" /> Nuova conversazione
        </DropdownMenuItem>
        {rows.length > 0 && <DropdownMenuSeparator />}
        {rows.length > 0 && <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">Recenti</DropdownMenuLabel>}
        {rows.map((c) => {
          const turn = turnOf(c.id, live, c.status);
          return (
            <DropdownMenuItem key={c.id} onSelect={() => select(c.id)} className="gap-2">
              <Check className={cn("size-3.5 shrink-0", c.id === currentId ? "opacity-100" : "opacity-0")} />
              <span className="min-w-0 flex-1 truncate">{c.title || "Senza titolo"}</span>
              {turn && <span className="agent-working size-1.5 shrink-0 rounded-full bg-[var(--author-bridge)]" aria-label="Turno in corso" />}
              {c.pending_actions > 0 && <span className="num shrink-0 rounded-tag bg-warn-soft px-1 text-[10px] leading-4 text-warn">{c.pending_actions}</span>}
              <span className="num shrink-0 text-2xs text-fg-subtle">{fmtWhen(c.updated_ts)}</span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

let consumedSeed = 0;

/**
 * The mini Bridge on every page: the same conversation as the Assistente, with the open page's context
 * (ticker, position, agent) attached to what Luca sends.
 */
export function BridgePanel({ onClose, className }: { onClose?: () => void; className?: string }) {
  const { composerSeed } = useShell();
  const bridge = useBridge();
  const { currentId, availability, pageContext, live, contextLabel, seedComposer } = bridge;
  const openFull = useOpenInAssistente();
  const conv = useConversation(currentId);
  const turn = turnOf(currentId, live, conv.data?.state === "ok" ? conv.data.data.status : undefined);
  const label = contextLabel(pageContext);
  const [dropped, setDropped] = useState<string | null>(null);
  const seedRef = useRef(seedComposer);
  seedRef.current = seedComposer;

  // "Scrivi a un agente" elsewhere in the shell lands here as "@agent …" in the composer.
  useEffect(() => {
    if (!composerSeed || composerSeed.nonce === consumedSeed) return;
    consumedSeed = composerSeed.nonce;
    seedRef.current(composerSeed.text);
  }, [composerSeed]);

  // A context Luca removed stays removed until the page's context changes.
  const context = label && dropped !== label ? pageContext : null;

  return (
    <aside data-region="bridge-panel" aria-label="Bridge" className={cn("flex h-full min-h-0 flex-col bg-ground", className)}>
      <div className="flex h-11 shrink-0 items-center gap-1.5 pl-3 pr-2">
        <AuthorChip author={BRIDGE} size="sm" tooltip="Bridge: legge tutto l'ufficio e propone, tu confermi" />
        {availability === "unavailable" ? <h2 className="pl-1 text-[13px] font-semibold text-fg">Bridge</h2> : <ConversationSwitcher />}
        <div className="ml-auto flex items-center gap-0.5">
          {availability !== "unavailable" && <IconButton icon={Maximize2} label="Apri nell'Assistente" onClick={() => openFull(currentId)} />}
          {onClose && <IconButton icon={X} label="Chiudi il Bridge" onClick={onClose} />}
        </div>
      </div>
      {availability === "unavailable" ? (
        <FallbackThread compact />
      ) : (
        <Thread
          key={currentId ?? "new"}
          conversationId={currentId}
          compact
          empty={
            <div className="px-4 py-6 text-xs leading-relaxed text-fg-muted">
              <p className="text-sm text-fg">Chiedi al Bridge quello che ti serve su questa pagina.</p>
              <p className="mt-1.5">
                {label ? `Il messaggio porta con sé il contesto «${label}». ` : ""}Con <span className="text-fg">@agente</span> gli chiedi di scrivere a un agente; le azioni sul capitale le propone e le confermi tu.
              </p>
            </div>
          }
        />
      )}
      <BridgeComposer conversationId={currentId} context={context} onDropContext={() => setDropped(label)} turnActive={!!turn} compact />
    </aside>
  );
}
