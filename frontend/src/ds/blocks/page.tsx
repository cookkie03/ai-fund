import * as React from "react"
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/ds/ui/breadcrumb"
import { ToggleGroup, ToggleGroupItem } from "@/ds/ui/toggle-group"
import { Delta } from "@/ds/identity/delta"
import { AnimatedNumber, Reveal } from "@/ds/motion"
import { money } from "@/ds/blocks/stat-card"

/** Title of a page: optional breadcrumb, the noun, one line of description, actions on the right. */
export function PageHeader({ title, description, crumbs, actions }: { title: string; description?: string; crumbs?: string[]; actions?: React.ReactNode }) {
  return (
    <Reveal className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1">
        {crumbs && crumbs.length > 0 && (
          <Breadcrumb>
            <BreadcrumbList>
              {crumbs.map((c, i) => (
                <React.Fragment key={c}>{i > 0 && <BreadcrumbSeparator />}<BreadcrumbItem>{i === crumbs.length - 1 ? <BreadcrumbPage>{c}</BreadcrumbPage> : <BreadcrumbLink href="#">{c}</BreadcrumbLink>}</BreadcrumbItem></React.Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        )}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </Reveal>
  )
}

export const PERIODS = ["1D", "1W", "1M", "3M", "YTD", "1Y", "All"] as const

/** The one hero figure of a page (Revolut-style balance): label, counting number, change, period. */
export function HeroBalance({ label = "Total equity", value, change, changePct, period = "1D", onPeriod }: { label?: string; value: number; change?: number; changePct?: number; period?: string; onPeriod?: (p: string) => void }) {
  return (
    <Reveal className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-sm text-muted-foreground">{label}</span>
        <AnimatedNumber value={value} format={(v) => money(v)} className="text-4xl font-semibold tracking-tight" />
        <span className="flex items-center gap-2 text-sm">
          {change !== undefined && <Delta value={change} kind="amount" />}
          {changePct !== undefined && <Delta value={changePct} />}
          <span className="text-muted-foreground">{period === "1D" ? "today" : period}</span>
        </span>
      </div>
      <ToggleGroup value={[period]} onValueChange={(v) => v[0] && onPeriod?.(v[0])} variant="outline" size="sm">
        {PERIODS.map((p) => <ToggleGroupItem key={p} value={p}>{p}</ToggleGroupItem>)}
      </ToggleGroup>
    </Reveal>
  )
}
