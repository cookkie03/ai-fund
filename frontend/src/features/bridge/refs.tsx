import { Bot, CandlestickChart, ClipboardList, FileText, Hash, Receipt, RefreshCcw, WalletCards, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { author } from "@/lib/authors";
import { cn } from "@/lib/utils";
import type { MessageRef } from "./types";

const PF_TAB_KEY = "cockpit.portafoglio.tab";

type Target = { to: string; icon: LucideIcon; label: string; tab?: string };

/** Where a reference leads: ticker → its dossier, position/order/trade → Portafoglio, proposal → the PM's queue, agent → its office view. */
export function refTarget(ref: { type: string; id: string; label?: string | null }): Target | null {
  const label = ref.label ?? null;
  switch (ref.type) {
    case "ticker":
      return { to: `/ticker/${encodeURIComponent(ref.id.toUpperCase())}`, icon: Hash, label: label ?? ref.id.toUpperCase() };
    case "position":
      return { to: "/portafoglio", icon: WalletCards, label: label ?? `Posizione ${ref.id}`, tab: "positions" };
    case "order":
      return { to: "/portafoglio", icon: Receipt, label: label ?? `Ordine #${ref.id}`, tab: "operations" };
    case "trade":
      return { to: "/portafoglio", icon: CandlestickChart, label: label ?? `Trade #${ref.id}`, tab: "operations" };
    case "proposal":
      return { to: "/ufficio/portfolio_manager", icon: ClipboardList, label: label ?? `Proposta #${ref.id}` };
    case "agent":
      return { to: `/ufficio/${encodeURIComponent(ref.id)}`, icon: Bot, label: label ?? author(ref.id).name };
    case "cycle":
      return { to: "/ufficio", icon: RefreshCcw, label: label ?? `Ciclo #${ref.id}` };
    default:
      return label ? { to: "", icon: FileText, label } : null;
  }
}

/** A reference the Bridge cites: a quiet tag that opens the object where it lives. */
export function RefTag({ refItem, className }: { refItem: MessageRef | { type: string; id: string; label?: string | null }; className?: string }) {
  const t = refTarget(refItem);
  if (!t) return null;
  const Icon = t.icon;
  const body = (
    <>
      <Icon className="size-3 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
      <span className="truncate">{t.label}</span>
    </>
  );
  const cls = cn(
    "inline-flex h-5 max-w-[22ch] [@media(pointer:coarse)]:h-6 items-center gap-1 rounded-tag bg-hover px-1.5 text-2xs text-fg-muted transition-colors duration-150",
    t.to && "hover:bg-selected hover:text-fg",
    className,
  );
  if (!t.to) return <span className={cls}>{body}</span>;
  return (
    <Link
      to={t.to}
      className={cls}
      onClick={() => {
        if (!t.tab) return;
        try {
          localStorage.setItem(PF_TAB_KEY, t.tab);
        } catch {
          /* storage unavailable */
        }
      }}
    >
      {body}
    </Link>
  );
}
