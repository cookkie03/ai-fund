# Risk a due livelli: Risk Analyst pari + Risk Gate deterministico

Il rischio è presente due volte: un **Risk Analyst** (LLM) lavora alla pari degli altri Analyst e porta la tesi contraria prima della decisione del PM; un **Risk Gate** deterministico, che non è un agente, verifica i limiti dopo la decisione e può solo bloccare. Abbiamo scartato il Risk solo come analista (nessun veto affidabile, l'LLM potrebbe sbagliare i limiti) e il Risk solo come gate finale (si perde il contraddittorio durante l'analisi). Il veto resta fuori dall'LLM perché nessuna esecuzione deve dipendere da un ragionamento non deterministico.

Decisione di Luca, 2026-11-18. Wiki: `wiki/system/foundation/decision-log.md`.
