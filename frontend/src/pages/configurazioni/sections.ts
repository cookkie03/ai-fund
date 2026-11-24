import { Activity, Clock3, Database, KeyRound, ListChecks, Newspaper, ShieldCheck, UsersRound, WalletCards, type LucideIcon } from "lucide-react";

export type SectionId = "agenti" | "chiavi" | "mercato" | "dati" | "salute";

export const SECTIONS: { id: SectionId; label: string; icon: LucideIcon; summary: string }[] = [
  { id: "agenti", label: "Agenti", icon: UsersRound, summary: "Modello, endpoint, effort, budget e prompt di ogni agente." },
  { id: "chiavi", label: "Provider e chiavi", icon: KeyRound, summary: "OmniRoute, broker e provider dati: chiavi in sola scrittura e prove di connessione." },
  { id: "mercato", label: "Mercato e orari", icon: Clock3, summary: "Orari di sessione, timeframe, cadenza dei cicli, task programmati e approvazione degli ordini." },
  { id: "dati", label: "Dati e archivio", icon: Database, summary: "Retention, dimensione del database e backup." },
  { id: "salute", label: "Salute del Runtime", icon: Activity, summary: "Versione, job, errori recenti, connessioni e stato di broker e provider." },
];

export const isSection = (s: string | undefined): s is SectionId => SECTIONS.some((x) => x.id === s);

/** What lives in another page, linked from the index instead of being duplicated here. */
export const ELSEWHERE: { label: string; page: string; to: string; icon: LucideIcon }[] = [
  { label: "Limiti di rischio", page: "Portafoglio", to: "/portafoglio?tab=risk", icon: ShieldCheck },
  { label: "Fonti delle notizie", page: "Notizie", to: "/notizie", icon: Newspaper },
  { label: "Watchlist", page: "Terminale", to: "/terminale", icon: ListChecks },
  { label: "Costi e token", page: "Ufficio", to: "/ufficio", icon: WalletCards },
];

/** Which page section a settings key belongs to; the contract's own section titles group rows inside it. */
export function sectionOfKey(key: string): SectionId {
  if (key.startsWith("agents.") || key.startsWith("budgets.")) return "agenti";
  if (key.startsWith("retention.") || key === "db_size_alert_mb") return "dati";
  return "mercato";
}

/** Agent id of an `agents.<id>.<field>` key. */
export const agentOfKey = (key: string) => (key.startsWith("agents.") ? key.split(".")[1] ?? null : null);
