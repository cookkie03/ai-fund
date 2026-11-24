# HANDOFF: Full Frontend Modernization with shadcn-ui + Base UI

> **Document Type:** Agent Handoff & Goal Definition  
> **Workspace:** `/home/luca/ai-fund/shadcn-ui-migration`  
> **Target Branch:** `shadcn-ui-migration`  
> **Reference Specs:** Official shadcn Base UI (`https://ui.shadcn.com/docs/components/base`)  
> **Created:** 2026-11-24  

---

## 1. Goal Definition (Primary Directive)

Eseguire una **modernizzazione e migrazione totale del frontend** (`frontend/`) adottando lo standard ufficiale **shadcn-ui con Base UI (`@base-ui/react`)**.

> **Direttiva chiave dell'utente:**
> **Non vincolarsi strettamente alla UI o ai componenti legacy attuali.**
> Utilizzare **esclusivamente** ciò che fa parte del catalogo ufficiale di [ui.shadcn.com](https://ui.shadcn.com/) (in particolare le pagine [`/docs/components/base`](https://ui.shadcn.com/docs/components/base), blocks, charts, design systems, elements, themings e icone Lucide).
> Ridisegnare e rifattorizzare le viste adottando i moderni blocchi e componenti shadcn invece di limitarsi a un wrapper replacement 1:1 del vecchio codice.

### Hard Constraints:
1. **Solo shadcn Base UI (`@base-ui/react`)**: Nessuna primitiva Radix UI. Alla fine della migrazione `radix-ui` e `@radix-ui/*` devono essere completamente disinstallate e assenti (`0` import residui).
2. **Catalog-first**: Tutto ciò che viene aggiunto deve provenire direttamente dall'ecosistema ufficiale shadcn (componenti base, blocchi layout, sidebar, card, tabelle, alert, badge, tabs, chart wrappers, theming).
3. **Theming & Design System**: Mantenere la palette dark del desk/trading-cockpit (OKLCH da `DESIGN.md`: desk, ground, raised, accenti di mercato e degli agenti) innestandola nelle variabili CSS e nei token standard di shadcn (Tailwind v4).
4. **Zero Broken States**: Ad ogni commit logico, il frontend deve compilare senza errori:
   ```bash
   npm run typecheck && npm run build
   ```
5. **Preservazione delle Funzionalità Core**: La logica applicativa, le chiamate API/SSE, il bridge con il backend runtime, i dati del portafoglio/ordini/dossier e il grafico Lightweight Charts devono rimanere perfettamente operativi dentro la nuova interfaccia moderna.

---

## 2. Skill & Strumenti a Disposizione

Tutte le skill necessarie sono già configurate nel branch (`.agents/skills/` e `.claude/skills/`):

- **`/shadcn`**: Per interrogare la documentazione di shadcn, componenti, blocchi, registry e snippet ufficiali.
- **`/migrate-radix-to-base`**: Guida al mapping esatto delle primitive e dei prop da Radix a `@base-ui/react` (es. `render` prop al posto di `asChild`, portali, positioner e popup).
- **`/impeccable`**: Per audit visivo, gerarchia dell'interfaccia, coerenza dei blocchi e rifinitura del design system.
- **`/taste-skill`**: Per elevare la qualità estetica e l'equilibrio dei componenti.
- **`/ask-matt`**: Per chiarimenti architetturali React/TypeScript o refactoring puliti.
- **`/lightweight-charts`**: Per armonizzare i canvas dei grafici finanziari all'interno delle nuove Card e Tile di shadcn.

---

## 3. Ambito di Riprogettazione (Componenti & Blocchi)

Non essere vincolato al codice pre-esistente; sfrutta i componenti e i blocchi ufficiali di shadcn per Base UI:

### A. Primitives & Elements (`/docs/components/base/*`)
- **Action & Controls**: Button, Toggle, Toggle Group.
- **Forms & Inputs**: Input, Textarea, Select, Switch, Checkbox, Slider, Label.
- **Overlays & Dialogs**: Dialog, Sheet (Drawer), Popover, Tooltip, Alert Dialog, Hover Card.
- **Navigation & Menus**: Dropdown Menu, Menubar, Context Menu, Tabs, Breadcrumb.
- **Feedback & Display**: Badge, Avatar, Skeleton, Separator, Scroll Area, Sonner (Toast), Accordion, Card.

### B. Shell & Layout Blocks
- Ripensare `AppShell`, la navigazione laterale/superiore e le split view usando i pattern di **shadcn Blocks** (Sidebar, Header, Metric Cards, Collapsible Panels).
- **Terminale / Cockpit**: Organizzare le sezioni in Card e Panel puliti con header, statistiche, status badge e toggle group.
- **Ufficio / Dossier**: Strutturare il feed decisionale e le proposte degli agenti con Card e Dialog standard di shadcn.
- **Portafoglio & Ordini**: Utilizzare tabelle e pannelli dock con badge semantici (Long/Short, PnL, Status).

---

## 4. Piano di Esecuzione in Fasi

### Fase 1: Inizializzazione Base UI & Shadcn Setup
1. Installare `@base-ui/react` in `frontend/`:
   ```bash
   cd frontend && npm i @base-ui/react
   ```
2. Aggiornare `components.json` se necessario per puntare allo stile base e verificare Tailwind v4.
3. Configurare i token del tema in `src/index.css` conformemente allo schema shadcn / Tailwind v4.

### Fase 2: Componenti Base UI di Shadcn
- Installare/generare i componenti ufficiali da shadcn Base UI (Button, Input, Dialog, Tooltip, Tabs, Separator, Badge, Card, ecc.).
- Usare `/shadcn` e `/migrate-radix-to-base` per verificare che ogni componente segua l'architettura `@base-ui/react`.
- Verificare la build: `npm run typecheck && npm run build`.

### Fase 3: Riprogettazione delle Pagine & Blocchi (Layout Moderno)
- Sostituire le vecchie implementazioni custom con i blocchi e pattern ufficiali shadcn:
  - `src/shell/`: Nuova shell con Sidebar/Header e pannelli collassabili.
  - `src/pages/terminal/`: Dashboard modulare con Card shadcn e metriche pulite.
  - `src/features/dossier/`: Proposte e decisioni riprogettate con componenti Base UI.
  - `src/features/chart/`: Contenitore del chart integrato con controlli e toolbars shadcn.
  - `src/features/portfolio/`: Data display pulito con tabelle e badge shadcn.

### Fase 4: Pulizia Radix UI & Chiusura
1. Rimuovere `radix-ui` da `package.json`:
   ```bash
   npm uninstall radix-ui
   ```
2. Verificare l'assenza totale di riferimenti residui:
   ```bash
   grep -rn "radix-ui" src/
   ```
3. Audit finale con `/impeccable` per validare l'estetica e la coerenza.
4. Test e build completa:
   ```bash
   npm run typecheck && npm run build
   ```

---

## 5. Come Avviare la Nuova Chat

Nel terminale, apri una nuova chat all'interno della branch:

```bash
cd /home/luca/ai-fund/shadcn-ui-migration
claude
```

E assegna il goal:

> **Leggi `@HANDOFF.md` ed esegui la migrazione/modernizzazione totale del frontend usando SOLO i componenti e blocchi ufficiali Base UI di shadcn-ui (`https://ui.shadcn.com/docs/components/base`), eliminando ogni residuo di Radix UI e mantenendo `npm run typecheck` e `npm run build` verdi ad ogni passo.**
