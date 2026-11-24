import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { matchPath, useLocation, useNavigate } from "react-router-dom";
import { author, tickerOf } from "@/lib/authors";
import { RuntimeError } from "@/lib/runtime/client";
import { CommandRefused } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import { useConversation, useConversations } from "./hooks";
import type { BridgeContext, LiveTurn } from "./types";

const CURRENT_KEY = "cockpit.bridge.conversation";

/** A message Luca sent that the conversation read does not show yet. */
export type PendingSend = { key: string; conversationId: number | null; text: string; context: BridgeContext | null; failed: string[] | null };

type SendOpts = { conversationId?: number | null; context?: BridgeContext | null };

type BridgeState = {
  /** null = a new conversation not created yet. */
  currentId: number | null;
  select: (id: number | null) => void;
  /** `unavailable` while the Runtime has no Bridge reads: the panel falls back to `say`. */
  availability: "loading" | "ready" | "unavailable" | "error";
  endpoint: string | null;
  /** The page's context, attached to every message sent from the side Bridge. */
  pageContext: BridgeContext | null;
  contextLabel: (c: BridgeContext | null) => string | null;
  /** Pages with a selection (Portafoglio's position) declare it here. */
  setPageRef: (ref: { type: string; id: string; ticker?: string | null } | null) => void;
  live: Record<number, LiveTurn>;
  pending: PendingSend[];
  sending: boolean;
  send: (text: string, opts?: SendOpts) => Promise<number | null>;
  retry: (key: string) => void;
  discard: (key: string) => void;
  /** Text to put in the composer (the shell's "scrivi a un agente"). */
  seed: { text: string; nonce: number } | null;
  seedComposer: (text: string) => void;
};

const Ctx = createContext<BridgeState | null>(null);

function loadCurrent(): number | null {
  try {
    const raw = localStorage.getItem(CURRENT_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

const PAGE_LABEL: Record<string, string> = { terminale: "Terminale", ticker: "Scheda", portafoglio: "Portafoglio", ufficio: "Ufficio", assistente: "Assistente" };

export function contextLabel(c: BridgeContext | null): string | null {
  if (!c) return null;
  const page = PAGE_LABEL[c.page] ?? c.page;
  if (c.ref?.type === "agent") return `${page} · ${author(c.ref.id).short}`;
  if (c.ref?.type === "position") return `${page} · posizione ${c.ref.id}`;
  if (c.ref?.type === "briefing_item") return c.ticker ? `Briefing · ${c.ticker}` : "Briefing";
  if (c.ref && c.ref.type !== "ticker") return `${page} · ${c.ref.type} ${c.ref.id}`;
  if (c.ticker) return `${page} · ${c.ticker}`;
  return c.page === "assistente" ? null : page;
}

function useRouteContext(declared: { type: string; id: string; ticker?: string | null } | null): BridgeContext | null {
  const { pathname, search } = useLocation();
  return useMemo(() => {
    if (pathname === "/" || pathname.startsWith("/assistente")) return null;
    if (pathname.startsWith("/terminale")) {
      const t = new URLSearchParams(search).get("t")?.toUpperCase() ?? null;
      return { page: "terminale", ticker: t, ref: t ? { type: "ticker", id: t } : null };
    }
    const tk = matchPath("/ticker/:symbol", pathname);
    if (tk?.params.symbol) {
      const t = tk.params.symbol.toUpperCase();
      return { page: "ticker", ticker: t, ref: { type: "ticker", id: t } };
    }
    if (pathname.startsWith("/portafoglio")) {
      return { page: "portafoglio", ticker: declared?.ticker ?? null, ref: declared ? { type: declared.type, id: declared.id } : null };
    }
    const uf = matchPath("/ufficio/:agent", pathname);
    if (uf?.params.agent) return { page: "ufficio", ticker: tickerOf(uf.params.agent), ref: { type: "agent", id: uf.params.agent } };
    if (pathname.startsWith("/ufficio")) return { page: "ufficio", ticker: null, ref: null };
    return { page: pathname.split("/")[1] || "assistente", ticker: null, ref: null };
  }, [pathname, search, declared]);
}

export function BridgeProvider({ children }: { children: ReactNode }) {
  const { client, onEvent } = useRuntime();
  const qc = useQueryClient();
  const [currentId, setCurrentId] = useState<number | null>(loadCurrent);
  const [declared, setDeclared] = useState<{ type: string; id: string; ticker?: string | null } | null>(null);
  const [live, setLive] = useState<Record<number, LiveTurn>>({});
  const [pending, setPending] = useState<PendingSend[]>([]);
  const [seed, setSeed] = useState<BridgeState["seed"]>(null);
  const pageContext = useRouteContext(declared);
  const list = useConversations();
  const current = useConversation(currentId);

  const select = useCallback((id: number | null) => {
    setCurrentId(id);
    try {
      if (id === null) localStorage.removeItem(CURRENT_KEY);
      else localStorage.setItem(CURRENT_KEY, String(id));
    } catch {
      /* storage unavailable */
    }
  }, []);

  // A remembered conversation that no longer exists (other account, deleted DB) falls back to the latest.
  useEffect(() => {
    if (current.data?.state !== "missing" || list.data?.state !== "ok") return;
    select(list.data.data.find((c) => c.id !== currentId)?.id ?? null);
  }, [current.data, list.data, currentId, select]);

  // bridge.status: "thinking" → "tool" (with the tool's name) → "idle", per conversation.
  useEffect(
    () =>
      onEvent((e) => {
        if (e.type !== "bridge.status") return;
        const id = Number(e.data.conversation_id);
        if (!Number.isFinite(id)) return;
        const status = e.data.status === "thinking" || e.data.status === "tool" ? e.data.status : "idle";
        const tool = typeof e.data.tool === "string" && e.data.tool ? e.data.tool : null;
        setLive((m) => ({ ...m, [id]: { status, tool, at: Date.now() } }));
      }),
    [onEvent],
  );

  const say = useMutation({
    mutationFn: async (p: PendingSend) => {
      const res = await client.command("bridge_say", { conversation_id: p.conversationId, text: p.text, context: p.context });
      if (!res.ok) throw new CommandRefused(res.reasons);
      const id = Number((res.data as Record<string, unknown>).conversation_id);
      return Number.isFinite(id) ? id : null;
    },
  });

  const run = useCallback(
    async (p: PendingSend): Promise<number | null> => {
      setPending((list) => [...list.filter((x) => x.key !== p.key), { ...p, failed: null }]);
      try {
        const id = await say.mutateAsync(p);
        if (id !== null && p.conversationId === null) {
          setPending((list) => list.map((x) => (x.key === p.key ? { ...x, conversationId: id } : x)));
          select(id);
        }
        await Promise.all([qc.invalidateQueries({ queryKey: ["bridge", "conversation"] }), qc.invalidateQueries({ queryKey: ["bridge", "conversations"] })]);
        setPending((list) => list.filter((x) => x.key !== p.key));
        return id;
      } catch (err) {
        const reasons =
          err instanceof CommandRefused
            ? err.reasons.length
              ? err.reasons
              : ["Nessuna ragione indicata"]
            : err instanceof RuntimeError && err.unreachable
              ? ["Runtime irraggiungibile: il messaggio non è stato inviato."]
              : err instanceof RuntimeError && err.status === 404
                ? ["Il Runtime non espone ancora il comando bridge_say."]
                : [err instanceof Error ? err.message : String(err)];
        setPending((list) => list.map((x) => (x.key === p.key ? { ...x, failed: reasons } : x)));
        return null;
      }
    },
    [say, qc, select],
  );

  const send = useCallback(
    (text: string, opts: SendOpts = {}) =>
      run({ key: crypto.randomUUID(), conversationId: opts.conversationId === undefined ? currentId : opts.conversationId, text, context: opts.context === undefined ? null : opts.context, failed: null }),
    [run, currentId],
  );

  const pendingRef = useRef(pending);
  pendingRef.current = pending;

  const value = useMemo<BridgeState>(() => {
    const d = list.data;
    const availability: BridgeState["availability"] = list.isPending ? "loading" : list.isError ? "error" : d?.state === "unavailable" ? "unavailable" : "ready";
    return {
      currentId,
      select,
      availability,
      endpoint: d?.state === "unavailable" ? d.endpoint : null,
      pageContext,
      contextLabel,
      setPageRef: setDeclared,
      live,
      pending,
      sending: say.isPending,
      send,
      retry: (key) => {
        const p = pendingRef.current.find((x) => x.key === key);
        if (p) void run(p);
      },
      discard: (key) => setPending((list) => list.filter((x) => x.key !== key)),
      seed,
      seedComposer: (text) => setSeed({ text, nonce: Date.now() }),
    };
  }, [list.data, list.isPending, list.isError, currentId, select, pageContext, live, pending, say.isPending, send, run, seed]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBridge(): BridgeState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useBridge outside BridgeProvider");
  return ctx;
}

/** Declares the page's selection (e.g. the open position) as the side Bridge's context while mounted. */
export function usePageRef(ref: { type: string; id: string; ticker?: string | null } | null) {
  const { setPageRef } = useBridge();
  const key = ref ? `${ref.type}:${ref.id}` : "";
  useEffect(() => {
    setPageRef(ref);
    return () => setPageRef(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, setPageRef]);
}

/** Open the Assistente on a conversation. */
export function useOpenInAssistente() {
  const navigate = useNavigate();
  const { select } = useBridge();
  return (id: number | null) => {
    select(id);
    navigate("/assistente");
  };
}

