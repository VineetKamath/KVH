/** `_date` values are zoneless calendar dates (R4): never pass them through `new Date("YYYY-MM-DD")` (UTC midnight). */
import { intlLocale, type Locale } from "./money";

export function parseDate(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.split("-").map(Number);
  return { y, m, d };
}

export function addDays(iso: string, days: number): string {
  const { y, m, d } = parseDate(iso);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return dt.toISOString().slice(0, 10);
}

export function daysBetween(a: string, b: string): number {
  const pa = parseDate(a), pb = parseDate(b);
  return Math.round((Date.UTC(pb.y, pb.m - 1, pb.d) - Date.UTC(pa.y, pa.m - 1, pa.d)) / 86_400_000);
}

export function formatDate(iso: string, locale: Locale = "en-IN", opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }): string {
  const { y, m, d } = parseDate(iso);
  return new Intl.DateTimeFormat(intlLocale(locale), { ...opts, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

export function weekday(iso: string, locale: Locale = "en-IN"): string {
  return formatDate(iso, locale, { weekday: "short" });
}
