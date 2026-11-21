import { NavLink } from "react-router-dom";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { InboxButton } from "./inbox";
import { NAV } from "./nav";

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
      <rect width="32" height="32" rx="7" fill="var(--raised)" />
      <path d="M8 21v-6M13 23V11M18 19V9M23 17v-5" stroke="var(--accent-c)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function Rail() {
  return (
    <nav data-region="rail" aria-label="Pagine" className="hidden w-[52px] shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-2 md:flex">
      <div className="mb-2 grid size-9 place-items-center" title="Cockpit">
        <Mark />
      </div>
      {NAV.map((item) => (
        <Tooltip key={item.path}>
          <TooltipTrigger asChild>
            <NavLink
              to={item.path}
              aria-label={item.label}
              className={({ isActive }) =>
                cn(
                  "grid size-9 place-items-center rounded-md transition-colors duration-150",
                  isActive ? "bg-selected text-accent-c" : "text-fg-subtle hover:bg-hover hover:text-fg",
                )
              }
            >
              <item.icon className="size-[18px]" strokeWidth={1.75} />
            </NavLink>
          </TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      ))}
      <div className="mt-auto">
        <InboxButton />
      </div>
    </nav>
  );
}

export function BottomNav() {
  return (
    <nav data-region="bottomnav" aria-label="Pagine" className="flex h-14 shrink-0 items-stretch border-t border-line bg-panel pb-[env(safe-area-inset-bottom)] md:hidden">
      {NAV.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) =>
            cn("flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] transition-colors", isActive ? "text-accent-c" : "text-fg-subtle")
          }
        >
          <item.icon className="size-5" strokeWidth={1.75} />
          <span className="max-w-full truncate px-0.5">{item.label === "Configurazioni" ? "Config." : item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
