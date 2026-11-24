import { BellDot, Bell, CheckCheck, CircleAlert, Info, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fmtWhen } from "@/lib/format";
import { useCommand, useInbox } from "@/lib/runtime/hooks";
import type { InboxItem } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { useShell } from "./shell-state";

const KIND: Record<string, { icon: typeof Info; tone: string; label: string }> = {
  approval: { icon: CircleAlert, tone: "text-warn", label: "Approvazione" },
  risk: { icon: ShieldAlert, tone: "text-down", label: "Risk Gate" },
  alert: { icon: CircleAlert, tone: "text-warn", label: "Allerta" },
  info: { icon: Info, tone: "text-fg-subtle", label: "Info" },
};

function Row({ item, onRead, disabled }: { item: InboxItem; onRead: () => void; disabled: boolean }) {
  const k = KIND[item.kind] ?? KIND.info;
  const Icon = k.icon;
  return (
    <li className={cn("group flex gap-3 border-b border-line px-3 py-2.5 last:border-b-0", item.read && "opacity-60")}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", k.tone)} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-2xs text-fg-subtle">
          <span className={cn("font-medium", item.read ? "" : k.tone)}>{k.label}</span>
          <span className="num ml-auto">{fmtWhen(item.ts)}</span>
        </div>
        <p className="mt-0.5 text-xs leading-snug text-fg">{item.text}</p>
      </div>
      {!item.read && (
        <Button
          type="button"
          variant="ghost"
          size="xs"
          onClick={onRead}
          disabled={disabled}
          className="mt-0.5 h-6 shrink-0 self-start rounded-item px-1.5 text-2xs text-fg-subtle"
        >
          Letto
        </Button>
      )}
    </li>
  );
}

export function InboxButton({ variant = "rail" }: { variant?: "rail" | "bar" }) {
  const inbox = useInbox();
  const { writable } = useShell();
  const markRead = useCommand("mark_inbox_read", { invalidate: [["inbox"]] });
  const items = inbox.data ?? [];
  const unread = items.filter((i) => !i.read);

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger
          render={
            <PopoverTrigger
              className={cn(
                "relative grid place-items-center rounded-control text-fg-subtle transition-colors hover:bg-hover hover:text-fg",
                variant === "rail" ? "size-9" : "size-8",
              )}
              aria-label={`Inbox, ${unread.length} non letti`}
            >
              {unread.length ? <BellDot className="size-[18px]" /> : <Bell className="size-[18px]" />}
              {unread.length > 0 && (
                <span className="num absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-warn px-1 text-[10px] font-semibold leading-none text-ground">
                  {unread.length}
                </span>
              )}
            </PopoverTrigger>
          }
        />
        <TooltipContent side={variant === "rail" ? "right" : "bottom"}>Inbox</TooltipContent>
      </Tooltip>
      <PopoverContent side={variant === "rail" ? "right" : "bottom"} align={variant === "rail" ? "end" : "end"} className="w-[360px] border-line-strong bg-raised p-0">
        <div className="flex h-10 items-center gap-2 border-b border-line px-3">
          <span className="text-sm font-medium">Inbox</span>
          <span className="num text-xs text-fg-subtle">{unread.length} non letti</span>
          {unread.length > 1 && (
            <button
              type="button"
              disabled={!writable || markRead.isPending}
              onClick={() => unread.forEach((i) => markRead.mutate({ item_id: i.id }))}
              className="ml-auto inline-flex h-6 items-center gap-1 rounded-item px-1.5 text-2xs text-fg-subtle hover:bg-hover hover:text-fg disabled:opacity-40"
            >
              <CheckCheck className="size-3.5" /> Segna tutti letti
            </button>
          )}
        </div>
        {inbox.isPending ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-item bg-hover" />
            ))}
          </div>
        ) : inbox.isError ? (
          <p className="p-4 text-xs text-down">Impossibile leggere l'inbox dal Runtime.</p>
        ) : items.length === 0 ? (
          <p className="p-4 text-xs leading-relaxed text-fg-subtle">Nessun avviso. Qui arrivano approvazioni richieste, rifiuti del Risk Gate e allerte del Runtime.</p>
        ) : (
          <ScrollArea className="max-h-[420px]">
            <ul>
              {items.map((item) => (
                <Row key={item.id} item={item} disabled={!writable} onRead={() => markRead.mutate({ item_id: item.id })} />
              ))}
            </ul>
          </ScrollArea>
        )}
      </PopoverContent>
    </Popover>
  );
}
