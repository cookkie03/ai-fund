import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { AuthorChip } from "@/components/author-chip";
import { COCKPIT_TOPIC } from "@/features/office/api";
import { AGENTS, AGENT_IDS, author } from "@/lib/authors";
import { fmtWhen, parseTs } from "@/lib/format";
import { useRuntime } from "@/lib/runtime/provider";
import type { Message } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { useBridge } from "./state";

/** Every agent's "cockpit" chat merged by time: what Luca wrote with `@agent` while the Bridge is not there. */
function useCockpitThreads() {
  const { client, target } = useRuntime();
  const results = useQueries({
    queries: AGENT_IDS.map((agent) => ({
      queryKey: ["cycles", target.id, "chat", agent, COCKPIT_TOPIC],
      queryFn: () => client.read<Message[]>("chat", { agent, topic: COCKPIT_TOPIC, limit: 100 }),
      staleTime: 10_000,
    })),
  });
  const stamp = results.map((r) => r.dataUpdatedAt).join();
  const messages = useMemo(
    () =>
      results
        .flatMap((r, i) => (r.data ?? []).map((m) => ({ ...m, agent: AGENT_IDS[i] })))
        .sort((a, b) => (parseTs(a.ts) ?? 0) - (parseTs(b.ts) ?? 0)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stamp],
  );
  return { messages, loading: results.some((r) => r.isPending), error: results.every((r) => r.isError) };
}

/**
 * The Bridge's endpoints are not exposed yet: say which one is missing, and keep the old path
 * (`@agent` → `say` into that agent's "cockpit" chat) working in the same place.
 */
export function FallbackThread({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { endpoint, seedComposer } = useBridge();
  const { messages, loading, error } = useCockpitThreads();
  const pad = compact ? "px-3" : "px-5";
  return (
    <div className={cn("min-h-0 flex-1 overflow-y-auto py-3", className)}>
      <div className={cn("mb-4", pad)}>
        <div className="rounded-control bg-[oklch(0_0_0/0.2)] px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
          <p className="font-medium text-fg">Bridge non disponibile</p>
          <p className="mt-1">
            Il Runtime non espone ancora <code className="font-mono text-2xs text-fg">{endpoint ?? "GET /v1/read/bridge_conversations"}</code>. Intanto scrivi direttamente a un agente con{" "}
            <span className="text-fg">@</span>: il messaggio entra nella sua chat «{COCKPIT_TOPIC}» e lui lo pesa come il parere di un collega.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {AGENT_IDS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => seedComposer(`@${id} `)}
                className="inline-flex h-6 items-center gap-1.5 rounded-item bg-hover px-1.5 text-2xs text-fg-muted transition-colors hover:bg-selected hover:text-fg"
              >
                <AuthorChip actor={id} size="xs" tooltip={AGENTS[id].name} />
                {AGENTS[id].short}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className={pad}>
        {loading ? (
          <div className="space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded-item bg-hover" />
            ))}
          </div>
        ) : error ? (
          <p className="text-xs text-warn">Impossibile leggere le chat dal Runtime.</p>
        ) : messages.length === 0 ? (
          <p className="text-xs text-fg-subtle">Nessun messaggio inviato dal cockpit.</p>
        ) : (
          <ol className="space-y-3.5">
            {messages.map((m) => {
              const a = author(m.author);
              return (
                <li key={`${m.agent}-${m.id}`} className="flex gap-2.5">
                  <AuthorChip author={a} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-1.5 text-2xs">
                      <span className="text-xs font-medium text-fg">{a.name}</span>
                      {a.kind === "human" && (
                        <span className="text-fg-subtle">
                          a <span className="text-fg-muted">{AGENTS[m.agent]?.short}</span>
                        </span>
                      )}
                      <span className="num ml-auto text-fg-subtle">{fmtWhen(m.ts)}</span>
                    </div>
                    <p className="mt-0.5 whitespace-pre-wrap text-sm leading-snug text-fg">{m.text}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
