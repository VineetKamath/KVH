/** Static interface strings only. Numbers never live in these bundles (Intl formats them from raw values). */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enIN from "./en-IN.json";
import hi from "./hi.json";
import kn from "./kn.json";

export const LOCALES = ["en-IN", "hi", "kn"] as const;

i18n.use(initReactI18next).init({
  resources: { "en-IN": { translation: enIN }, hi: { translation: hi }, kn: { translation: kn } },
  lng: "en-IN", // English is the primary language; हिन्दी and ಕನ್ನಡ are one click away
  fallbackLng: { kn: ["hi", "en-IN"], hi: ["en-IN"], default: ["en-IN"] },
  interpolation: { escapeValue: false }, // React escapes rendered strings; we never inject HTML
  returnNull: false,
});

export default i18n;
