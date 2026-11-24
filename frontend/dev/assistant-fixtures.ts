// Development only. Answers the Bridge agent's reads and commands the Runtime does not expose yet
// (`bridge_conversations`, `bridge_conversation`, `bridge_actions`, `briefing`, `bridge_say`, `bridge_stop`,
// `bridge_rename_conversation`, `bridge_archive_conversation`, `bridge_action_decide`, `mark_briefing_seen`)
// with synthetic data shaped exactly like the binding contract in .scratch/assistente/handoff-backend.md,
// and simulates a turn's SSE events (`bridge.status`, `bridge.message`, `bridge.action`, `bridge.conversation`,
// `briefing.updated`) by relaying the Runtime's `/v1/events` stream with the fixture's events woven in.
// Enabled only by `COCKPIT_ASSISTANT_FIXTURES` on `vite` serve: it never reaches a build.
//   =1        seeded conversations and briefing
//   =empty    no conversations, nothing new in the briefing
//   =slow     reads answer after 2,5 s (loading states)
//   =nobudget the Bridge's budget is spent: no summary, every turn ends in an error
// Values combine with commas (e.g. `=1,slow`).
import http from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

type Row = Record<string, unknown>;
const MIN = 60_000;
const H = 60 * MIN;
const iso = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();

type Action = {
  id: number;
  command: string;
  payload: Row;
  summary: string;
  capital: true;
  status: "pending" | "confirmed" | "dismissed" | "executed" | "failed";
  preview: { ok: boolean; reasons: string[]; detail: Row | null } | null;
  result_reasons: string[];
  decided_ts: string | null;
  decided_by: string | null;
};

type Msg = {
  id: number;
  conversation_id: number;
  author: string;
  kind: "text" | "agent_relay" | "action" | "error";
  text: string;
  ts: string;
  context: { page: string; ticker: string | null; ref: { type: string; id: string } | null } | null;
  refs: { type: string; id: string; label: string | null }[];
  action: Action | null;
};

type Conv = { id: number; title: string; created_ts: string; updated_ts: string; archived: boolean; messages: Msg[] };

type Turn = { status: "thinking" | "tool"; tool: string | null; timers: ReturnType<typeof setTimeout>[]; queued: boolean };

const ORDER_COMMANDS = new Set(["approve_order", "close_position", "modify_exit", "decide_proposal"]);
const AGENT_NAMES: Record<string, string> = {
  portfolio_manager: "il PM",
  technical_analyst: "il Tecnico",
  fundamental_analyst: "il Fondamentale",
  sentiment_analyst: "il Sentiment",
  market_analyst: "il Mercato",
  risk_analyst: "il Rischio",
};
const agentName = (id: string) => AGENT_NAMES[id] ?? id;
const TICKERS = ["AAPL", "NVDA", "AMD", "AVGO", "MSFT", "GOOGL", "LLY", "JPM", "TSLA", "META", "COST", "XOM", "MU"];

function seed(): { convs: Map<number, Conv>; nextMsg: number; nextAction: number } {
  let mid = 9000;
  let aid = 700;
  const convs = new Map<number, Conv>();
  const conv = (id: number, title: string, createdAgo: number, archived = false): Conv => {
    const c: Conv = { id, title, created_ts: iso(createdAgo), updated_ts: iso(createdAgo), archived, messages: [] };
    convs.set(id, c);
    return c;
  };
  const msg = (c: Conv, ago: number, author: string, text: string, extra: Partial<Msg> = {}) => {
    const m: Msg = { id: ++mid, conversation_id: c.id, author, kind: "text", text, ts: iso(ago), context: null, refs: [], action: null, ...extra };
    c.messages.push(m);
    c.updated_ts = m.ts;
    return m;
  };
  const action = (a: Omit<Action, "id" | "capital" | "result_reasons" | "decided_ts" | "decided_by"> & Partial<Action>): Action => ({
    capital: true,
    result_reasons: [],
    decided_ts: null,
    decided_by: null,
    ...a,
    id: ++aid,
  });

  const arch = conv(35, "Watchlist dei semiconduttori", 3 * 24 * H, true);
  msg(arch, 3 * 24 * H, "luca", "Aggiungi AVGO e MU alla watchlist, voglio che il Tecnico li segua.");
  msg(arch, 3 * 24 * H - 40_000, "bridge", "Fatto: AVGO e MU sono in watchlist (aggiunti come Bridge per te). Il Tecnico li vedrà al prossimo giro di analisi.", {
    refs: [
      { type: "ticker", id: "AVGO", label: null },
      { type: "ticker", id: "MU", label: null },
    ],
  });

  const costs = conv(38, "Costi del Sentiment questa settimana", 26 * H);
  msg(costs, 26 * H, "luca", "Quanto ci è costato il Sentiment questa settimana? Mi sembra tanto.");
  msg(costs, 26 * H - 50_000, "bridge", "Sette giorni: 4,82 $ su 61 chiamate, il 21% della spesa degli agenti. Il picco è martedì (1,90 $): due cicli NVDA rifatti dopo il timeout del provider notizie.", {
    refs: [{ type: "agent", id: "sentiment_analyst", label: null }],
  });
  msg(costs, 25 * H, "luca", "E il dettaglio per giorno?");
  msg(costs, 25 * H - 8000, "bridge", "Budget giornaliero del Bridge esaurito (2,00 $ su 2,00 $): non posso fare altre letture oggi. Riprendo domani alle 00:00 UTC, o prima se alzi il budget del Bridge.", { kind: "error" });

  const jpm = conv(39, "Perché il PM ha rimandato JPM", 5 * H);
  msg(jpm, 5 * H, "luca", "Perché il PM ha rimandato JPM?");
  msg(jpm, 5 * H - 60_000, "bridge", "L'ha rimandata ieri alle 15:20. Il R:R della proposta è 1,50, esattamente sulla soglia del Risk Gate, e il Fondamentale aspetta i dati sui tassi di giovedì. Il PM ricontrolla dopo quella data; nella scheda il prossimo controllo è fissato a dopodomani.", {
    refs: [
      { type: "proposal", id: "407", label: "Proposta JPM #407" },
      { type: "ticker", id: "JPM", label: null },
      { type: "agent", id: "portfolio_manager", label: null },
    ],
  });
  msg(jpm, 4 * H, "luca", "Ok. Allora approva l'ordine di AAPL in attesa e alza lo stop di LLY a 760.");
  msg(jpm, 4 * H - 30_000, "bridge", "Due azioni, una per comando. L'ordine #118 è quello che il PM ha lasciato in approvazione manuale.", {
    kind: "action",
    action: action({
      command: "approve_order",
      payload: { order_id: 118 },
      summary: "Acquisto 40 AAPL limite 236,70 $, stop 224,00, target 260,80.",
      status: "executed",
      preview: { ok: true, reasons: ["Tutte le regole del Risk Gate rispettate."], detail: { quantity: 40, price: 236.7, value: 9468, risk_amount: 508 } },
      result_reasons: ["Ordine inviato al broker: 40 AAPL limite 236,70 $."],
      decided_ts: iso(4 * H - 20_000),
      decided_by: "luca",
    }),
    refs: [{ type: "order", id: "118", label: null }],
  });
  msg(jpm, 4 * H - 31_000, "bridge", "", {
    kind: "action",
    action: action({
      command: "modify_exit",
      payload: { ticker: "LLY", stop_price: 760, target_price: 855 },
      summary: "Stop di LLY da 741,00 a 760,00; target invariato.",
      status: "dismissed",
      preview: { ok: true, reasons: [], detail: { new_risk: 312, risk_reward: 2.6 } },
      decided_ts: iso(4 * H - 10_000),
      decided_by: "luca",
    }),
  });
  msg(jpm, 3 * H, "luca", "Accetta la proposta di AMD.");
  msg(jpm, 3 * H - 40_000, "bridge", "La propongo, ma l'anteprima dice già che il Risk Gate la fermerà: con il 4% il settore Tecnologia arriverebbe al 34%.", {
    kind: "action",
    action: action({
      command: "decide_proposal",
      payload: { proposal_id: 401, action: "accept", reason: "Luca: accettata dopo la revisione dei livelli." },
      summary: "Accetta la proposta long su AMD (4%, R:R 1,70).",
      status: "failed",
      preview: { ok: false, reasons: ["Settore Tecnologia al 34% dopo l'ingresso: oltre il limite del 30%."], detail: null },
      result_reasons: ["Risk Gate: settore Tecnologia al 34% dopo l'ingresso, oltre il limite del 30%. Proposta lasciata in attesa."],
      decided_ts: iso(3 * H - 30_000),
      decided_by: "luca",
    }),
    refs: [
      { type: "proposal", id: "401", label: "Proposta AMD #401" },
      { type: "ticker", id: "AMD", label: null },
    ],
  });

  const amd = conv(40, "Livelli di AMD con il Tecnico", 70 * MIN);
  msg(amd, 70 * MIN, "luca", "@technical_analyst rivedi i livelli di AMD dopo il gap di stamattina", { context: { page: "terminale", ticker: "AMD", ref: { type: "ticker", id: "AMD" } } });
  msg(amd, 69 * MIN, "bridge", "Ho scritto al Tecnico nella sua chat AMD, per conto tuo. Ti riporto qui la risposta.", {
    refs: [
      { type: "agent", id: "technical_analyst", label: null },
      { type: "ticker", id: "AMD", label: null },
    ],
  });
  msg(amd, 52 * MIN, "technical_analyst", "Il gap ha chiuso a 159,2: sposto il supporto a 158,9, il minimo della candela. Resistenza invariata a 177,5. RSI 44, nessuna divergenza; la struttura resta rialzista finché tiene 158,9.", {
    kind: "agent_relay",
    refs: [{ type: "ticker", id: "AMD", label: null }],
  });
  msg(amd, 51 * MIN, "bridge", "In sintesi: il supporto scende a 158,9 e coincide con lo stop della proposta, che quindi resta coerente. La proposta AMD è ancora in attesa del PM e il Risk Gate la blocca per l'esposizione al settore, non per i livelli.", {
    refs: [
      { type: "proposal", id: "401", label: "Proposta AMD #401" },
      { type: "cycle", id: "11", label: null },
    ],
  });

  const aapl = conv(41, "Ridurre AAPL prima della trimestrale", 9 * MIN);
  msg(aapl, 9 * MIN, "luca", "AAPL è in perdita e la trimestrale si avvicina. Ha senso alleggerire?", { context: { page: "portafoglio", ticker: "AAPL", ref: { type: "position", id: "AAPL" } } });
  msg(aapl, 8 * MIN, "bridge", "Fatti: 40 azioni a 236,72 $, prezzo 229,00 $, P&L −308,80 $ (9,2% del portafoglio). Lo stop è a 224,00, a 2,2% dal prezzo. Il Tecnico vede supporto a 225, il Sentiment è fermo da 11 giorni. Opinione mia: ridurre di metà dimezza il rischio sul gap della trimestrale senza uscire dalla tesi, che il PM considera ancora valida.", {
    refs: [
      { type: "position", id: "AAPL", label: "Posizione AAPL" },
      { type: "ticker", id: "AAPL", label: null },
    ],
  });
  msg(aapl, 6 * MIN, "bridge", "Ecco l'azione: parte solo se la confermi.", {
    kind: "action",
    action: action({
      command: "close_position",
      payload: { ticker: "AAPL", qty: 20, reason: "Riduzione prudenziale prima della trimestrale" },
      summary: "Vendita di 20 azioni AAPL a mercato; ne restano 20 con stop 224,00.",
      status: "pending",
      preview: { ok: true, reasons: ["Tutte le regole del Risk Gate rispettate."], detail: { quantity: 20, price: 229.0, value: 4580, realized_pnl: -154.4, remaining_qty: 20 } },
    }),
    refs: [{ type: "position", id: "AAPL", label: "Posizione AAPL" }],
  });

  return { convs, nextMsg: mid, nextAction: aid };
}

function briefingItems(): Row[] {
  return [
    { id: "b-halt-1", type: "resume", ts: iso(12 * H), title: "Trading ripreso dopo l'Halt di ieri sera", detail: "Ripreso da Luca via Telegram alle 21:04.", ticker: null, ref: null, severity: "info" },
    { id: "b-agent-err-2", type: "agent_error", ts: iso(2.2 * H), title: "Il Sentiment ha fallito due volte su NVDA", detail: "Provider notizie: timeout dopo 10 s (retry 2/2).", ticker: "NVDA", ref: { type: "agent", id: "sentiment_analyst" }, severity: "attention" },
    { id: "b-order-118", type: "order_pending", ts: iso(4.5 * H), title: "Ordine AAPL in attesa di approvazione", detail: "Acquisto 40 AAPL limite 236,70 $.", ticker: "AAPL", ref: { type: "order", id: "118" }, severity: "attention" },
    { id: "b-trade-311", type: "trade", ts: iso(6 * H), title: "Chiuso LLY parziale con +224,28 $", detail: "6 azioni a 812,00 $ (take profit parziale).", ticker: "LLY", ref: { type: "trade", id: "311" }, severity: "info" },
    { id: "b-prop-401", type: "proposal_pending", ts: iso(112 * MIN), title: "AMD aspetta il PM, bloccata dal Risk Gate", detail: "Settore Tecnologia al 34% dopo l'ingresso.", ticker: "AMD", ref: { type: "proposal", id: "401" }, severity: "critical" },
    { id: "b-prop-400", type: "proposal_pending", ts: iso(38 * MIN), title: "NVDA proposta long al 4,5%, pronta per il PM", detail: "Conviction 0,72, R:R 2,10.", ticker: "NVDA", ref: { type: "proposal", id: "400" }, severity: "info" },
    { id: "b-prop-407", type: "proposal_decided", ts: iso(20 * H), title: "Il PM ha rimandato JPM", detail: "R:R al limite; rivedere dopo i dati sui tassi.", ticker: "JPM", ref: { type: "proposal", id: "407" }, severity: "info" },
    { id: "b-alert-9", type: "alert", ts: iso(3 * H), title: "Stop di AAPL a 2,2% dal prezzo", detail: null, ticker: "AAPL", ref: { type: "position", id: "AAPL" }, severity: "attention" },
    { id: "b-dossier-msft", type: "dossier", ts: iso(2 * MIN + 30 * MIN), title: "Scheda MSFT aggiornata (v14)", detail: "Il Tecnico e il Fondamentale hanno riscritto le loro sezioni.", ticker: "MSFT", ref: { type: "ticker", id: "MSFT" }, severity: "info" },
    { id: "b-limits-7", type: "risk_limits", ts: iso(13 * H), title: "Vincoli di rischio v7: riserva di cassa al 5%", detail: "Cambiati da Luca: era 8%.", ticker: null, ref: null, severity: "info" },
  ];
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Dev-Fixture", "assistant");
  res.end(JSON.stringify(body));
}

function readBody(req: IncomingMessage): Promise<Row> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        resolve({});
      }
    });
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function assistantFixtures(runtimeUrl: string, mode: string): Plugin {
  const flags = new Set(mode.split(",").map((s) => s.trim()));
  const empty = flags.has("empty");
  const slow = flags.has("slow");
  const nobudget = flags.has("nobudget");
  const s = empty ? { convs: new Map<number, Conv>(), nextMsg: 9000, nextAction: 700 } : seed();
  const convs = s.convs;
  let nextMsg = s.nextMsg;
  let nextAction = s.nextAction;
  let nextConv = 50;
  let seenTs: string | null = empty ? new Date().toISOString() : null;
  const turns = new Map<number, Turn>();

  // --- SSE relay: the Runtime's stream with the fixture's events woven in, ids kept strictly increasing.
  const clients = new Set<ServerResponse>();
  let lastId = 0;
  let seq = 0;
  const emit = (type: string, data: unknown) => {
    seq += 1;
    const id = (lastId + seq / 1e6).toFixed(6);
    for (const c of clients) c.write(`id: ${id}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`);
  };

  const summary = (c: Conv) => {
    const last = c.messages.at(-1);
    return {
      id: c.id,
      title: c.title,
      created_ts: c.created_ts,
      updated_ts: c.updated_ts,
      message_count: c.messages.length,
      status: turns.has(c.id) ? "thinking" : "idle",
      archived: c.archived,
      last_message: last ? { author: last.author, text: last.text || (last.action ? last.action.summary : ""), ts: last.ts } : null,
      pending_actions: c.messages.filter((m) => m.action?.status === "pending").length,
    };
  };
  const touch = (c: Conv, m: Msg) => {
    c.messages.push(m);
    c.updated_ts = m.ts;
    emit("bridge.message", { conversation_id: c.id, message: m });
  };
  const newMsg = (c: Conv, author: string, text: string, extra: Partial<Msg> = {}): Msg => ({
    id: ++nextMsg,
    conversation_id: c.id,
    author,
    kind: "text",
    text,
    ts: new Date().toISOString(),
    context: null,
    refs: [],
    action: null,
    ...extra,
  });
  const status = (c: Conv, st: "thinking" | "tool" | "idle", tool: string | null = null) => {
    const t = turns.get(c.id);
    if (t && st !== "idle") {
      t.status = st;
      t.tool = tool;
    }
    emit("bridge.status", { conversation_id: c.id, status: st, tool });
  };
  const allActions = () => [...convs.values()].flatMap((c) => c.messages.filter((m) => m.action).map((m) => ({ ...m.action!, conversation_id: c.id })));
  const findAction = (id: number) => {
    for (const c of convs.values()) for (const m of c.messages) if (m.action?.id === id) return { c, a: m.action };
    return null;
  };

  /** A scripted Bridge turn: thinking → a tool → thinking → reply (and an action, a relay or an error by keyword). */
  const runTurn = (c: Conv, text: string, ctx: Msg["context"]) => {
    const t: Turn = { status: "thinking", tool: null, timers: [], queued: false };
    turns.set(c.id, t);
    const at = (ms: number, fn: () => void) => t.timers.push(setTimeout(fn, ms));
    const lower = text.toLowerCase();
    const mention = /(?:^|\s)@([a-z_]+)/.exec(lower)?.[1] ?? null;
    const ticker = TICKERS.find((x) => new RegExp(`\\b${x}\\b`, "i").test(text)) ?? ctx?.ticker ?? null;
    const end = () => {
      turns.delete(c.id);
      status(c, "idle");
      emit("bridge.conversation", { conversation: summary(c) });
      if (t.queued) runTurn(c, "(messaggio arrivato durante il turno)", null);
    };

    at(250, () => status(c, "thinking"));
    if (nobudget || /budget/.test(lower)) {
      at(1100, () => {
        touch(c, newMsg(c, "bridge", "Budget giornaliero del Bridge esaurito (2,00 $ su 2,00 $): non posso leggere né rispondere fino a domani alle 00:00 UTC, o finché non alzi il budget del Bridge.", { kind: "error" }));
        end();
      });
      return;
    }
    at(900, () => status(c, "tool", mention ? "message_agent" : ticker ? "read_dossier" : "get_portfolio"));
    at(2200, () => status(c, "tool", ticker ? "get_positions" : "read_events"));
    at(3300, () => status(c, "thinking"));
    at(4300, () => {
      if (mention) {
        touch(c, newMsg(c, "bridge", `Ho scritto ${agentName(mention).replace(/^il /, "al ")} nella sua chat${ticker ? ` ${ticker}` : ""}, per conto tuo. Ti riporto qui la risposta.`, { refs: [{ type: "agent", id: mention, label: null }] }));
        end();
        setTimeout(() => {
          touch(c, newMsg(c, mention, `Ricevuto. ${ticker ? `Su ${ticker} ` : ""}rileggo i dati e aggiorno la mia sezione della scheda entro il prossimo ciclo; per ora non vedo motivi per cambiare la lettura.`, { kind: "agent_relay", refs: ticker ? [{ type: "ticker", id: ticker, label: null }] : [] }));
          runTurnSummary(c, mention);
        }, 5000);
        return;
      }
      if (/chiud|riduc|vend|alleggeri/.test(lower)) {
        const tk = ticker ?? "AAPL";
        const blocked = tk === "AMD";
        touch(c, newMsg(c, "bridge", `Ti propongo l'azione qui sotto: non parte finché non la confermi, e il Runtime ricontrolla tutto al momento dell'esecuzione.`, {
          kind: "action",
          refs: [{ type: "position", id: tk, label: `Posizione ${tk}` }],
          action: {
            id: ++nextAction,
            command: "close_position",
            payload: { ticker: tk, qty: /met[aà]/.test(lower) ? 20 : null, reason: "Richiesta di Luca via Bridge" },
            summary: /met[aà]/.test(lower) ? `Vendita di metà della posizione ${tk} a mercato.` : `Chiusura completa della posizione ${tk} a mercato.`,
            capital: true,
            status: "pending",
            preview: blocked
              ? { ok: false, reasons: ["Nessuna posizione aperta su AMD: niente da chiudere."], detail: null }
              : { ok: true, reasons: ["Tutte le regole del Risk Gate rispettate."], detail: { quantity: 20, price: 229.0, value: 4580, realized_pnl: -154.4 } },
            result_reasons: [],
            decided_ts: null,
            decided_by: null,
          },
        }));
        emit("bridge.action", { conversation_id: c.id, action: c.messages.at(-1)!.action });
        end();
        return;
      }
      touch(c, newMsg(c, "bridge", ticker
        ? `Su ${ticker}: la scheda è alla versione 14, aggiornata 28 minuti fa dall'agente del ticker. Tesi long con conviction 0,72; il Tecnico vede supporto a 171,6 e il Rischio conferma lo stop entro l'1% del capitale. Nessun ordine aperto. Se vuoi, chiedo al Tecnico di rivedere i livelli.`
        : "Dall'ultima visita: portafoglio +0,4%, nessun trade nuovo, due proposte in attesa del PM (NVDA pronta, AMD bloccata dal Risk Gate per il settore). L'unica cosa che richiede te è l'ordine AAPL in approvazione manuale.", {
        refs: ticker ? [{ type: "ticker", id: ticker, label: null }] : [{ type: "proposal", id: "400", label: "Proposta NVDA #400" }, { type: "order", id: "118", label: null }],
      }));
      if (c.title.startsWith("Nuova") || c.messages.length <= 2) {
        c.title = ticker ? `Domande su ${ticker}` : "Cosa è successo oggi";
      }
      end();
    });
  };

  const runTurnSummary = (c: Conv, agent: string) => {
    const t: Turn = { status: "thinking", tool: null, timers: [], queued: false };
    turns.set(c.id, t);
    status(c, "thinking");
    t.timers.push(
      setTimeout(() => {
        touch(c, newMsg(c, "bridge", `In breve: ${agentName(agent)} non cambia la sua lettura per ora e aggiornerà la scheda al prossimo ciclo. Ti avviso qui se cambia qualcosa.`));
        turns.delete(c.id);
        status(c, "idle");
      }, 1800),
    );
  };

  const briefing = () => {
    const since = seenTs ?? iso(14 * H);
    const items = empty ? [] : briefingItems().filter((i) => Date.parse(String(i.ts)) > Date.parse(since));
    const count = (t: string) => items.filter((i) => i.type === t).length;
    return {
      since,
      generated_ts: new Date().toISOString(),
      summary_text: nobudget || !items.length ? null : "Notte tranquilla sul portafoglio (+0,4%). Due proposte aspettano il PM: NVDA è pronta, AMD è bloccata dal Risk Gate per l'esposizione al settore. Il Sentiment ha fallito due volte sul provider notizie, e l'ordine AAPL attende la tua approvazione.",
      summary_ts: nobudget || !items.length ? null : iso(12 * MIN),
      portfolio: { value: 101284.12, change: 402.9, change_fraction: 0.004 },
      counts: {
        trades: count("trade"),
        orders_pending: count("order_pending"),
        proposals_pending: count("proposal_pending"),
        proposals_decided: count("proposal_decided"),
        alerts: count("alert"),
        agent_errors: count("agent_error"),
      },
      items: items.sort((a, b) => Date.parse(String(b.ts)) - Date.parse(String(a.ts))),
    };
  };

  const halted = async () => {
    try {
      const h = (await (await fetch(`${runtimeUrl}/v1/health`)).json()) as Row;
      return h.halted === true;
    } catch {
      return false;
    }
  };

  return {
    name: "cockpit-assistant-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info(`  ⚠ Assistente: fixture di sviluppo attive per il Bridge (COCKPIT_ASSISTANT_FIXTURES=${mode})`);
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        const p = url.pathname;
        const q = (k: string) => url.searchParams.get(k);

        if (req.method === "GET" && p === "/v1/events") {
          const raw = q("after") ?? (req.headers["last-event-id"] as string | undefined) ?? "";
          const after = raw === "" ? NaN : Math.floor(Number(raw));
          if (Number.isFinite(after) && after > lastId) {
            lastId = after;
            seq = 0;
          }
          const up = new URL("/v1/events", runtimeUrl);
          if (Number.isFinite(after)) up.searchParams.set("after", String(after));
          const upReq = http.get(up, (upRes) => {
            if ((upRes.statusCode ?? 500) >= 400) {
              res.statusCode = upRes.statusCode ?? 502;
              upRes.pipe(res);
              return;
            }
            res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
            res.flushHeaders();
            clients.add(res);
            let buf = "";
            upRes.setEncoding("utf8");
            upRes.on("data", (chunk: string) => {
              buf += chunk;
              let i: number;
              // Forward whole events only, so a woven-in event never lands inside one.
              while ((i = buf.indexOf("\n\n")) >= 0) {
                const evt = buf.slice(0, i + 2);
                buf = buf.slice(i + 2);
                const m = /^id:\s*(\d+)/m.exec(evt);
                if (m && Number(m[1]) > lastId) {
                  lastId = Number(m[1]);
                  seq = 0;
                }
                res.write(evt);
              }
            });
            upRes.on("end", () => {
              clients.delete(res);
              res.end();
            });
          });
          upReq.on("error", () => {
            clients.delete(res);
            if (!res.headersSent) send(res, 502, { detail: "Runtime irraggiungibile" });
            else res.end();
          });
          req.on("close", () => {
            clients.delete(res);
            upReq.destroy();
          });
          return;
        }

        const isRead = req.method === "GET" && /^\/v1\/read\/(bridge_conversations|bridge_conversation|bridge_actions|briefing)$/.test(p);
        if (isRead && slow) await sleep(2500);

        if (req.method === "GET" && p === "/v1/read/bridge_conversations") {
          const archived = q("archived") === "true";
          const term = (q("q") ?? "").toLowerCase();
          const rows = [...convs.values()]
            .filter((c) => c.archived === archived)
            .filter((c) => !term || c.title.toLowerCase().includes(term) || c.messages.some((m) => m.text.toLowerCase().includes(term)))
            .sort((a, b) => Date.parse(b.updated_ts) - Date.parse(a.updated_ts))
            .slice(0, Number(q("limit") ?? 100))
            .map(summary);
          return send(res, 200, rows);
        }
        if (req.method === "GET" && p === "/v1/read/bridge_conversation") {
          const c = convs.get(Number(q("id")));
          if (!c) return send(res, 404, { detail: `Conversazione ${q("id")} inesistente` });
          const limit = Number(q("limit") ?? 100);
          return send(res, 200, { id: c.id, title: c.title, created_ts: c.created_ts, updated_ts: c.updated_ts, status: turns.has(c.id) ? "thinking" : "idle", archived: c.archived, messages: c.messages.slice(-limit) });
        }
        if (req.method === "GET" && p === "/v1/read/bridge_actions") {
          return send(res, 200, allActions().filter((a) => !q("status") || a.status === q("status")));
        }
        if (req.method === "GET" && p === "/v1/read/briefing") return send(res, 200, briefing());

        if (req.method === "POST" && p.startsWith("/v1/commands/")) {
          const name = p.slice("/v1/commands/".length);
          if (!["bridge_say", "bridge_stop", "bridge_rename_conversation", "bridge_archive_conversation", "bridge_action_decide", "mark_briefing_seen"].includes(name)) return next();
          const body = await readBody(req);
          const refuse = (...reasons: string[]) => send(res, 200, { ok: false, data: {}, reasons });

          if (name === "bridge_say") {
            const text = String(body.text ?? "").trim();
            if (!text) return refuse("Il messaggio è vuoto");
            let c = body.conversation_id === null || body.conversation_id === undefined ? null : convs.get(Number(body.conversation_id));
            if (body.conversation_id !== null && body.conversation_id !== undefined && !c) return refuse(`Conversazione ${body.conversation_id} inesistente`);
            if (!c) {
              const id = ++nextConv;
              c = { id, title: text.split(/\s+/).slice(0, 6).join(" "), created_ts: new Date().toISOString(), updated_ts: new Date().toISOString(), archived: false, messages: [] };
              convs.set(id, c);
              emit("bridge.conversation", { conversation: summary(c) });
            }
            const ctx = (body.context ?? null) as Msg["context"];
            const m = newMsg(c, "luca", text, { context: ctx });
            touch(c, m);
            const running = turns.get(c.id);
            if (running) running.queued = true;
            else runTurn(c, text, ctx);
            return send(res, 200, { ok: true, data: { conversation_id: c.id, message_id: m.id }, reasons: [] });
          }
          if (name === "bridge_stop") {
            const c = convs.get(Number(body.conversation_id));
            if (!c) return refuse(`Conversazione ${body.conversation_id} inesistente`);
            const t = turns.get(c.id);
            if (!t) return refuse("Nessun turno in corso in questa conversazione");
            t.timers.forEach(clearTimeout);
            turns.delete(c.id);
            touch(c, newMsg(c, "bridge", "Mi fermo qui, come hai chiesto. Riprendo dal tuo prossimo messaggio."));
            status(c, "idle");
            return send(res, 200, { ok: true, data: { conversation_id: c.id }, reasons: [] });
          }
          if (name === "bridge_rename_conversation") {
            const c = convs.get(Number(body.conversation_id));
            const title = String(body.title ?? "").trim();
            if (!c) return refuse(`Conversazione ${body.conversation_id} inesistente`);
            if (!title) return refuse("Il titolo è vuoto");
            c.title = title.slice(0, 120);
            emit("bridge.conversation", { conversation: summary(c) });
            return send(res, 200, { ok: true, data: { conversation_id: c.id }, reasons: [] });
          }
          if (name === "bridge_archive_conversation") {
            const c = convs.get(Number(body.conversation_id));
            if (!c) return refuse(`Conversazione ${body.conversation_id} inesistente`);
            c.archived = body.archived === true;
            emit("bridge.conversation", { conversation: summary(c) });
            return send(res, 200, { ok: true, data: { conversation_id: c.id }, reasons: [] });
          }
          if (name === "mark_briefing_seen") {
            seenTs = String(body.ts ?? new Date().toISOString());
            emit("briefing.updated", { since: seenTs });
            return send(res, 200, { ok: true, data: { since: seenTs }, reasons: [] });
          }
          if (name === "bridge_action_decide") {
            const hit = findAction(Number(body.action_id));
            if (!hit) return refuse(`Azione #${body.action_id} inesistente`);
            const { c, a } = hit;
            if (body.decision !== "confirm" && body.decision !== "dismiss") return refuse(`Decisione non valida: ${body.decision}`);
            if (body.decision === "confirm" && body.confirm !== true) return refuse("Per eseguire un'azione con capitale serve confirm: true");
            if (a.status !== "pending") return refuse(`L'azione è già ${a.status}`);
            const now = new Date().toISOString();
            if (body.decision === "dismiss") {
              Object.assign(a, { status: "dismissed", decided_ts: now, decided_by: "luca" });
              emit("bridge.action", { conversation_id: c.id, action: a });
              touch(c, newMsg(c, "bridge", "Annullata: non ho eseguito nulla."));
              return send(res, 200, { ok: true, data: { action_id: a.id, status: a.status }, reasons: [] });
            }
            Object.assign(a, { status: "confirmed", decided_ts: now, decided_by: "luca" });
            emit("bridge.action", { conversation_id: c.id, action: a });
            const isHalted = ORDER_COMMANDS.has(a.command) && (await halted());
            setTimeout(() => {
              if (isHalted) Object.assign(a, { status: "failed", result_reasons: ["Halt attivo: nessun ordine viene inviato al broker. Riprendi il trading e chiedimelo di nuovo."] });
              else if (a.preview && !a.preview.ok) Object.assign(a, { status: "failed", result_reasons: a.preview.reasons.map((r) => `Risk Gate: ${r}`) });
              else
                Object.assign(a, {
                  status: "executed",
                  result_reasons: [a.command === "close_position" ? `Ordine di vendita inviato al broker: ${a.payload.qty ?? "tutte le"} azioni ${a.payload.ticker} a mercato.` : "Comando eseguito dal Runtime."],
                });
              emit("bridge.action", { conversation_id: c.id, action: a });
              touch(c, newMsg(c, "bridge", a.status === "executed" ? "Eseguita. Il Portafoglio si aggiorna appena il broker conferma il fill." : `Non è partita: ${a.result_reasons.join(" ")}`));
            }, 1200);
            return send(res, 200, { ok: true, data: { action_id: a.id, status: "confirmed" }, reasons: [] });
          }
        }
        next();
      });
    },
  };
}
