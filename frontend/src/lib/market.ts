/** NYSE regular session in New York time. Exchange holidays are not modelled. */
export type Session = "pre" | "open" | "post" | "closed";

const fmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function nyParts(now: number) {
  const parts = Object.fromEntries(fmt.formatToParts(new Date(now)).map((p) => [p.type, p.value]));
  return { weekday: parts.weekday as string, h: Number(parts.hour) % 24, m: Number(parts.minute) };
}

export function marketSession(now: number): { session: Session; label: string; nextLabel: string; clock: string } {
  const { weekday, h, m } = nyParts(now);
  const mins = h * 60 + m;
  const weekend = weekday === "Sat" || weekday === "Sun";
  const clock = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  const until = (target: number) => {
    const d = target - mins;
    return d >= 60 ? `${Math.floor(d / 60)} h ${String(d % 60).padStart(2, "0")} min` : `${d} min`;
  };
  const reopen = weekday === "Fri" ? "Riapre lunedì alle 09:30" : "Riapre domani alle 09:30";
  if (weekend) return { session: "closed", label: "Chiuso", nextLabel: "Riapre lunedì alle 09:30", clock };
  if (mins >= 570 && mins < 960) return { session: "open", label: "Aperto", nextLabel: `Chiude tra ${until(960)}`, clock };
  if (mins >= 240 && mins < 570) return { session: "pre", label: "Pre-market", nextLabel: `Apre tra ${until(570)}`, clock };
  if (mins >= 960 && mins < 1200) return { session: "post", label: "After-hours", nextLabel: reopen, clock };
  return { session: "closed", label: "Chiuso", nextLabel: mins < 240 ? "Apre alle 09:30" : reopen, clock };
}
