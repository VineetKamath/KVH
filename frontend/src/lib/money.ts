/**
 * Money is a string from the API ("5200.00") and is only ever FORMATTED here — never parsed into a JS number
 * for arithmetic (rule R3). Intl.NumberFormat accepts decimal strings exactly, so no float ever touches a price.
 * Native digits: हिन्दी → Devanagari numerals, ಕನ್ನಡ → Kannada numerals; the VALUE never changes, only the script.
 */
import Decimal from "decimal.js";

export type Locale = "en-IN" | "hi" | "kn";
export type Money = { amount: string; currency: string };

const EXPONENT: Record<string, number> = { JPY: 0, KRW: 0, IDR: 0, KWD: 3, BHD: 3, OMR: 3 };

export function intlLocale(locale: Locale, nativeDigits = true): string {
  if (!nativeDigits) return locale === "en-IN" ? "en-IN" : `${locale}-IN`;
  return { "en-IN": "en-IN", hi: "hi-IN-u-nu-deva", kn: "kn-IN-u-nu-knda" }[locale];
}

export function formatMoney(amount: string, currency: string, locale: Locale = "en-IN", nativeDigits = true): string {
  const digits = EXPONENT[currency] ?? 2;
  const fmt = new Intl.NumberFormat(intlLocale(locale, nativeDigits), {
    style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
  // format() takes the decimal string directly (exact); decimal.js only normalises precision for exponent-0 currencies
  const exact = new Decimal(amount).toFixed(digits);
  return fmt.format(exact as unknown as number);
}

export function formatPct(value: string, locale: Locale = "en-IN", withSign = true): string {
  const d = new Decimal(value);
  const fmt = new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 1, minimumFractionDigits: 1,
    signDisplay: withSign ? "exceptZero" : "auto" });
  return `${fmt.format(d.toFixed(1) as unknown as number)}%`;
}

export function formatNumber(value: string | number, locale: Locale = "en-IN", digits = 0): string {
  return new Intl.NumberFormat(intlLocale(locale), { minimumFractionDigits: digits, maximumFractionDigits: digits })
    .format(String(value) as unknown as number);
}

/** Signed difference as a display string (e.g. "+312.40"). Decimal arithmetic, never float. */
export function diff(a: string, b: string): string {
  const d = new Decimal(a).minus(new Decimal(b));
  return (d.isPositive() && !d.isZero() ? "+" : "") + d.toFixed(2);
}

/** Pixel positions only (charts): converting to a JS number for layout is not price arithmetic. */
export function toPlotNumber(amount: string | null | undefined): number | null {
  return amount == null ? null : new Decimal(amount).toNumber();
}

export function sumMoney(values: string[]): string {
  return values.reduce((acc, v) => acc.plus(new Decimal(v)), new Decimal(0)).toFixed(2);
}

/** Traveller-facing display: drops a zero fraction ("₹4,940" not "₹4,940.00"); keeps paise when they exist. */
export function formatPrice(amount: string, currency: string, locale: Locale = "en-IN"): string {
  const d = new Decimal(amount);
  if (!d.isInteger()) return formatMoney(amount, currency, locale);
  const fmt = new Intl.NumberFormat(intlLocale(locale), { style: "currency", currency, minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return fmt.format(d.toFixed(0) as unknown as number);
}
