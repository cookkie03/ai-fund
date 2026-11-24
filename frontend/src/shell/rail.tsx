import { NavLink, useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
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

/** "/" is the Assistente too: its nav item stays lit on the home. */
function useHomeActive() {
  const { pathname } = useLocation();
  return (path: string, isActive: boolean) => isActive || (path === "/assistente" && pathname === "/");
}

export function AppSidebar() {
  const { pathname } = useLocation();
  const homeActive = useHomeActive();

  return (
    <Sidebar collapsible="icon" className="border-r border-line bg-desk">
      <SidebarHeader className="h-14 items-center justify-center p-2">
        <div className="grid size-9 place-items-center" title="Cockpit">
          <Mark />
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2 py-1">
        <SidebarMenu className="gap-1.5">
          {NAV.map((item) => {
            const isActive = homeActive(item.path, pathname === item.path || (item.path !== "/" && pathname.startsWith(item.path)));
            return (
              <SidebarMenuItem key={item.path}>
                <SidebarMenuButton
                  isActive={isActive}
                  tooltip={item.label}
                  className={cn(
                    "flex items-center gap-3 rounded-control text-sm transition-[background-color,color,transform] duration-150 active:scale-[0.96]",
                    isActive
                      ? "bg-ground font-medium text-fg shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]"
                      : "text-fg-subtle hover:bg-hover hover:text-fg"
                  )}
                  render={
                    <NavLink to={item.path} aria-label={item.label}>
                      <item.icon className="size-[18px] shrink-0" strokeWidth={1.75} />
                      <span className="truncate group-data-[collapsible=icon]:hidden">{item.label}</span>
                    </NavLink>
                  }
                />
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="items-center p-2">
        <InboxButton />
      </SidebarFooter>
    </Sidebar>
  );
}

export function BottomNav() {
  const active = useHomeActive();
  return (
    <nav data-region="bottomnav" aria-label="Pagine" className="flex h-14 shrink-0 items-stretch bg-desk pb-[env(safe-area-inset-bottom)] md:hidden">
      {NAV.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) =>
            cn("flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] transition-colors", active(item.path, isActive) ? "text-accent-c" : "text-fg-subtle")
          }
        >
          <item.icon className="size-5" strokeWidth={1.75} />
          <span className="max-w-full truncate px-0.5">{item.label === "Configurazioni" ? "Config." : item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
