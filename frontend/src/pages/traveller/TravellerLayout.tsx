import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet } from "react-router-dom";
import { initialLocale, useLocale } from "../../lib/locale";
import type { Locale } from "../../lib/money";

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <svg width="20" height="16" viewBox="0 0 20 16" aria-hidden className="translate-y-[2px]">
        <path d="M1 14 L6 8 L10 11 L18 2" fill="none" stroke="var(--indigo)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="18" cy="2" r="1.8" fill="var(--saffron)" />
      </svg>
      <span className="font-display text-[19px] font-semibold tracking-tight text-ink">Rate Ledger</span>
      {!compact && <span className="eyebrow hidden sm:inline">by PixelMinds</span>}
    </span>
  );
}

export default function TravellerLayout() {
  const { t } = useTranslation();
  const [locale, setLocale] = useLocale();
  useEffect(() => { setLocale(initialLocale()); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen" lang={locale}>
      <header className="border-b border-rule bg-paper/90 backdrop-blur-[2px]">
        <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link to="/" aria-label="Rate Ledger home"><Wordmark /></Link>
          <nav className="flex items-center gap-1 text-[13px]">
            <NavLink to="/" end className="rail-link !py-1.5">{t("nav.stays")}</NavLink>
            <NavLink to="/desk" className="rail-link !py-1.5">{t("nav.desk")}</NavLink>
          </nav>
          <div role="group" aria-label="Language" className="flex items-center rounded-[6px] border border-rule bg-surface p-0.5">
            {(["hi", "kn", "en-IN"] as Locale[]).map((l) => (
              <button key={l} onClick={() => setLocale(l)} aria-pressed={locale === l} lang={l}
                className={`rounded-[4px] px-2.5 py-1 text-[13px] transition-colors ${locale === l ? "bg-ink text-paper" : "text-ink-muted hover:text-ink"}`}>
                {t(`lang.${l}`)}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1120px] px-4 py-8 sm:px-6"><Outlet /></main>
      <footer className="mx-auto max-w-[1120px] border-t border-rule px-4 py-6 text-[12px] text-ink-muted sm:px-6">{t("footer")}</footer>
    </div>
  );
}
