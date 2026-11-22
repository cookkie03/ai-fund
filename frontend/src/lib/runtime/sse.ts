import type { RuntimeEvent } from "./types";

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed";

type Options = {
  url: (after: number | null) => string;
  /** Last event id already applied; the stream replays everything after it. */
  initialAfter: number | null;
  onEvent: (event: RuntimeEvent) => void;
  onStatus: (status: StreamStatus) => void;
};

/**
 * SSE subscription with replay. The browser's EventSource resends `Last-Event-ID` on its own
 * reconnects; after an error we close it and reopen with `?after=<last id>` and backoff,
 * so no event is lost or applied twice.
 */
export function subscribeEvents({ url, initialAfter, onEvent, onStatus }: Options): () => void {
  let lastId = initialAfter;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let stopped = false;

  const handle = (raw: MessageEvent) => {
    const id = Number(raw.lastEventId);
    if (Number.isFinite(id) && lastId !== null && id <= lastId) return;
    if (Number.isFinite(id)) lastId = id;
    let data: Record<string, unknown> = {};
    try {
      data = JSON.parse(raw.data);
    } catch {
      /* non-JSON payload: keep empty */
    }
    onEvent({ id, type: raw.type, data });
  };

  const open = () => {
    if (stopped) return;
    onStatus(attempt === 0 ? "connecting" : "reconnecting");
    source = new EventSource(url(lastId));
    source.onopen = () => {
      attempt = 0;
      onStatus("open");
    };
    source.onmessage = handle;
    source.onerror = () => {
      source?.close();
      source = null;
      if (stopped) return;
      attempt += 1;
      onStatus("reconnecting");
      const delay = Math.min(15_000, 500 * 2 ** Math.min(attempt, 5));
      timer = setTimeout(open, delay);
    };
    for (const type of EVENT_TYPES) source.addEventListener(type, handle as EventListener);
  };

  open();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    source?.close();
    onStatus("closed");
  };
}

/** Event names the Runtime emits (runtime/, execution/, workflows/). Named SSE events need a listener each. */
export const EVENT_TYPES = [
  // Ufficio (backend-ufficio): live chat, tool calls and agent state.
  "agent.status",
  "chat.message",
  "tool.started",
  "tool.called",
  // Ticker agents (ticker-agents-backend): dossier versions and the proposal flow.
  "dossier.updated",
  "proposal.submitted",
  "proposal.decided",
  "annotation.created",
  "annotation.updated",
  "annotation.struck",
  "command.accepted",
  "command.rejected",
  "cycle.opened",
  "cycle.closed",
  "data.refreshed",
  "halt.changed",
  "inbox.changed",
  "job.ran",
  "message.appended",
  "order.created",
  "order.approved",
  "order.rejected",
  "order.status_changed",
  "portfolio.synced",
  "runtime.started",
  "runtime.stopped",
  "task.delivered",
  "task.enqueued",
  "trade.opened",
  "trade.closed",
  "watchlist.changed",
] as const;
