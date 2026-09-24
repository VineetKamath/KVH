import { useTranslation } from "react-i18next";
import type { Locale } from "./money";

const KEY = "rl.locale";

export function useLocale(): [Locale, (l: Locale) => void] {
  const { i18n } = useTranslation();
  const current = (["en-IN", "hi", "kn"].includes(i18n.language) ? i18n.language : "hi") as Locale;
  const set = (l: Locale) => {
    i18n.changeLanguage(l);
    document.documentElement.lang = l;
    try { localStorage.setItem(KEY, l); } catch { /* per-viewer convenience only */ }
  };
  return [current, set];
}

export function initialLocale(): Locale {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "en-IN" || v === "hi" || v === "kn") return v;
  } catch { /* storage unavailable */ }
  return "hi";
}
