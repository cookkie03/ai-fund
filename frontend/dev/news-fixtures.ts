// Development only. Answers the news reads and commands the Runtime does not expose yet with synthetic data
// shaped exactly like the contract (.scratch/notizie/handoff-backend.md), so every state of /notizie can be
// designed and checked before the backend lands. Enabled only by `COCKPIT_NEWS_FIXTURES=1` on `vite` (serve):
// it never reaches a build. It also serves `/v1/dev/news-events`, a synthetic SSE stream with new items.
//
// States are switched per browser with the `news_fixture` cookie (comma separated):
//   empty   no news for any filter          nocal    empty calendar
//   missing every news read/command answers 404 "not found" (Runtime predating the contract)
//   down    502 on every news read (Runtime unreachable)
//   refuse  forward_news is refused by the Runtime
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

type Row = Record<string, unknown>;

const MIN = 60_000;
const HOUR = 60 * MIN;
const PORTFOLIO = ["NVDA", "AAPL", "MSFT", "JPM"];
const WATCHLIST = ["AMD", "TSLA", "META"];

const SOURCES: Row[] = [
  { id: 1, provider: "alpaca", name: "Alpaca News (Benzinga)", url: null, enabled: true, status: "ok", last_error: null },
  { id: 2, provider: "rss", name: "Reuters Business", url: "https://feeds.reuters.com/reuters/businessNews", enabled: true, status: "ok", last_error: null },
  { id: 3, provider: "rss", name: "Il Sole 24 Ore · Finanza", url: "https://www.ilsole24ore.com/rss/finanza.xml", enabled: true, status: "error", last_error: "HTTP 403 dal feed (ultimi 3 tentativi); ultimo successo 2 giorni fa" },
  { id: 4, provider: "rss", name: "CNBC Top News", url: "https://www.cnbc.com/id/100003114/device/rss/rss.html", enabled: false, status: "ok", last_error: null },
  { id: 5, provider: "openbb", name: "OpenBB · società e mondo", url: null, enabled: true, status: "unavailable", last_error: "Extra openbb non installato nel Runtime (uv sync --extra openbb)" },
];

// Headlines are synthetic but written like the wire: [ticker(s), themes, headline, summary | null, full text?]
const WIRE: [string[], string[], string, string | null, boolean][] = [
  [["NVDA"], ["semiconductors", "ai"], "Nvidia, ordini di Blackwell oltre le attese: i fornitori asiatici alzano la produzione del 20%", "I fornitori di packaging avanzato a Taiwan segnalano ordini superiori ai piani per il primo trimestre, con consegne anticipate a gennaio.", true],
  [["AAPL"], ["consumer", "regulation"], "Apple, la Commissione UE apre una nuova istruttoria sull'App Store dopo il DMA", "Bruxelles chiede documenti sulle commissioni applicate agli sviluppatori che usano pagamenti esterni.", true],
  [["MSFT"], ["ai", "cloud"], "Microsoft firma un accordo pluriennale per capacità di calcolo con un operatore nucleare in Pennsylvania", null, false],
  [["AMD"], ["semiconductors"], "AMD presenta gli acceleratori MI400: consegne ai primi clienti hyperscaler nel secondo trimestre", "La società conferma la roadmap annuale e indica una capacità produttiva in crescita presso TSMC.", true],
  [["TSLA"], ["autos", "ev"], "Tesla, consegne in Cina in calo del 9% su base mensile secondo i dati preliminari della CPCA", "I dati non includono le esportazioni dallo stabilimento di Shanghai.", false],
  [[], ["macro", "fed"], "Fed, i verbali di novembre: la maggioranza vede spazio per un altro taglio se l'inflazione dei servizi rallenta", "Diversi partecipanti hanno espresso cautela sul ritmo dei tagli, citando la tenuta del mercato del lavoro.", true],
  [["JPM"], ["banks"], "JPMorgan alza la guidance sul margine di interesse netto per il 2027 all'investor day", null, false],
  [["META"], ["ai", "advertising"], "Meta, la spesa in conto capitale 2027 potrebbe superare i 100 miliardi secondo due analisti sell-side", "Le stime riflettono la costruzione di nuovi data center in Louisiana e Ohio.", false],
  [["XOM", "CVX"], ["energy", "oil"], "Petrolio, il Brent scende sotto 70 dollari dopo l'aumento delle scorte USA superiore alle attese", "L'EIA riporta un aumento di 4,1 milioni di barili contro un consenso di 1,2 milioni.", false],
  [["NVDA", "AMD"], ["semiconductors", "regulation"], "Washington valuta nuovi limiti all'export di chip verso il Medio Oriente, dicono fonti vicine al dossier", "Le regole riguarderebbero gli acceleratori di fascia alta e richiederebbero licenze caso per caso.", true],
  [[], ["macro", "inflation"], "Eurozona, inflazione di novembre stimata al 2,1%: core stabile al 2,5%", null, false],
  [["AAPL"], ["consumer"], "Apple, i tempi di consegna di iPhone 18 Pro si accorciano negli Stati Uniti: segnale di domanda più debole", "Lo indica un monitoraggio settimanale dei tempi di spedizione sul sito Apple in 30 paesi.", false],
  [["MSFT"], ["cloud"], "Azure, interruzione di servizio di due ore in Europa occidentale: risolta, cause in analisi", null, false],
  [["GOOGL"], ["ai", "regulation"], "Alphabet, il giudice fissa a marzo l'udienza sui rimedi nel caso search", null, false],
  [["TSLA"], ["autos", "ai"], "Tesla avvia il servizio robotaxi a Phoenix con 50 veicoli senza supervisione a bordo", "Il servizio è limitato a una zona di 80 chilometri quadrati e a utenti invitati.", true],
  [["AMZN"], ["consumer", "cloud"], "Amazon, AWS annuncia nuovi chip Trainium 3 disponibili a inizio 2027", null, false],
];

const PROVIDER_OF = (sourceId: number) => (sourceId === 1 ? "alpaca" : sourceId === 5 ? "openbb" : "rss");

type Item = Row & { id: number; published_ms: number; usage_detail: Row[] };

const AGENTS_READ = ["sentiment_analyst", "market_analyst", "fundamental_analyst", "technical_analyst", "portfolio_manager"];

function buildItems(): Item[] {
  const now = Date.now();
  const items: Item[] = [];
  for (let i = 0; i < 84; i++) {
    const w = WIRE[i % WIRE.length];
    const sourceId = [1, 1, 2, 1, 3, 2, 5, 1][i % 8];
    const published = now - (i * 41 + (i % 5) * 7) * MIN - 3 * MIN;
    const tickers = w[0];
    const reads = i % 3 === 0 ? 0 : (i % 4) + 1;
    const cites = i % 5 === 1 ? 1 : 0;
    const usage: Row[] = [];
    for (let r = 0; r < reads; r++)
      usage.push({ agent: tickers[0] && r === 0 ? `ticker:${tickers[0]}` : AGENTS_READ[(i + r) % AGENTS_READ.length], kind: "read", ts: new Date(published + (r + 1) * 6 * MIN).toISOString(), cycle_id: 30 + (i % 12), chat_id: 100 + i, topic: tickers[0] ?? "macro", note: null });
    if (cites)
      usage.push({ agent: "sentiment_analyst", kind: "cited", ts: new Date(published + 25 * MIN).toISOString(), cycle_id: 30 + (i % 12), chat_id: 100 + i, topic: tickers[0] ?? "macro", note: null });
    if (i === 1)
      usage.push({ agent: "ticker:AAPL", kind: "forwarded", ts: new Date(published + 40 * MIN).toISOString(), cycle_id: null, chat_id: 220, topic: "AAPL", note: "Rischio regolatorio sottovalutato nella tesi: pesalo prima della prossima revisione." });
    const variant = i >= WIRE.length ? ` (${Math.floor(i / WIRE.length) + 1}° aggiornamento)` : "";
    items.push({
      id: 5000 - i,
      headline: w[2] + variant,
      summary: w[3],
      url: i % 9 === 4 ? null : `https://news.example.com/${5000 - i}`,
      source: (SOURCES.find((s) => s.id === sourceId)?.name as string) ?? "",
      source_id: sourceId,
      provider: PROVIDER_OF(sourceId),
      published_ms: published,
      published_ts: new Date(published).toISOString(),
      fetched_ts: new Date(published + 2 * MIN).toISOString(),
      tickers,
      themes: w[1],
      image_url: null,
      has_full_text: w[4],
      full_text: w[4] ? fullText(w[2], w[3]) : null,
      usage_detail: usage,
    });
  }
  return items;
}

function fullText(headline: string, summary: string | null): string {
  return [
    summary ?? headline,
    "Secondo le persone informate, le discussioni sono in una fase avanzata ma i termini potrebbero ancora cambiare. Le società coinvolte non hanno commentato.",
    "Gli analisti interpellati sottolineano che l'effetto sui conti del prossimo trimestre sarebbe limitato, mentre il segnale sulla domanda dell'intero 2027 resta il punto da seguire. Alcuni desk hanno già rivisto le stime di consenso.",
    "Il titolo ha reagito nelle contrattazioni pre-mercato, con volumi superiori alla media delle ultime venti sedute.",
  ].join("\n\n");
}

const state = { items: buildItems(), sources: SOURCES.map((s) => ({ ...s })), nextId: 5001, clients: new Set<ServerResponse>() };

const usageOf = (it: Item) => ({
  reads: it.usage_detail.filter((u) => u.kind === "read").length,
  citations: it.usage_detail.filter((u) => u.kind === "cited").length,
  forwards: it.usage_detail.filter((u) => u.kind === "forwarded").length,
});

function publicItem(it: Item): Row {
  const { published_ms: _p, usage_detail: _u, full_text: _f, source_id: _s, ...rest } = it;
  const tickers = it.tickers as string[];
  return { ...rest, in_portfolio: tickers.some((t) => PORTFOLIO.includes(t)), in_watchlist: tickers.some((t) => WATCHLIST.includes(t)), usage: usageOf(it) };
}

function emit(type: string, data: Row) {
  for (const res of state.clients) res.write(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`);
}

let tick = 0;
function ingest() {
  const w = WIRE[(tick * 7 + 3) % WIRE.length];
  tick++;
  const id = state.nextId++;
  const now = Date.now();
  state.items.unshift({
    id,
    headline: `${w[2]} · aggiornamento delle ${new Date(now).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`,
    summary: w[3],
    url: `https://news.example.com/${id}`,
    source: "Alpaca News (Benzinga)",
    source_id: 1,
    provider: "alpaca",
    published_ms: now,
    published_ts: new Date(now).toISOString(),
    fetched_ts: new Date(now).toISOString(),
    tickers: w[0],
    themes: w[1],
    image_url: null,
    has_full_text: false,
    full_text: null,
    usage_detail: [],
  });
  emit("news.ingested", { source_id: 1, count: 1 });
  // An agent picks it up a little later.
  setTimeout(() => {
    const it = state.items.find((x) => x.id === id);
    if (!it) return;
    it.usage_detail.push({ agent: "sentiment_analyst", kind: "read", ts: new Date().toISOString(), cycle_id: 52, chat_id: 300, topic: (w[0][0] as string) ?? "macro", note: null });
    emit("news.used", { news_id: id, agent: "sentiment_analyst", kind: "read" });
  }, 9000);
}

function calendar(from: number, to: number): Row[] {
  const day = (offset: number, h: number, m = 0) => {
    const d = new Date();
    d.setUTCHours(0, 0, 0, 0);
    d.setUTCDate(d.getUTCDate() + offset);
    d.setUTCHours(h, m);
    return d.toISOString();
  };
  const rows: Row[] = [
    { id: "m1", kind: "macro", ts: day(0, 13, 30), title: "Richieste iniziali di sussidi di disoccupazione", country: "US", ticker: null, importance: "medium", actual: "214K", forecast: "220K", previous: "223K", source: "OpenBB · economy.calendar" },
    { id: "m2", kind: "macro", ts: day(0, 19, 0), title: "Verbali FOMC", country: "US", ticker: null, importance: "high", actual: null, forecast: null, previous: null, source: "OpenBB · economy.calendar" },
    { id: "e1", kind: "earnings", ts: day(0, 21, 5), title: "Trimestrale Q3 FY27", country: "US", ticker: "NVDA", importance: "high", actual: null, forecast: "EPS 1,12", previous: "EPS 0,81", source: "OpenBB · equity.calendar.earnings" },
    { id: "m3", kind: "macro", ts: day(1, 10, 0), title: "Inflazione Eurozona (stima flash)", country: "EU", ticker: null, importance: "high", actual: null, forecast: "2,1%", previous: "2,0%", source: "OpenBB · economy.calendar" },
    { id: "e2", kind: "earnings", ts: day(1, 12, 30), title: "Trimestrale Q4", country: "US", ticker: "CRM", importance: "medium", actual: null, forecast: "EPS 2,71", previous: "EPS 2,41", source: "OpenBB · equity.calendar.earnings" },
    { id: "m4", kind: "macro", ts: day(2, 13, 30), title: "PCE core (m/m)", country: "US", ticker: null, importance: "high", actual: null, forecast: "0,2%", previous: "0,3%", source: "OpenBB · economy.calendar" },
    { id: "m5", kind: "macro", ts: day(2, 15, 0), title: "Fiducia dei consumatori Michigan (finale)", country: "US", ticker: null, importance: "low", actual: null, forecast: "71,8", previous: "71,6", source: "OpenBB · economy.calendar" },
    { id: "e3", kind: "earnings", ts: day(3, 21, 0), title: "Trimestrale Q4", country: "US", ticker: "AMD", importance: "high", actual: null, forecast: "EPS 1,04", previous: "EPS 0,92", source: "OpenBB · equity.calendar.earnings" },
    { id: "m6", kind: "macro", ts: day(4, 13, 30), title: "Rapporto sull'occupazione (non agricoli)", country: "US", ticker: null, importance: "high", actual: null, forecast: "165K", previous: "142K", source: "OpenBB · economy.calendar" },
    { id: "m7", kind: "macro", ts: day(4, 13, 30), title: "Tasso di disoccupazione", country: "US", ticker: null, importance: "medium", actual: null, forecast: "4,1%", previous: "4,1%", source: "OpenBB · economy.calendar" },
    { id: "e4", kind: "earnings", ts: day(6, 12, 0), title: "Trimestrale Q4", country: "US", ticker: "COST", importance: "low", actual: null, forecast: "EPS 4,25", previous: "EPS 3,98", source: "OpenBB · equity.calendar.earnings" },
    { id: "m8", kind: "macro", ts: day(7, 13, 30), title: "CPI (a/a)", country: "US", ticker: null, importance: "high", actual: null, forecast: "2,8%", previous: "2,9%", source: "OpenBB · economy.calendar" },
  ];
  return rows
    .filter((r) => {
      const t = Date.parse(r.ts as string);
      return t >= from && t < to;
    })
    .map((r) => ({ ...r, in_portfolio: PORTFOLIO.includes(r.ticker as string), in_watchlist: WATCHLIST.includes(r.ticker as string) }));
}

function modes(req: IncomingMessage): Set<string> {
  const m = /(?:^|;\s*)news_fixture=([^;]*)/.exec(req.headers.cookie ?? "");
  return new Set(m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : []);
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Dev-Fixture", "news");
  res.end(JSON.stringify(body));
}

async function readBody(req: IncomingMessage): Promise<Row> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  try {
    return JSON.parse(Buffer.concat(chunks).toString() || "{}");
  } catch {
    return {};
  }
}

const READS = ["news", "news_item", "news_sources", "calendar"];
const COMMANDS = ["forward_news", "add_news_source", "set_news_source_enabled", "remove_news_source", "refresh_news"];
const ok = (data: Row = {}) => ({ ok: true, data, reasons: [] });
const refused = (...reasons: string[]) => ({ ok: false, data: {}, reasons });

function readNews(url: URL, m: Set<string>): Row {
  if (m.has("empty")) return { items: [], next_before: null };
  const p = url.searchParams;
  const q = (p.get("q") ?? "").toLowerCase();
  const before = p.get("before");
  const limit = Math.min(200, Number(p.get("limit") ?? 50) || 50);
  const list = state.items.filter((it) => {
    const tickers = it.tickers as string[];
    if (p.get("ticker") && !tickers.includes(p.get("ticker")!.toUpperCase())) return false;
    if (p.get("theme") && !(it.themes as string[]).includes(p.get("theme")!)) return false;
    if (p.get("source_id") && String(it.source_id) !== p.get("source_id")) return false;
    if (p.get("provider") && it.provider !== p.get("provider")) return false;
    if (p.get("scope") === "portfolio" && !tickers.some((t) => PORTFOLIO.includes(t))) return false;
    if (p.get("scope") === "watchlist" && !tickers.some((t) => WATCHLIST.includes(t))) return false;
    if (q && !`${it.headline} ${it.summary ?? ""}`.toLowerCase().includes(q)) return false;
    if (before && it.published_ms >= Date.parse(before)) return false;
    return true;
  });
  const page = list.slice(0, limit);
  return { items: page.map(publicItem), next_before: list.length > limit ? (page.at(-1)!.published_ts as string) : null };
}

export function newsFixtures(): Plugin {
  return {
    name: "cockpit-news-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info("  ⚠ Notizie: fixture di sviluppo attive per news, news_item, news_sources, calendar e comandi (COCKPIT_NEWS_FIXTURES=1)");
      const timer = setInterval(ingest, 25_000);
      server.httpServer?.on("close", () => clearInterval(timer));
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        if (url.pathname === "/v1/dev/news-events") {
          res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
          res.write(": news fixtures\n\n");
          state.clients.add(res);
          req.on("close", () => state.clients.delete(res));
          return;
        }
        const read = url.pathname.match(/^\/v1\/read\/([a-z_]+)$/);
        const cmd = url.pathname.match(/^\/v1\/commands\/([a-z_]+)$/);
        const name = read?.[1] ?? cmd?.[1];
        if (!name || !(read ? READS : COMMANDS).includes(name)) return next();
        const m = modes(req);
        if (m.has("down")) return send(res, 502, { detail: "Bad gateway" });
        if (m.has("missing")) return send(res, 404, { detail: read ? `Read endpoint '${name}' not found` : `Command '${name}' not found` });

        if (read) {
          if (name === "news") return send(res, 200, readNews(url, m));
          if (name === "news_item") {
            const it = state.items.find((x) => x.id === Number(url.searchParams.get("id")));
            if (!it) return send(res, 404, { detail: "News item not found" });
            return send(res, 200, { ...publicItem(it), full_text: it.full_text, usage_detail: [...it.usage_detail].sort((a, b) => Date.parse(b.ts as string) - Date.parse(a.ts as string)) });
          }
          if (name === "news_sources") {
            const now = Date.now();
            return send(
              res,
              200,
              state.sources.map((s) => ({
                ...s,
                last_fetch_ts: s.status === "unavailable" || !s.enabled ? null : new Date(now - (s.status === "error" ? 2 * 24 * HOUR : 4 * MIN)).toISOString(),
                items_24h: state.items.filter((it) => it.source_id === s.id && now - it.published_ms < 24 * HOUR).length,
              })),
            );
          }
          if (name === "calendar") {
            if (m.has("nocal")) return send(res, 200, []);
            const from = Date.parse(url.searchParams.get("from") ?? "") || Date.now();
            const to = Date.parse(url.searchParams.get("to") ?? "") || Date.now() + 8 * 24 * HOUR;
            const kind = url.searchParams.get("kind");
            return send(res, 200, calendar(from, to).filter((r) => !kind || r.kind === kind));
          }
        }

        const body = await readBody(req);
        if (name === "forward_news") {
          const it = state.items.find((x) => x.id === Number(body.news_id));
          const to = (body.to ?? {}) as Row;
          const note = typeof body.note === "string" ? body.note.trim() : "";
          if (m.has("refuse")) return send(res, 200, refused("Halt attivo: gli inoltri agli agenti sono sospesi fino a resume"));
          if (!it) return send(res, 200, refused(`Notizia ${String(body.news_id)} non trovata`));
          if (!note) return send(res, 200, refused("La nota è obbligatoria"));
          const agent = typeof to.ticker === "string" ? `ticker:${to.ticker.toUpperCase()}` : String(to.agent ?? "");
          it.usage_detail.push({ agent, kind: "forwarded", ts: new Date().toISOString(), cycle_id: null, chat_id: 999, topic: typeof to.ticker === "string" ? to.ticker.toUpperCase() : "cockpit", note });
          setTimeout(() => emit("news.used", { news_id: it.id, agent, kind: "forwarded" }), 50);
          return send(res, 200, ok({ news_id: it.id, agent }));
        }
        if (name === "add_news_source") {
          const u = String(body.url ?? "");
          if (!/^https?:\/\//i.test(u)) return send(res, 200, refused("Solo feed http(s)"));
          if (state.sources.some((s) => s.url === u)) return send(res, 200, refused("Feed già presente"));
          const id = Math.max(...state.sources.map((s) => s.id as number)) + 1;
          const source = { id, provider: "rss", name: String(body.name || new URL(u).hostname), url: u, enabled: true, status: "ok", last_error: null };
          state.sources.push(source);
          setTimeout(() => emit("news.source", { source }), 50);
          return send(res, 200, ok({ source_id: id }));
        }
        const s = state.sources.find((x) => x.id === Number(body.source_id));
        if (name === "refresh_news") {
          setTimeout(() => emit("news.source", { source: s ?? null }), 400);
          return send(res, 200, ok({}));
        }
        if (!s) return send(res, 200, refused(`Fonte ${String(body.source_id)} non trovata`));
        if (name === "set_news_source_enabled") s.enabled = body.enabled === true;
        if (name === "remove_news_source") {
          if (s.provider !== "rss") return send(res, 200, refused("Si possono togliere solo i feed RSS"));
          state.sources = state.sources.filter((x) => x !== s);
        }
        setTimeout(() => emit("news.source", { source: s }), 50);
        return send(res, 200, ok({}));
      });
    },
  };
}
