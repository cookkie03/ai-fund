import { Activity, MessagesSquare, PanelLeft, SquarePen } from "lucide-react";
import { useEffect, useState } from "react";
import { CollapsedRail } from "@/components/collapsed-rail";
import { Gutter } from "@/components/gutter";
import { IconButton } from "@/components/tile";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { BridgeComposer } from "@/features/bridge/composer";
import { ConversationList } from "@/features/bridge/conversation-list";
import { FallbackThread } from "@/features/bridge/fallback";
import { useBridgeActions, useConversation } from "@/features/bridge/hooks";
import { useBridge } from "@/features/bridge/state";
import { Thread, turnOf } from "@/features/bridge/thread";
import { fmtDateTime } from "@/lib/format";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { PANEL_LIMITS, PANEL_SHORTCUT, useShell } from "@/shell/shell-state";
import { Briefing } from "./briefing";
import { LivePanel } from "./live-panel";

/** What a new conversation teaches: what the Bridge is and the three things it does, no greeting. */
function NewConversationHint({ brief = false }: { brief?: boolean }) {
  if (brief)
    return (
      <p className="max-w-[72ch] px-5 py-4 text-xs leading-relaxed text-fg-subtle">
        Chiedi al Bridge di una voce qui sopra o di altro; con <span className="text-fg-muted">@agente</span> gira la domanda a un agente, e ciò che tocca il capitale arriva come azione da confermare.
      </p>
    );
  return (
    <div className="px-5 py-6">
      <div className="max-w-[60ch] text-xs leading-relaxed text-fg-muted">
        <p className="text-sm text-fg">Il Bridge legge tutto l'ufficio: portafoglio, schede, chat degli agenti, ordini e costi.</p>
        <ul className="mt-2 space-y-1">
          <li>Chiedigli cosa è successo, o perché un agente ha deciso qualcosa: risponde citando le fonti.</li>
          <li>
            Con <span className="text-fg">@agente</span> gli chiedi di scrivere a quell'agente; la risposta torna in questa conversazione.
          </li>
          <li>Ciò che tocca il capitale lo propone come azione: la esegui tu con Conferma, e il Runtime ricontrolla Risk Gate e Halt.</li>
        </ul>
      </div>
    </div>
  );
}

function useTitle() {
  const { currentId } = useBridge();
  const q = useConversation(currentId);
  const conv = q.data?.state === "ok" ? q.data.data : null;
  return { conv, title: currentId === null ? "Nuova conversazione" : conv?.title || (q.isPending ? "" : "Conversazione") };
}

/** Centre tile: header, briefing (full on a new conversation, one row otherwise), thread, composer. */
function ConversationTile({ phone, onOpenList, onOpenLive, listHidden }: { phone: boolean; onOpenList?: () => void; onOpenLive?: () => void; listHidden?: boolean }) {
  const { currentId, select, availability, live } = useBridge();
  const { conv, title } = useTitle();
  const pending = useBridgeActions("pending");
  const pendingCount = pending.data?.state === "ok" ? pending.data.data.length : 0;
  const turn = turnOf(currentId, live, conv?.status);
  const fallback = availability === "unavailable";

  return (
    <section aria-label="Conversazione con il Bridge" data-region="conversation" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-tile bg-ground">
      <header className="flex h-11 shrink-0 items-center gap-1.5 pl-2 pr-2">
        {phone ? (
          <IconButton icon={PanelLeft} label="Conversazioni" onClick={() => onOpenList?.()} />
        ) : (
          listHidden && <IconButton icon={SquarePen} label="Nuova conversazione" onClick={() => select(null)} />
        )}
        <div className="flex min-w-0 flex-1 items-baseline gap-2 pl-2">
          <h1 className="min-w-0 truncate text-[13px] font-semibold tracking-[-0.005em] text-fg">{fallback ? "Assistente" : title}</h1>
          {conv && !phone && <span className="num shrink-0 text-2xs text-fg-subtle">iniziata {fmtDateTime(conv.created_ts)}</span>}
        </div>
        {import.meta.env.VITE_ASSISTANT_FIXTURES === "1" && (
          <span data-sample className="shrink-0 rounded-tag bg-warn-soft px-1.5 py-px text-2xs font-medium text-warn" title="COCKPIT_ASSISTANT_FIXTURES: conversazioni e briefing sintetici del dev server">
            Dati di esempio
          </span>
        )}
        {phone && (
          <>
            {!fallback && <IconButton icon={SquarePen} label="Nuova conversazione" onClick={() => select(null)} />}
            <span className="relative">
              <IconButton icon={Activity} label="Stato vivo" onClick={() => onOpenLive?.()} />
              {pendingCount > 0 && (
                <span className="num pointer-events-none absolute -right-0.5 -top-0.5 grid h-3.5 min-w-3.5 place-items-center rounded-tag bg-warn px-0.5 text-[9px] font-semibold leading-none text-ground">
                  {pendingCount}
                </span>
              )}
            </span>
          </>
        )}
      </header>
      {fallback ? (
        <FallbackThread compact={phone} />
      ) : (
        <>
          {(currentId !== null || phone) && <Briefing mode="compact" />}
          <Thread
            key={currentId ?? "new"}
            conversationId={currentId}
            lead={currentId === null && !phone ? <Briefing mode="full" /> : undefined}
            empty={<NewConversationHint brief={currentId === null && !phone} />}
          />
        </>
      )}
      <BridgeComposer conversationId={currentId} context={null} turnActive={!!turn} compact={phone} autoFocus={!phone} />
    </section>
  );
}

function DesktopAssistente() {
  const { layout, setPanelOpen, setPanelSize } = useShell();
  const { open, size } = layout;
  return (
    <div data-region="workspace" className="flex h-full min-h-0 min-w-0 flex-1 pb-2.5 pr-2.5">
      {open.left ? (
        <>
          <ConversationList onHide={() => setPanelOpen("left", false)} className="tile-enter-left shrink-0 overflow-hidden rounded-tile" style={{ width: size.left }} />
          <Gutter
            orientation="vertical"
            label="Larghezza delle conversazioni"
            value={size.left}
            min={PANEL_LIMITS.left.min}
            max={PANEL_LIMITS.left.max}
            direction={1}
            onResize={(px) => setPanelSize("left", px)}
            onReset={() => setPanelSize("left", PANEL_LIMITS.left.initial)}
          />
        </>
      ) : (
        <CollapsedRail side="left" label="Conversazioni" icon={MessagesSquare} shortcut={PANEL_SHORTCUT.left} onOpen={() => setPanelOpen("left", true)} className="mr-2.5" />
      )}
      <ConversationTile phone={false} listHidden={!open.left} />
      {open.right ? (
        <>
          <Gutter
            orientation="vertical"
            label="Larghezza dello stato vivo"
            value={size.right}
            min={PANEL_LIMITS.right.min}
            max={PANEL_LIMITS.right.max}
            direction={-1}
            onResize={(px) => setPanelSize("right", px)}
            onReset={() => setPanelSize("right", PANEL_LIMITS.right.initial)}
          />
          <LivePanel onHide={() => setPanelOpen("right", false)} className="tile-enter-right shrink-0 overflow-hidden rounded-tile" style={{ width: size.right }} />
        </>
      ) : (
        <CollapsedRail side="right" label="Stato vivo" icon={Activity} shortcut={PANEL_SHORTCUT.right} onOpen={() => setPanelOpen("right", true)} className="ml-2.5" />
      )}
    </div>
  );
}

function PhoneAssistente() {
  const [sheet, setSheet] = useState<"list" | "live" | null>(null);
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col px-2 pb-2">
      <ConversationTile phone onOpenList={() => setSheet("list")} onOpenLive={() => setSheet("live")} />
      <Sheet open={sheet === "list"} onOpenChange={(o) => setSheet(o ? "list" : null)}>
        <SheetContent side="left" initialFocus={false} className="w-[86vw] max-w-[340px] gap-0 rounded-r-tile border-0 bg-ground p-0 [&>button]:hidden">
          <SheetTitle className="sr-only">Conversazioni</SheetTitle>
          <ConversationList onPicked={() => setSheet(null)} className="h-full" />
        </SheetContent>
      </Sheet>
      <Sheet open={sheet === "live"} onOpenChange={(o) => setSheet(o ? "live" : null)}>
        <SheetContent side="right" initialFocus={false} className="w-[86vw] max-w-[340px] gap-0 rounded-l-tile border-0 bg-ground p-0 [&>button]:hidden">
          <SheetTitle className="sr-only">Stato vivo</SheetTitle>
          <LivePanel className="h-full" />
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** Home of the cockpit: Luca's conversation with the Bridge, the briefing on top, the live state beside it. */
export function AssistentePage() {
  const desktop = useMediaQuery("(min-width: 1024px)");
  useEffect(() => {
    document.title = "Assistente";
  }, []);
  return <div className={cn("flex min-h-0 min-w-0 flex-1")}>{desktop ? <DesktopAssistente /> : <PhoneAssistente />}</div>;
}
