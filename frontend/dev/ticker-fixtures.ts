// Development only. Answers the ticker-agent reads and commands the Runtime does not expose yet
// (`dossier`, `dossier_history`, `proposals`, `dossiers`, ticker agents in `agents`, their chats and tools,
// `add_dossier_note`, `decide_proposal`) with synthetic data shaped exactly like the binding contract in
// .scratch/ticker-agents/handoff-backend.md. Enabled only by `COCKPIT_TICKER_FIXTURES=1` (or `=dense` for
// 40 tickers) on `vite` serve: it never reaches a build. Everything else stays the real (synthetic) Runtime.
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

const MIN = 60_000;
const H = 60 * MIN;
const D = 24 * H;
const iso = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();
const day = (offsetDays: number) => new Date(Date.now() + offsetDays * D).toISOString().slice(0, 10);

type Row = Record<string, unknown>;
type AgentState = "working" | "waiting" | "idle";

type Seed = {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  price: number;
  cap: number;
  status: string;
  agent: AgentState | null;
  label?: string;
  direction?: string;
  conviction?: number;
  proposal?: { status: string; sizing: number; rr: number; entry: number; stop: number; target: number; ageMin: number; reason?: string; decidedBy?: string };
  risk?: "pass" | "blocked";
  invested?: { qty: number; avg: number; weight: number; pnl: number };
  empty?: boolean;
  costToday?: number;
  lastMin: number;
};

const SEEDS: Seed[] = [
  { ticker: "NVDA", name: "NVIDIA Corporation", sector: "Tecnologia", industry: "Semiconduttori", price: 181.0, cap: 4.41e12, status: "proposed", agent: "working", label: "Risponde alle domande del PM sul sizing", direction: "long", conviction: 0.72, proposal: { status: "pending", sizing: 0.045, rr: 2.1, entry: 180.2, stop: 171.6, target: 198.4, ageMin: 38 }, risk: "pass", costToday: 0.42, lastMin: 1 },
  { ticker: "AMD", name: "Advanced Micro Devices", sector: "Tecnologia", industry: "Semiconduttori", price: 166.4, cap: 2.69e11, status: "proposed", agent: "waiting", label: "Attende la decisione del PM", direction: "long", conviction: 0.61, proposal: { status: "pending", sizing: 0.04, rr: 1.7, entry: 165.8, stop: 158.9, target: 177.5, ageMin: 112 }, risk: "blocked", costToday: 0.31, lastMin: 14 },
  { ticker: "AVGO", name: "Broadcom Inc.", sector: "Tecnologia", industry: "Semiconduttori", price: 342.1, cap: 1.6e12, status: "proposed", agent: "waiting", label: "Proposta inviata al PM", direction: "long", conviction: 0.58, proposal: { status: "pending", sizing: 0.03, rr: 1.6, entry: 340.0, stop: 326.5, target: 361.6, ageMin: 9 }, risk: "pass", costToday: 0.27, lastMin: 9 },
  { ticker: "MSFT", name: "Microsoft Corporation", sector: "Tecnologia", industry: "Software", price: 512.3, cap: 3.81e12, status: "analyzing", agent: "working", label: "Raccoglie le analisi degli specialist", direction: "long", conviction: 0.55, costToday: 0.22, lastMin: 2 },
  { ticker: "GOOGL", name: "Alphabet Inc.", sector: "Comunicazione", industry: "Servizi internet", price: 247.8, cap: 3.0e12, status: "analyzing", agent: "working", label: "Chiede al Fondamentale i margini del cloud", costToday: 0.18, lastMin: 4 },
  { ticker: "AAPL", name: "Apple Inc.", sector: "Tecnologia", industry: "Hardware", price: 229.0, cap: 3.4e12, status: "monitoring", agent: "idle", direction: "long", conviction: 0.48, proposal: { status: "accepted", sizing: 0.09, rr: 1.9, entry: 236.7, stop: 224.0, target: 260.8, ageMin: 6 * D / MIN, decidedBy: "portfolio_manager", reason: "Coerente con il peso tech; sizing ridotto al 9%." }, risk: "pass", invested: { qty: 40, avg: 236.72, weight: 0.092, pnl: -308.8 }, costToday: 0.04, lastMin: 5 * 60 },
  { ticker: "LLY", name: "Eli Lilly and Company", sector: "Sanità", industry: "Farmaceutica", price: 812.0, cap: 7.7e11, status: "monitoring", agent: "idle", direction: "long", conviction: 0.66, proposal: { status: "accepted", sizing: 0.05, rr: 2.4, entry: 774.6, stop: 741.0, target: 855.0, ageMin: 9 * D / MIN, decidedBy: "portfolio_manager", reason: "Diversifica fuori dal tech." }, risk: "pass", invested: { qty: 6, avg: 774.62, weight: 0.049, pnl: 224.28 }, costToday: 0.02, lastMin: 20 * 60 },
  { ticker: "JPM", name: "JPMorgan Chase & Co.", sector: "Finanza", industry: "Banche", price: 298.5, cap: 8.3e11, status: "idle", agent: "idle", direction: "long", conviction: 0.44, proposal: { status: "deferred", sizing: 0.03, rr: 1.5, entry: 297.0, stop: 288.0, target: 310.5, ageMin: 2 * D / MIN, decidedBy: "portfolio_manager", reason: "R:R al limite; rivedere dopo i dati sui tassi." }, risk: "pass", costToday: 0, lastMin: 2 * 24 * 60 },
  { ticker: "TSLA", name: "Tesla, Inc.", sector: "Consumi discrezionali", industry: "Auto", price: 402.7, cap: 1.3e12, status: "declined", agent: "idle", direction: "long", conviction: 0.39, proposal: { status: "rejected", sizing: 0.03, rr: 1.3, entry: 400.0, stop: 380.0, target: 426.0, ageMin: 3 * D / MIN, decidedBy: "luca", reason: "Troppa volatilità attorno alle consegne." }, risk: "blocked", costToday: 0, lastMin: 3 * 24 * 60 },
  { ticker: "META", name: "Meta Platforms, Inc.", sector: "Comunicazione", industry: "Servizi internet", price: 688.2, cap: 1.7e12, status: "analyzing", agent: "waiting", label: "Il PM ha chiesto dati sul capex", direction: "long", conviction: 0.57, proposal: { status: "asked", sizing: 0.035, rr: 1.8, entry: 685.0, stop: 660.0, target: 730.0, ageMin: 5 * H / MIN, decidedBy: "portfolio_manager", reason: "Quanto pesa il capex 2027 sul free cash flow?" }, risk: "pass", costToday: 0.11, lastMin: 47 },
  { ticker: "COST", name: "Costco Wholesale", sector: "Beni di prima necessità", industry: "Distribuzione", price: 951.4, cap: 4.2e11, status: "idle", agent: "idle", costToday: 0, lastMin: 6 * 24 * 60 },
  { ticker: "XOM", name: "Exxon Mobil Corporation", sector: "Energia", industry: "Petrolio e gas", price: 112.6, cap: 4.8e11, status: "idle", agent: null, empty: true, lastMin: 0 },
];

const DENSE_EXTRA = "ORCL CRM ADBE INTC QCOM TXN MU AMAT LRCX KLAC SNPS CDNS PANW CRWD NOW UBER SHOP NFLX DIS PEP KO WMT HD UNH ABBV MRK".split(" ");

function seeds(dense: boolean): Seed[] {
  if (!dense) return SEEDS;
  const states: AgentState[] = ["idle", "idle", "working", "waiting", "idle"];
  const extra = DENSE_EXTRA.slice(0, 40 - SEEDS.length).map<Seed>((t, i) => ({
    ticker: t,
    name: `${t} (sintetico)`,
    sector: ["Tecnologia", "Sanità", "Consumi", "Finanza"][i % 4],
    industry: "—",
    price: 50 + ((i * 37) % 400),
    cap: 1e11,
    status: ["idle", "monitoring", "analyzing", "idle"][i % 4],
    agent: states[i % states.length],
    direction: i % 3 ? "long" : undefined,
    conviction: i % 3 ? 0.4 + (i % 5) / 10 : undefined,
    costToday: i % 3 ? 0.05 + (i % 4) / 50 : 0,
    lastMin: 5 + i * 41,
  }));
  return [...SEEDS, ...extra];
}

const SPECIALISTS = ["technical_analyst", "market_analyst", "sentiment_analyst", "fundamental_analyst", "risk_analyst"];

function desks(s: Seed): Row[] {
  if (s.empty) return [];
  const t = s.ticker;
  const base: Row[] = [
    { agent: "technical_analyst", section: "technical", text: `${t} ha chiuso sopra la media a 50 giorni con volumi 1,4 volte la media; supporto a ${(s.price * 0.95).toFixed(1)}, resistenza a ${(s.price * 1.08).toFixed(1)}. RSI 61, nessuna divergenza.`, ts: iso(35 * MIN), reference_date: day(0), confidence: 0.8, status: "active" },
    { agent: "market_analyst", section: "market", text: `Settore ${s.industry.toLowerCase()} in rotazione positiva da tre sedute; flussi ETF di settore +2,1% nella settimana. Beta 1,3 rispetto all'S&P 500.`, ts: iso(52 * MIN), reference_date: day(0), confidence: 0.62, status: "active" },
    ["NVDA", "AMD", "AAPL"].includes(t)
      ? { agent: "sentiment_analyst", section: "sentiment", text: `Tono delle notizie neutro; due downgrade minori dopo la trimestrale, nessun evento regolatorio aperto.`, ts: iso(11 * D), reference_date: day(-11), confidence: 0.55, status: "stale" }
      : { agent: "sentiment_analyst", section: "sentiment", text: `Tono delle notizie moderatamente positivo: tre upgrade nell'ultima settimana, nessun evento regolatorio aperto.`, ts: iso(5 * H), reference_date: day(0), confidence: 0.58, status: "active" },
    { agent: "fundamental_analyst", section: "fundamental", text: `Ricavi +18% a/a, margine operativo 34%; P/E forward 31 contro 27 di settore. Guidance alzata per il trimestre in corso.`, ts: iso(3 * H), reference_date: day(-2), confidence: 0.7, status: "active" },
    { agent: "fundamental_analyst", section: "fundamental", text: `Ricavi attesi +12% a/a; margini sotto pressione per il mix di prodotto.`, ts: iso(16 * D), reference_date: day(-30), confidence: 0.6, status: "superseded" },
    { agent: "risk_analyst", section: "risk", text: s.risk === "blocked" ? `Con questa posizione l'esposizione al settore salirebbe al 34%, oltre il limite del 30%. ATR 14 al 3,1%: stop coerente con il rischio dell'1%.` : `ATR 14 al 2,4% del prezzo: lo stop proposto rispetta il rischio dell'1% del capitale. Correlazione 0,71 con le posizioni tech aperte.`, ts: iso(40 * MIN), reference_date: day(0), confidence: 0.88, status: "active" },
  ];
  if (s.status === "analyzing") return base.filter((d) => d.agent !== "risk_analyst");
  return base;
}

function thesis(s: Seed): Row | null {
  if (!s.direction || s.empty) return null;
  return {
    direction: s.direction,
    conviction: s.conviction ?? null,
    pro: ["Domanda in accelerazione e guidance alzata", "Rottura tecnica con volumi sopra la media", "Rotazione positiva del settore"],
    contro: ["Valutazione sopra la media di settore", "Sentiment non aggiornato da 11 giorni", s.risk === "blocked" ? "Esposizione al settore già vicina al limite" : "Correlazione alta con le posizioni aperte"],
    time_horizon: "4–8 settimane",
    catalysts: [
      { text: "Trimestrale", date: day(9) },
      { text: "Dati sull'inflazione USA (CPI)", date: day(3) },
      { text: "Investor day", date: day(24) },
    ],
    next_check_date: day(2),
    author: `ticker:${s.ticker}`,
    ts: iso(28 * MIN),
  };
}

function proposalOf(s: Seed, id: number): Row | null {
  const p = s.proposal;
  if (!p) return null;
  return { id, status: p.status, k_entry: 0.42, k_stop: 1.8, k_tp: 3.6, entry_price: p.entry, stop_price: p.stop, target_price: p.target, sizing_fraction: p.sizing, risk_reward: p.rr, submitted_ts: iso(p.ageMin * MIN) };
}

function riskOf(s: Seed): Row | null {
  if (!s.proposal) return null;
  const blocked = s.risk === "blocked";
  const rr = s.proposal.rr;
  return {
    verdict: blocked ? "rejected" : "pass",
    rationale: blocked ? "Bloccata: la posizione porterebbe l'esposizione al settore oltre il 30%." : "Tutte le regole rispettate.",
    guardrails: [
      { rule: "Rischio per trade ≤ 1%", ok: true, detail: "0,92% del capitale" },
      { rule: "Posizione ≤ 10%", ok: true, detail: `${(s.proposal.sizing * 100).toFixed(1).replace(".", ",")}% del capitale` },
      { rule: "Settore ≤ 30%", ok: !blocked, detail: blocked ? "34% dopo l'ingresso" : "21% dopo l'ingresso" },
      { rule: "Posizioni aperte ≤ 30", ok: true, detail: "3 di 30" },
      { rule: "Riserva di cassa ≥ 5%", ok: true, detail: "81% di cassa" },
      { rule: "R:R ≥ 1,5", ok: rr >= 1.5, detail: rr.toFixed(2).replace(".", ",") },
      { rule: "Embargo trimestrale 2 giorni", ok: true, detail: "trimestrale tra 9 giorni" },
    ],
  };
}

type State = {
  dense: boolean;
  notes: Map<string, Row[]>;
  decided: Map<number, { status: string; by: string; reason: string; ts: string }>;
  extraDecisions: Map<string, Row[]>;
  version: Map<string, number>;
};

const PROPOSAL_ID = (i: number) => 400 + i;

function dossierOf(st: State, s: Seed, i: number): Row {
  const pid = PROPOSAL_ID(i);
  const decided = st.decided.get(pid);
  const proposal = proposalOf(s, pid);
  if (proposal && decided) proposal.status = decided.status;
  const ds = desks(s);
  const decisions: Row[] = [];
  if (s.proposal && s.proposal.status !== "pending" && s.proposal.decidedBy) {
    decisions.push({ ts: iso(s.proposal.ageMin * MIN - 20 * MIN), actor: s.proposal.decidedBy, action: { accepted: "accept", deferred: "defer", rejected: "reject", asked: "ask" }[s.proposal.status] ?? s.proposal.status, reason: s.proposal.reason ?? null, cycle_id: 10 + i });
  }
  if (s.proposal) decisions.push({ ts: iso(s.proposal.ageMin * MIN), actor: `ticker:${s.ticker}`, action: "submit", reason: `Proposta ${s.direction ?? ""} con conviction ${(s.conviction ?? 0).toFixed(2).replace(".", ",")}`.trim(), cycle_id: 10 + i });
  if (!s.empty && s.ticker !== "GOOGL") decisions.push({ ts: iso(14 * D), actor: "portfolio_manager", action: "defer", reason: "Attendere la trimestrale prima di entrare.", cycle_id: 3 + i });
  decisions.unshift(...(st.extraDecisions.get(s.ticker) ?? []));
  const status = decided ? (decided.status === "accepted" ? "approved" : decided.status === "rejected" ? "declined" : decided.status === "asked" ? "analyzing" : "idle") : s.status;
  const notes = st.notes.get(s.ticker) ?? (s.ticker === "NVDA" ? [{ id: 1, author: "luca", text: "Occhio all'export verso la Cina: un nuovo limite cambierebbe la tesi più di qualunque numero della trimestrale.", ts: iso(26 * H) }] : []);
  return {
    ticker: s.ticker,
    version: st.version.get(s.ticker) ?? (s.empty ? 1 : 14),
    updated_ts: s.empty ? iso(4 * D) : iso(s.lastMin * MIN),
    updated_by: s.empty ? "system" : `ticker:${s.ticker}`,
    status,
    identity: { name: s.name, sector: s.sector, industry: s.industry, market_cap: s.cap, currency: "USD", current_price: s.price, as_of: iso(2 * MIN) },
    portfolio: s.invested
      ? { invested: true, qty: s.invested.qty, position_weight: s.invested.weight, avg_entry_price: s.invested.avg, unrealized_pnl: s.invested.pnl, sector_exposure: 0.21, cash_fraction: 0.86 }
      : { invested: false, qty: null, position_weight: null, avg_entry_price: null, unrealized_pnl: null, sector_exposure: s.risk === "blocked" ? 0.27 : 0.14, cash_fraction: 0.86 },
    desks: ds,
    thesis: thesis(s),
    proposal,
    risk: riskOf(s),
    decisions: decisions.sort((a, b) => Date.parse(String(b.ts)) - Date.parse(String(a.ts))),
    lessons:
      s.ticker === "AAPL" || s.ticker === "NVDA"
        ? [
            { ts: iso(21 * D), text: "Ingresso prima della trimestrale: lo stop troppo stretto è scattato sul gap di apertura.", exit_reason: "stop_loss" },
            { ts: iso(48 * D), text: "Target raggiunto in 6 sedute: la rottura con volumi era un segnale affidabile.", exit_reason: "take_profit" },
          ]
        : [],
    notes,
    stale_count: ds.filter((d) => d.status === "stale").length,
  };
}

function history(s: Seed): Row[] {
  if (s.empty) return [{ version: 1, ts: iso(4 * D), author: "system", sections_changed: ["identity"] }];
  const rows: Row[] = [
    { version: 14, ts: iso(28 * MIN), author: `ticker:${s.ticker}`, sections_changed: ["thesis", "proposal"] },
    { version: 13, ts: iso(35 * MIN), author: "technical_analyst", sections_changed: ["technical"] },
    { version: 12, ts: iso(40 * MIN), author: "risk_analyst", sections_changed: ["risk"] },
    { version: 11, ts: iso(52 * MIN), author: "market_analyst", sections_changed: ["market"] },
    { version: 10, ts: iso(3 * H), author: "fundamental_analyst", sections_changed: ["fundamental"] },
    { version: 9, ts: iso(26 * H), author: "luca", sections_changed: ["notes"] },
    { version: 8, ts: iso(11 * D), author: "sentiment_analyst", sections_changed: ["sentiment"] },
    { version: 7, ts: iso(14 * D), author: "portfolio_manager", sections_changed: ["decisions"] },
  ];
  return rows;
}

function agents(st: State, upstream: Row[]): Row[] {
  const core = upstream.map((a) => ({ ...a, kind: "core", ticker: null, supervisor: null }));
  const list = seeds(st.dense);
  const tickers = list
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.agent)
    .map(({ s, i }) => {
      const cost = s.costToday ?? 0;
      return {
        name: `ticker:${s.ticker}`,
        role: "ticker_agent",
        model: "my-combo",
        kind: "ticker",
        ticker: s.ticker,
        supervisor: "portfolio_manager",
        status: s.agent,
        current_task: s.agent === "idle" ? null : { type: "cycle", ticker: s.ticker, cycle_id: 10 + i, description: s.label ?? "Ciclo di analisi" },
        last_activity_ts: iso(s.lastMin * MIN),
        today_tokens_in: Math.round(cost * 210_000),
        today_tokens_out: Math.round(cost * 19_000),
        today_tokens: Math.round(cost * 229_000),
        today_cost: cost,
      };
    });
  return [...core, ...tickers];
}

function chat(s: Seed): Row[] {
  const t = s.ticker;
  const a = `ticker:${t}`;
  const base = 9000 + t.charCodeAt(0) * 10;
  const msgs: [string, number, string][] = [
    [a, 70, `Apro il ciclo su ${t}. @technical_analyst livelli e struttura sul giornaliero; @fundamental_analyst aggiornamento dopo la guidance; @risk_analyst esposizione se entriamo con il 4–5%.`],
    ["technical_analyst", 64, `Chiusura sopra la media a 50 con volumi 1,4×. Supporto ${(s.price * 0.95).toFixed(1)}, resistenza ${(s.price * 1.08).toFixed(1)}. Struttura rialzista finché tiene il supporto.`],
    ["fundamental_analyst", 58, "Guidance alzata, margine operativo al 34%. Il multiplo è sopra il settore ma giustificato dalla crescita."],
    ["risk_analyst", 45, s.risk === "blocked" ? "Attenzione: con il 4% il settore arriva al 34%, oltre il limite del 30%. Il Risk Gate la bloccherebbe." : "ATR 2,4%: con lo stop proposto il rischio resta sotto l'1%. Correlazione alta con il tech già in portafoglio."],
    [a, 38, s.proposal ? `Scrivo tesi e proposta nella scheda: ${s.direction} con conviction ${(s.conviction ?? 0).toFixed(2).replace(".", ",")}, R:R ${s.proposal.rr.toFixed(1).replace(".", ",")}. La sottopongo al PM.` : "Tesi ancora aperta: aspetto il sentiment aggiornato prima di proporre."],
  ];
  if (s.ticker === "NVDA") msgs.push(["portfolio_manager", 6, "Prima di decidere: il 4,5% ci lascia margine sul settore? Valuta anche il 3,5%."], [a, 1, "Con il 3,5% il settore resta al 19%; la tesi regge, R:R invariato. Aggiorno la proposta se preferisci il sizing ridotto."]);
  return msgs.map(([author, minAgo, text], k) => ({ id: base + k, chat_id: base, author, ts: iso(minAgo * MIN), text, kind: "message", cycle_id: 10 }));
}

function toolCalls(s: Seed): Row[] {
  const a = `ticker:${s.ticker}`;
  return [
    { id: 7001, ts: iso(1 * MIN), tool: "read_dossier", params: { ticker: s.ticker }, result: { version: 14 }, status: "ok", duration_ms: 38 },
    { id: 7000, ts: iso(28 * MIN), tool: "submit_proposal", params: { ticker: s.ticker, direction: s.direction ?? "long", sizing_fraction: s.proposal?.sizing ?? 0.04 }, result: { ok: true, proposal_id: 400 }, status: "ok", duration_ms: 112 },
    { id: 6999, ts: iso(29 * MIN), tool: "write_thesis", params: { ticker: s.ticker, conviction: s.conviction ?? 0.5 }, result: { version: 14 }, status: "ok", duration_ms: 64 },
    { id: 6998, ts: iso(70 * MIN), tool: "say", params: { to: ["technical_analyst", "fundamental_analyst", "risk_analyst"], chat: s.ticker }, result: { ok: true }, status: "ok", duration_ms: 21 },
  ].map((c) => ({ agent: a, topic: s.ticker, cycle_id: 10, error: null, compacted: { params: false, result: false, at: null }, ...c }));
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Dev-Fixture", "ticker-agents");
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

export function tickerFixtures(runtimeUrl: string, mode: string): Plugin {
  const st: State = { dense: mode === "dense", notes: new Map(), decided: new Map(), extraDecisions: new Map(), version: new Map() };
  const find = (t: string | null) => {
    const list = seeds(st.dense);
    const i = list.findIndex((s) => s.ticker === (t ?? "").toUpperCase());
    return i < 0 ? null : { s: list[i], i };
  };
  const bump = (t: string) => st.version.set(t, (st.version.get(t) ?? 14) + 1);

  return {
    name: "cockpit-ticker-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info(`  ⚠ Agenti del ticker: fixture di sviluppo attive (COCKPIT_TICKER_FIXTURES=${mode})`);
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        const p = url.pathname;
        const q = (k: string) => url.searchParams.get(k);
        const tickerAgent = /^ticker:/i.test(q("agent") ?? "") ? find((q("agent") ?? "").slice(7)) : null;

        if (req.method === "GET" && p === "/v1/read/agents") {
          try {
            const up = (await (await fetch(`${runtimeUrl}/v1/read/agents`)).json()) as Row[];
            return send(res, 200, agents(st, Array.isArray(up) ? up : []));
          } catch {
            return send(res, 502, { detail: "Runtime irraggiungibile" });
          }
        }
        if (req.method === "GET" && p === "/v1/read/dossier") {
          const hit = find(q("ticker"));
          return hit ? send(res, 200, dossierOf(st, hit.s, hit.i)) : send(res, 404, { detail: `Nessuna scheda per ${q("ticker")}` });
        }
        if (req.method === "GET" && p === "/v1/read/dossier_history") {
          const hit = find(q("ticker"));
          if (!hit) return send(res, 200, []);
          const extra = Array.from({ length: (st.version.get(hit.s.ticker) ?? 14) - 14 }, (_, k) => ({ version: 15 + k, ts: iso(0), author: "luca", sections_changed: ["notes"] })).reverse();
          return send(res, 200, [...extra, ...history(hit.s)].slice(0, Number(q("limit") ?? 30)));
        }
        if (req.method === "GET" && p === "/v1/read/dossiers") {
          return send(
            res,
            200,
            seeds(st.dense).map((s, i) => {
              const d = dossierOf(st, s, i);
              return { ticker: s.ticker, status: d.status, direction: s.direction ?? null, conviction: s.conviction ?? null, proposal_status: (d.proposal as Row | null)?.status ?? null, updated_ts: d.updated_ts, stale_count: d.stale_count, invested: !!s.invested };
            }),
          );
        }
        if (req.method === "GET" && p === "/v1/read/proposals") {
          const rows = seeds(st.dense)
            .map((s, i) => ({ s, i }))
            .filter(({ s }) => s.proposal)
            .map(({ s, i }) => {
              const pid = PROPOSAL_ID(i);
              const dec = st.decided.get(pid);
              const pr = s.proposal!;
              return {
                id: pid,
                ticker: s.ticker,
                agent: `ticker:${s.ticker}`,
                status: dec?.status ?? pr.status,
                direction: s.direction ?? null,
                conviction: s.conviction ?? null,
                sizing_fraction: pr.sizing,
                risk_reward: pr.rr,
                submitted_ts: iso(pr.ageMin * MIN),
                decided_ts: dec?.ts ?? (pr.status === "pending" ? null : iso(pr.ageMin * MIN - 20 * MIN)),
                decided_by: dec?.by ?? pr.decidedBy ?? null,
                reason: dec?.reason ?? pr.reason ?? null,
                cycle_id: 10 + i,
              };
            })
            .filter((r) => (!q("status") || r.status === q("status")) && (!q("ticker") || r.ticker === q("ticker")?.toUpperCase()))
            .sort((a, b) => Date.parse(a.submitted_ts) - Date.parse(b.submitted_ts));
          return send(res, 200, rows.slice(0, Number(q("limit") ?? 100)));
        }
        if (req.method === "GET" && tickerAgent && p === "/v1/read/chat_topics") {
          const last = chat(tickerAgent.s).at(-1)!;
          return send(res, 200, [{ chat_id: last.chat_id, topic: tickerAgent.s.ticker, title: tickerAgent.s.ticker, ticker: tickerAgent.s.ticker, cycle_id: 10, last_message: { author: last.author, text: last.text, ts: last.ts }, message_count: chat(tickerAgent.s).length }]);
        }
        if (req.method === "GET" && tickerAgent && p === "/v1/read/chat") {
          return send(res, 200, q("topic")?.toUpperCase() === tickerAgent.s.ticker ? chat(tickerAgent.s) : []);
        }
        if (req.method === "GET" && tickerAgent && p === "/v1/read/tool_calls") return send(res, 200, toolCalls(tickerAgent.s));

        if (req.method === "POST" && p === "/v1/commands/add_dossier_note") {
          const body = await readBody(req);
          const hit = find(String(body.ticker ?? ""));
          const text = String(body.text ?? "").trim();
          if (!hit) return send(res, 200, { ok: false, data: {}, reasons: [`Nessuna scheda per ${body.ticker}`] });
          if (!text) return send(res, 200, { ok: false, data: {}, reasons: ["La nota è vuota"] });
          const cur = dossierOf(st, hit.s, hit.i).notes as Row[];
          const note = { id: Date.now(), author: "luca", text, ts: new Date().toISOString() };
          st.notes.set(hit.s.ticker, [...cur, note]);
          bump(hit.s.ticker);
          return send(res, 200, { ok: true, data: { note_id: note.id, version: st.version.get(hit.s.ticker) }, reasons: [] });
        }
        if (req.method === "POST" && p === "/v1/commands/decide_proposal") {
          const body = await readBody(req);
          const pid = Number(body.proposal_id);
          const list = seeds(st.dense);
          const i = list.findIndex((_, k) => PROPOSAL_ID(k) === pid);
          if (i < 0) return send(res, 200, { ok: false, data: {}, reasons: [`Proposta #${body.proposal_id} inesistente`] });
          if (body.confirm !== true) return send(res, 200, { ok: false, data: {}, reasons: ["Serve confirm: true"] });
          const status = { accept: "accepted", defer: "deferred", reject: "rejected", ask: "asked" }[String(body.action)];
          if (!status) return send(res, 200, { ok: false, data: {}, reasons: [`Azione non valida: ${body.action}`] });
          const cur = st.decided.get(pid)?.status ?? list[i].proposal?.status;
          if (cur !== "pending") return send(res, 200, { ok: false, data: {}, reasons: [`La proposta è già ${cur}`] });
          const ts = new Date().toISOString();
          st.decided.set(pid, { status, by: "luca", reason: String(body.reason ?? ""), ts });
          st.extraDecisions.set(list[i].ticker, [{ ts, actor: "luca", action: body.action, reason: String(body.reason ?? ""), cycle_id: 10 + i }, ...(st.extraDecisions.get(list[i].ticker) ?? [])]);
          bump(list[i].ticker);
          return send(res, 200, { ok: true, data: { proposal_id: pid, status, risk_gate: list[i].risk === "blocked" && status === "accepted" ? "rejected" : "pending" }, reasons: [] });
        }
        next();
      });
    },
  };
}

export const SPECIALIST_IDS = SPECIALISTS;
