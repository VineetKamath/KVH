import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api } from "../../api/client";
import type { CatalogCities } from "../../api/types";
import { formatDate } from "../../lib/dates";
import { initialLocale, useLocale } from "../../lib/locale";
import type { Locale } from "../../lib/money";

/** The mark: a price line moving between a ceiling and a floor, ending on a published point. */
export function Mark({ size = 22, tone = "ink" }: { size?: number; tone?: "ink" | "light" }) {
  const line = tone === "ink" ? "var(--ink)" : "#fff";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <line x1="2" y1="4" x2="22" y2="4" stroke="var(--saffron)" strokeWidth="1.4" />
      <line x1="2" y1="20" x2="22" y2="20" stroke="var(--teal)" strokeWidth="1.4" />
      <path d="M3 15 L8 11 L12 13 L18 7" fill="none" stroke={line} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="18.5" cy="7" r="2.2" fill="var(--brass)" />
    </svg>
  );
}

export function Wordmark({ compact = false, tone = "ink" }: { compact?: boolean; tone?: "ink" | "light" }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Mark tone={tone} />
      <span className={`font-display text-[21px] font-medium tracking-[-0.02em] ${tone === "ink" ? "text-ink" : "text-white"}`}>
        Rate <span className="italic-serif">Ledger</span>
      </span>
      {!compact && <span className={`eyebrow hidden border-l pl-2.5 sm:inline ${tone === "ink" ? "border-rule-strong" : "border-night-rule !text-night-faint"}`}>PixelMinds</span>}
    </span>
  );
}

export function LanguageSwitch({ locale, setLocale, tone = "ink" }: { locale: Locale; setLocale: (l: Locale) => void; tone?: "ink" | "light" }) {
  const short: Record<Locale, string> = { "en-IN": "EN", hi: "हि", kn: "ಕ" };
  const full: Record<Locale, string> = { "en-IN": "English", hi: "हिन्दी", kn: "ಕನ್ನಡ" };
  return (
    <div role="group" aria-label="Language" className={`flex items-center gap-0.5 rounded-[3px] border p-0.5 ${tone === "ink" ? "border-rule-strong bg-surface" : "border-night-rule"}`}>
      {(["en-IN", "hi", "kn"] as Locale[]).map((l) => (
        <button key={l} onClick={() => setLocale(l)} aria-pressed={locale === l} lang={l} title={full[l]} aria-label={full[l]}
          className={`min-w-[34px] rounded-[2px] px-2 py-1 text-[12.5px] transition-colors duration-150 ${locale === l
            ? (tone === "ink" ? "bg-ink text-paper" : "bg-white text-ink") : (tone === "ink" ? "text-ink-muted hover:text-ink" : "text-night-text hover:text-white")}`}>
          {short[l]}
        </button>
      ))}
    </div>
  );
}

export default function TravellerLayout() {
  const { t } = useTranslation();
  const [locale, setLocale] = useLocale();
  useEffect(() => { setLocale(initialLocale()); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api.get<CatalogCities>("/v1/catalog/cities") });
  const bd = catalog.data?.business_date;

  return (
    <div className="min-h-screen" lang={locale}>
      <div className="bg-ink text-paper">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-4 py-1.5 sm:px-8">
          <p className="num flex items-center gap-2 text-[11px] tracking-[0.06em] text-night-text">
            <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-teal" aria-hidden />
            {bd ? t("home.live", { date: formatDate(bd, locale, { day: "numeric", month: "short", year: "numeric" }) }) : " "}
          </p>
          <p className="hidden text-[11px] text-night-faint sm:block">{t("tagline")}</p>
        </div>
      </div>
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-4 px-4 py-4 sm:px-8">
          <Link to="/" aria-label="Rate Ledger home"><Wordmark /></Link>
          <nav className="hidden items-center gap-7 text-[13.5px] md:flex">
            <NavLink to="/" end className="nav-link">{t("nav.stays")}</NavLink>
            <NavLink to="/desk" className="nav-link inline-flex items-center gap-1">{t("nav.for_hotels")} · {t("nav.desk")}<ArrowUpRight size={13} strokeWidth={1.6} /></NavLink>
          </nav>
          <LanguageSwitch locale={locale} setLocale={setLocale} />
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-8 sm:py-12"><Outlet /></main>
      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-4 py-8 sm:flex-row sm:items-start sm:justify-between sm:px-8">
          <div className="max-w-[52ch]">
            <Wordmark compact />
            <p className="mt-3 text-[12.5px] leading-relaxed text-ink-muted">{t("footer")}</p>
          </div>
          <div className="flex items-center gap-5 text-[12.5px]">
            <NavLink to="/desk" className="nav-link md:hidden">{t("nav.desk")}</NavLink>
            <span className="eyebrow">APS-02 · PixelMinds</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
