import { CandlestickChart, MessageSquareText, Newspaper, Settings2, UsersRound, WalletCards, type LucideIcon } from "lucide-react";

export type NavItem = { path: string; label: string; icon: LucideIcon; summary: string; built: boolean };

export const NAV: NavItem[] = [
  { path: "/assistente", label: "Assistente", icon: MessageSquareText, built: false, summary: "Conversazione con il Bridge, l'agente che parla con tutto l'ufficio e usa gli stessi comandi della UI." },
  { path: "/ufficio", label: "Ufficio", icon: UsersRound, built: true, summary: "Gli agenti, le loro chat da leggere e scrivere, e lo stream dei tool che chiamano." },
  { path: "/terminale", label: "Terminale", icon: CandlestickChart, built: true, summary: "Grafico condiviso con il Technical Analyst, watchlist, ordini." },
  { path: "/notizie", label: "Notizie", icon: Newspaper, built: true, summary: "L'ambiente notizie degli agenti: leggere, filtrare e inviare notizie agli agenti." },
  { path: "/portafoglio", label: "Portafoglio", icon: WalletCards, built: true, summary: "Statistiche, esposizione, allocazione, posizioni, trade e vincoli di rischio." },
  { path: "/configurazioni", label: "Configurazioni", icon: Settings2, built: false, summary: "Agenti, modelli, prompt, schedule, budget, provider, account, database e salute del Runtime." },
];
