import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-control text-sm font-medium whitespace-nowrap transition-[background-color,color,border-color,box-shadow,transform] duration-150 active:scale-[0.97] outline-none focus-visible:ring-2 focus-visible:ring-ring/70 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[inset_0_0.5px_0_oklch(1_0_0/0.22),0_1px_2px_oklch(0_0_0/0.4)] hover:bg-[oklch(0.66_0.17_252)] active:bg-[oklch(0.58_0.17_252)]",
        destructive:
          "bg-[oklch(0.56_0.19_22)] text-white shadow-[inset_0_0.5px_0_oklch(1_0_0/0.2),0_1px_2px_oklch(0_0_0/0.4)] hover:bg-[oklch(0.6_0.19_22)] focus-visible:ring-destructive/50",
        outline:
          "border border-line-strong bg-transparent text-fg hover:bg-hover",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "text-fg-muted hover:bg-hover hover:text-fg",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3 has-[>svg]:px-2.5",
        xs: "h-6 gap-1 rounded-item px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1.5 rounded-control px-2.5 text-xs has-[>svg]:px-2",
        lg: "h-10 rounded-control px-6 has-[>svg]:px-4",
        icon: "size-8",
        "icon-xs": "size-6 rounded-item [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

interface ButtonProps
  extends Omit<ButtonPrimitive.Props, "render">,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  render?: ButtonPrimitive.Props["render"]
}

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  render,
  children,
  ...props
}: ButtonProps) {
  const resolvedRender =
    render ?? (asChild && React.isValidElement(children) ? children : undefined)
  const resolvedChildren =
    asChild && React.isValidElement(children) ? undefined : children

  return (
    <ButtonPrimitive
      data-slot="button"
      data-variant={variant}
      data-size={size}
      render={resolvedRender}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    >
      {resolvedChildren}
    </ButtonPrimitive>
  )
}

export { Button, buttonVariants }
export type { ButtonProps }
