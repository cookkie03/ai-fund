# terminale-ui-2026 (archivio)

Prototipo di frontend alternativo (Chart + Terminal con lightweight-charts), costruito sulla base `0bb0b99`,
prima della migrazione shadcn/Base UI. Salvato da `wip/terminale-ui-2026`.

Non è stato unito come codice: sostituiva `main.tsx`, `App.tsx` e `vite.config.ts` del frontend reale e usava
dipendenze `latest`. I file sono `.txt` apposta, così `tsc` e Vite non li toccano.

Per riusarlo: `Chart.tsx.txt` e `Terminal.tsx.txt` sono i pezzi riutilizzabili (grafico lightweight-charts e terminale);
`runtime.ts.txt` è il client Runtime di allora, ormai superato da `src/lib/runtime/`.
Il ramo completo resta in `wip/terminale-ui-2026`.
