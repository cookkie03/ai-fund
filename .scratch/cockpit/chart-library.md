# Libreria grafici del Terminale (ricerca del 2026-11-20)

## Decisione proposta

- **Motore: `lightweight-charts` v5.3** (TradingView, Apache-2.0). È l'unico prodotto TradingView ammesso in un'app personale self-hosted. Lasciare attivo `attributionLogo` (o NOTICE + link a tradingview.com).
- **Disegni: `deepentropy/lightweight-charts-drawing`** (MIT, 86 strumenti, `DrawingManager` con add/update/remove/get, `exportJSON`/`importJSON`, eventi). I punti sono `{time, price}`: il JSON del disegno è anche il formato di persistenza nel Runtime e ciò che leggono e scrivono gli agenti. Le linee orizzontali semplici possono usare le price line native.
- **Indicatori: calcolati nel Runtime**, con la stessa definizione che usano i tool degli agenti (`IndicatorsInput`), e disegnati come serie native nei pane v5. Così l'agente e Luca vedono gli stessi valori. Riserva per indicatori non presenti nel Runtime: i 117 standard di `deepentropy/lightweight-charts-indicators` (MIT), mai i port "community".
- **Adattatore `ChartState`** tipizzato (`symbol`, `timeframe`, `indicators[]`, `drawings[]`, `notes[]`) come unica fonte di verità condivisa da UI e Runtime: il grafico è solo una vista, le librerie restano sostituibili.
- **Piano B: KLineChart** (Apache-2.0, 27 indicatori e 16 overlay integrati, API create/get), meno strumenti e meno aspetto TradingView.

## Esclusi

- **TradingView Advanced Charts / Trading Platform**: avrebbero 100+ indicatori, 110+ disegni e un'API completa, ma TradingView non li concede "for personal use, hobbies, studies, or testing", solo ad aziende per progetti web pubblici ([FAQ](https://www.tradingview.com/free-charting-libraries/), verificato).
- react-financial-charts, trading-vue-js, NightVision, technicalindicators: fermi o abbandonati.
- Order book: fuori scope.

## Rischi

- I pacchetti deepentropy sono giovani (pre-1.0, una rottura di API tra 0.1 e 0.2): fissare le versioni e coprire con test dietro l'adattatore.
- MPL-2.0 per `difurious/line-tools-core` (scartato come scelta primaria).

## Fonti verificate (API GitHub, 2026-11-20)

| Repo | Stelle | Licenza | Ultimo push |
|---|---|---|---|
| tradingview/lightweight-charts | 17.919 | Apache-2.0 | 2026-11-18 |
| deepentropy/lightweight-charts-drawing | 157 | MIT | 2026-11-19 |
| deepentropy/lightweight-charts-indicators | 345 | MIT | 2026-11-18 |
| klinecharts/KLineChart | 4.319 | Apache-2.0 | 2026-11-16 |
