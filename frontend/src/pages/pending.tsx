import { Link } from "react-router-dom";
import type { NavItem } from "@/shell/nav";

/** Pages not built yet say so plainly: no placeholder data. */
export function PendingPage({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <section className="grid flex-1 place-items-center p-6">
      <div className="max-w-md text-center">
        <Icon className="mx-auto size-8 text-fg-faint" strokeWidth={1.5} aria-hidden />
        <h1 className="mt-4 text-base font-semibold text-fg">{item.label}</h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">{item.summary}</p>
        <p className="mt-4 text-xs text-fg-subtle">
          Questa pagina si costruisce dopo la shell e il Terminale.{" "}
          <Link to="/terminale" className="text-accent-c underline-offset-4 hover:underline">
            Apri il Terminale
          </Link>
        </p>
      </div>
    </section>
  );
}
