import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, ExternalLink, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, sessionId, type ApiError } from "../../api/client";
import type { Quote } from "../../api/types";
import { Button, ErrorNote, Skeleton } from "../../components/ui";
import { daysBetween, formatDate, weekday } from "../../lib/dates";
import { useLocale } from "../../lib/locale";
import { formatNumber, formatPrice as formatMoney, type Locale } from "../../lib/money";
import { Mark } from "./TravellerLayout";

function useCountdown(expiresAt?: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  if (!expiresAt) return null;
  return Math.max(0, Math.floor((Date.parse(expiresAt) - now) / 1000));
}

function Gate({ seconds, locale }: { seconds: number; locale: Locale }) {
  const m = Math.floor(seconds / 60), s = seconds % 60;
  const pad = (n: number) => formatNumber(n, locale).padStart(2, locale === "en-IN" ? "0" : formatNumber(0, locale));
  return <span className="num text-[40px] leading-none tracking-tight text-ink" aria-live="off">{pad(m)}:{pad(s)}</span>;
}

export default function PricePass() {
  const { roomId = "" } = useParams();
  const [params] = useSearchParams();
  const { t } = useTranslation();
  const [locale] = useLocale();
  const [showWhy, setShowWhy] = useState(true);
  const navigate = useNavigate();
  const body = { entity_id: roomId, checkin_date: params.get("in"), checkout_date: params.get("out"),
    party_size: Number(params.get("g") ?? 2), session_id: sessionId(), locale };
  const quote = useQuery({ queryKey: ["quote", roomId, body.checkin_date, body.checkout_date, body.party_size, locale],
    queryFn: () => api.post<Quote>("/v1/quote", body), retry: false });
  const book = useMutation({ mutationFn: (id: string) => api.post<{ status: string }>(`/v1/quote/${id}/confirm`, {}) });
  const seconds = useCountdown(quote.data?.expires_at);
  const q = quote.data;
  const err = quote.error as unknown as ApiError | null;
  const bookErr = book.error as unknown as ApiError | null;

  if (quote.isLoading) return <div className="panel mx-auto max-w-[1040px] p-8"><Skeleton lines={9} /></div>;
  if (err) return (
    <div className="mx-auto max-w-[1040px] space-y-4">
      <Link to="/" className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft size={14} strokeWidth={1.5} /> {t("nav.stays")}</Link>
      <ErrorNote error={{ ...err, message: t(`errors.${err.error_code}`, { defaultValue: err.message }) }} />
    </div>
  );
  if (!q) return null;
  const nights = daysBetween(q.checkin_date, q.checkout_date);
  const expired = seconds === 0;
  const booked = book.data?.status === "confirmed";

  return (
    <div className="mx-auto max-w-[1040px] space-y-10">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted transition-colors hover:text-ink">
        <ArrowLeft size={14} strokeWidth={1.5} /> {t("nav.stays")}
      </button>

      <article className="panel rise overflow-hidden" aria-label={t("quote.boarding")}>
        {/* header band */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-ink px-6 py-3 text-paper sm:px-8">
          <p className="flex items-center gap-2.5"><Mark size={18} tone="light" />
            <span className="eyebrow !text-night-text">Rate Ledger · {t("quote.boarding")}</span></p>
          <p className="num text-[12px] text-night-text">{t("quote.pass_no")} <span className="text-white">{q.quote_id}</span></p>
        </div>

        <div className="flex flex-col md:flex-row">
          <div className="min-w-0 flex-1 p-6 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <h1 className="min-w-0 text-[28px] leading-[1.1] sm:text-[34px]">{q.entity_id && <RoomTitle roomId={q.entity_id} />}</h1>
              {booked ? <span className="stamp stamp-floor stamp-lg shrink-0">{t("quote.booked")}</span>
                : !expired && <span className="stamp stamp-override stamp-lg shrink-0">{t("quote.held_badge")}</span>}
            </div>

            {/* the stay, laid out like a route */}
            <div className="mt-7 grid grid-cols-[1fr_auto_1fr] items-end gap-3 border-y border-rule py-5">
              <div>
                <p className="eyebrow">{t("search.checkin")}</p>
                <p className="display mt-1 text-[26px] leading-none sm:text-[30px]">{formatDate(q.checkin_date, locale)}</p>
                <p className="num mt-1 text-[12px] text-ink-muted">{weekday(q.checkin_date, locale)}</p>
              </div>
              <div className="flex flex-col items-center pb-5">
                <span className="num text-[11px] text-ink-muted">{t("search.nights", { count: nights })}</span>
                <span className="mt-1 flex w-16 items-center sm:w-36"><span className="h-px flex-1 border-t border-dashed border-ink-faint" /><ArrowRight size={14} strokeWidth={1.5} className="text-ink-faint" /></span>
              </div>
              <div className="text-right">
                <p className="eyebrow">{t("search.checkout")}</p>
                <p className="display mt-1 text-[26px] leading-none sm:text-[30px]">{formatDate(q.checkout_date, locale)}</p>
                <p className="num mt-1 text-[12px] text-ink-muted">{weekday(q.checkout_date, locale)}</p>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-end justify-between gap-5">
              <div>
                <p className="eyebrow">{t("quote.total")} · {t("quote.guests")} {formatNumber(q.party_size, locale)}</p>
                <p className="display-price mt-1.5 text-[46px] leading-none text-ink sm:text-[54px]">{formatMoney(q.total.amount, q.total.currency, locale)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="quiet" onClick={() => window.open(window.location.href, "_blank", "noopener")}
                  title={t("quote.compare_note")}><ExternalLink size={14} strokeWidth={1.5} />{t("quote.compare")}</Button>
                <Button variant="primary" className="px-6" disabled={expired || booked || book.isPending} onClick={() => book.mutate(q.quote_id)}>
                  {booked ? t("quote.booked") : t("quote.book")}
                </Button>
              </div>
            </div>
            {bookErr && <div className="mt-3"><ErrorNote error={{ ...bookErr, message: t(`errors.${bookErr.error_code}`, { defaultValue: bookErr.message }) }} /></div>}
            {booked && <p className="mt-3 text-[13px] text-teal">{t("quote.booked_note")}</p>}

            <div className="mt-7">
              <p className="eyebrow mb-2">{t("quote.nightly")}</p>
              <ul className="ledger border-y border-rule">
                {q.nightly.map((n) => (
                  <li key={n.for_date} className="flex items-center justify-between py-2.5 text-[13.5px]">
                    <span className="num text-ink-muted">{weekday(n.for_date, locale)} · {formatDate(n.for_date, locale)}</span>
                    <span className="num text-ink">{formatMoney(n.price.amount, n.price.currency, locale)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="perforation hidden md:block" aria-hidden />
          <div className="perforation perforation-h md:hidden" aria-hidden />

          {/* stub */}
          <aside className="flex w-full flex-col justify-between gap-7 bg-paper-deep/50 p-6 sm:p-8 md:w-[290px]">
            <div>
              <p className="eyebrow">{t("quote.pass_no")}</p>
              <p className="num mt-1 break-all text-[14px] text-ink" data-testid="pass-no">{q.quote_id}</p>
            </div>
            <div>
              <p className="eyebrow">{expired ? t("quote.expired") : t("quote.held")}</p>
              <div className="mt-2">{seconds !== null && <Gate seconds={seconds} locale={locale} />}</div>
              {!expired && <p className="mt-2 text-[12px] leading-snug text-ink-muted">{t("quote.held_note")}</p>}
            </div>
            <div>
              <span className="stamp stamp-ok">{t("results.within")}</span>
              <div className="mt-4 h-12 w-full opacity-80" aria-hidden
                style={{ backgroundImage: "repeating-linear-gradient(90deg, var(--ink) 0 1px, transparent 1px 3px, var(--ink) 3px 5px, transparent 5px 6px, var(--ink) 6px 7px, transparent 7px 10px)" }} />
              <p className="num mt-1.5 break-all text-[10px] tracking-[0.2em] text-ink-faint">{q.quote_id.toUpperCase()}</p>
            </div>
          </aside>
        </div>
      </article>

      <section className="rise" aria-labelledby="why" style={{ animationDelay: "80ms" }}>
        <div className="flex items-end justify-between border-b border-ink pb-3">
          <div>
            <p className="eyebrow text-brass">{t("home.pipeline_label")}</p>
            <h2 id="why" className="mt-1 text-[28px]">{t("quote.why")}</h2>
          </div>
          <Button variant="ghost" onClick={() => setShowWhy(!showWhy)} aria-expanded={showWhy}>{showWhy ? t("quote.hide") : t("quote.why")}</Button>
        </div>
        {showWhy && (
          <>
            <ol className="ledger">
              {q.reasons.map((r, i) => (
                <li key={i} className="grid grid-cols-[36px_1fr] gap-3 py-4 text-[15.5px] leading-relaxed">
                  <span className="num pt-1 text-[12px] text-brass">{formatNumber(i + 1, locale).padStart(2, formatNumber(0, locale))}</span>
                  <span className="text-ink-soft">{r.text}</span>
                </li>
              ))}
            </ol>
            {q.warnings.includes("low_confidence") && <p className="mt-2 border-l-2 border-saffron pl-3 text-[13px] text-saffron-text">{t("quote.low_confidence")}</p>}
            <p className="mt-4 inline-flex items-center gap-1.5 text-[12px] text-ink-muted">
              {q.reasons[0]?.source === "llm" ? <Sparkles size={13} strokeWidth={1.5} /> : <ShieldCheck size={13} strokeWidth={1.5} />}
              {q.reasons[0]?.source === "llm" ? t("quote.source_llm") : t("quote.source_template")}
            </p>
          </>
        )}
      </section>
    </div>
  );
}

function RoomTitle({ roomId }: { roomId: string }) {
  const meta = useQuery({
    queryKey: ["room-meta", roomId],
    queryFn: () => api.get<{ hotel_name: string; room_name: string; city_name: string }>(`/v1/catalog/rooms/${roomId}`),
    staleTime: Infinity,
  });
  if (!meta.data) return <span className="num text-ink-muted">{roomId}</span>;
  return (
    <span>{meta.data.hotel_name}
      <span className="mt-1.5 block text-[14px] font-normal tracking-normal text-ink-muted" style={{ fontFamily: "var(--font-ui)" }}>
        {meta.data.room_name} · {meta.data.city_name}
      </span>
    </span>
  );
}
