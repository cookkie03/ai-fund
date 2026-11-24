"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Popover as PopoverPrimitive } from "@base-ui/react/popover"

function Popover({
  ...props
}: PopoverPrimitive.Root.Props) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />
}

interface PopoverTriggerProps
  extends Omit<PopoverPrimitive.Trigger.Props, "render"> {
  asChild?: boolean
  render?: PopoverPrimitive.Trigger.Props["render"]
}

function PopoverTrigger({
  asChild,
  render,
  children,
  ...props
}: PopoverTriggerProps) {
  const resolvedRender =
    render ?? (asChild && React.isValidElement(children) ? children : undefined)
  const resolvedChildren =
    asChild && React.isValidElement(children) ? undefined : children

  return (
    <PopoverPrimitive.Trigger
      data-slot="popover-trigger"
      render={resolvedRender}
      {...props}
    >
      {resolvedChildren}
    </PopoverPrimitive.Trigger>
  )
}

interface PopoverContentProps extends PopoverPrimitive.Popup.Props {
  align?: PopoverPrimitive.Positioner.Props["align"]
  alignOffset?: PopoverPrimitive.Positioner.Props["alignOffset"]
  side?: PopoverPrimitive.Positioner.Props["side"]
  sideOffset?: PopoverPrimitive.Positioner.Props["sideOffset"]
}

function PopoverContent({
  className,
  align = "center",
  alignOffset = 0,
  side = "bottom",
  sideOffset = 4,
  children,
  ...props
}: PopoverContentProps) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="isolate z-50 outline-none"
      >
        <PopoverPrimitive.Popup
          data-slot="popover-content"
          className={cn(
            "z-50 w-72 origin-(--transform-origin) rounded-tile border border-line-strong/70 bg-raised p-4 text-popover-foreground shadow-[0_16px_40px_-12px_oklch(0_0_0/0.75),0_2px_6px_oklch(0_0_0/0.35)] outline-hidden data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            className
          )}
          {...props}
        >
          {children}
        </PopoverPrimitive.Popup>
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  )
}

function PopoverAnchor({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return <div data-slot="popover-anchor" className={className} {...props} />
}

function PopoverHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="popover-header"
      className={cn("flex flex-col gap-1 text-sm", className)}
      {...props}
    />
  )
}

function PopoverTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return (
    <div
      data-slot="popover-title"
      className={cn("font-medium", className)}
      {...props}
    />
  )
}

function PopoverDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="popover-description"
      className={cn("text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverAnchor,
  PopoverHeader,
  PopoverTitle,
  PopoverDescription,
}
