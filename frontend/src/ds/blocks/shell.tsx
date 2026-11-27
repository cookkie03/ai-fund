import * as React from "react"
import { BellIcon, CheckIcon, HomeIcon, LineChartIcon, MessageSquareIcon, MoonIcon, MoreHorizontalIcon, NewspaperIcon, PauseIcon, PlayIcon, SearchIcon, SettingsIcon, SparklesIcon, SunIcon, UsersIcon, WalletIcon } from "lucide-react"
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarTrigger } from "@/ds/ui/sidebar"
import { Badge } from "@/ds/ui/badge"
import { Button } from "@/ds/ui/button"
import { Separator } from "@/ds/ui/separator"
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/ds/ui/breadcrumb"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/ds/ui/alert-dialog"
import { Popover, PopoverContent, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/ds/ui/popover"
import { Kbd } from "@/ds/ui/kbd"
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/ds/ui/dropdown-menu"
import { AgentAvatar } from "@/ds/identity/agent-avatar"
import { AfMark } from "@/ds/identity/af-mark"
import { cn } from "cn"

export type Section = "home" | "assistant" | "agents" | "markets" | "news" | "portfolio" | "approvals" | "settings"

export const NAV: { id: Section; label: string; icon: typeof HomeIcon }[] = [
  { id: "home", label: "Home", icon: HomeIcon },
  { id: "portfolio", label: "Portfolio", icon: WalletIcon },
  { id: "approvals", label: "Approvals", icon: CheckIcon },
  { id: "agents", label: "Agents", icon: UsersIcon },
  { id: "markets", label: "Markets", icon: LineChartIcon },
  { id: "news", label: "News", icon: NewspaperIcon },
  { id: "assistant", label: "Assistant", icon: SparklesIcon },
]

/** The app's navigation: shadcn Sidebar, inset variant, collapsible to icons. */
/**
 * `account` is the name Luca gave the broker account (e.g. "Alpaca · Paper").
 * The software never knows whether an account is paper or live (DECISIONS §8): it only shows the name.
 */
export function AppSidebar({ active = "home", approvals = 0, account, ...props }: React.ComponentProps<typeof Sidebar> & { active?: Section; approvals?: number; account: string }) {
  return (
    <Sidebar variant="inset" collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg">
              <AfMark className="size-8" />
              <span className="flex flex-col leading-tight"><span className="font-semibold">AI Fund</span><span className="truncate text-xs text-muted-foreground">{account}</span></span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Fund</SidebarGroupLabel>
          <SidebarMenu>
            {NAV.map((n) => (
              <SidebarMenuItem key={n.id}>
                <SidebarMenuButton isActive={active === n.id} tooltip={n.label}><n.icon /><span>{n.label}</span></SidebarMenuButton>
                {n.id === "approvals" && approvals > 0 && <SidebarMenuBadge>{approvals}</SidebarMenuBadge>}
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem><SidebarMenuButton isActive={active === "settings"} tooltip="Settings"><SettingsIcon /><span>Settings</span></SidebarMenuButton></SidebarMenuItem>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton size="lg" />}>
                <AgentAvatar actor="luca" showName description="Owner" />
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end" className="w-52">
                <DropdownMenuGroup><DropdownMenuLabel>Luca</DropdownMenuLabel></DropdownMenuGroup>
                <DropdownMenuItem><SunIcon />Light theme</DropdownMenuItem>
                <DropdownMenuItem><MoonIcon />Dark theme</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem><SettingsIcon />Settings</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}

export type Freshness = { state: "live" | "connecting" | "stale" | "unreachable"; age?: string }

/** Always-visible data freshness: dot + word (+ age). */
export function FreshnessBadge({ state, age }: Freshness) {
  const label = state === "live" ? "Live" : state === "connecting" ? "Connecting…" : state === "stale" ? `Stale data${age ? ` · ${age}` : ""}` : "Runtime unreachable"
  return (
    <Badge variant="outline" className="gap-1.5">
      <span className={cn("size-1.5 rounded-full", state === "live" && "bg-success", state === "connecting" && "bg-muted-foreground ds-breathe", state === "stale" && "bg-warning", state === "unreachable" && "bg-destructive")} />
      {label}
    </Badge>
  )
}

/** Halt / Resume trading. Halt always asks first. */
export function HaltButton({ halted = false, onHalt, onResume, size = "sm" }: { halted?: boolean; onHalt?: () => void; onResume?: () => void; size?: "sm" | "default" }) {
  if (halted) return <Button size={size} variant="outline" onClick={onResume}><PlayIcon />Resume trading</Button>
  return (
    <AlertDialog>
      <AlertDialogTrigger render={<Button size={size} variant="destructive" />}><PauseIcon />Halt</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Halt all trading?</AlertDialogTitle>
          <AlertDialogDescription>Pending orders are suspended and every capital action is disabled until you resume.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={onHalt}>Halt trading</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** The slim bar at the top of the inset: sidebar toggle, where you are, search, freshness, Bridge, notifications, Halt. */
export function TopBar({ crumbs = [], freshness = { state: "live" }, notifications = 0, halted, onSearch, onBridge }: { crumbs?: string[]; freshness?: Freshness; notifications?: number; halted?: boolean; onSearch?: () => void; onBridge?: () => void }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-1 h-4 self-center" />
      <Breadcrumb>
        <BreadcrumbList>
          {crumbs.map((c, i) => (
            <React.Fragment key={c}>
              {i > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>{i === crumbs.length - 1 ? <BreadcrumbPage>{c}</BreadcrumbPage> : <BreadcrumbLink href="#">{c}</BreadcrumbLink>}</BreadcrumbItem>
            </React.Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="outline" size="sm" className="w-56 justify-start text-muted-foreground" onClick={onSearch}><SearchIcon />Search instruments<Kbd className="ml-auto">⌘K</Kbd></Button>
        <FreshnessBadge {...freshness} />
        <Button variant="ghost" size="icon-sm" aria-label="Open Bridge" onClick={onBridge}><MessageSquareIcon /></Button>
        <Popover>
          <PopoverTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Notifications" className="relative" />}>
            <BellIcon />{notifications > 0 && <span className="absolute top-1 right-1 size-2 rounded-full bg-destructive" />}
          </PopoverTrigger>
          <PopoverContent align="end"><PopoverHeader><PopoverTitle>Notifications</PopoverTitle></PopoverHeader></PopoverContent>
        </Popover>
        <HaltButton halted={halted} />
      </div>
    </header>
  )
}

/** Phone navigation: five tabs fixed at the bottom; the rest lives under More. */
export function MobileTabBar({ active = "home", approvals = 0 }: { active?: Section | "more"; approvals?: number }) {
  const tabs: { id: Section | "more"; label: string; icon: typeof HomeIcon }[] = [
    { id: "home", label: "Home", icon: HomeIcon },
    { id: "portfolio", label: "Portfolio", icon: WalletIcon },
    { id: "approvals", label: "Approvals", icon: CheckIcon },
    { id: "agents", label: "Agents", icon: UsersIcon },
    { id: "more", label: "More", icon: MoreHorizontalIcon },
  ]
  return (
    <nav className="grid grid-cols-5 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
      {tabs.map((t) => (
        <button key={t.id} type="button" aria-current={active === t.id ? "page" : undefined} className={cn("relative flex flex-col items-center gap-1 py-2 text-[11px] font-medium text-muted-foreground transition-colors", active === t.id && "text-foreground")}>
          <t.icon className="size-5" />
          {t.label}
          {t.id === "approvals" && approvals > 0 && <span className="absolute top-1 left-1/2 ml-2 rounded-full bg-primary px-1.5 text-[10px] leading-4 text-primary-foreground">{approvals}</span>}
        </button>
      ))}
    </nav>
  )
}


