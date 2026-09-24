import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, sessionId, type ApiError } from "../../api/client";
import type { Quote } from "../../api/types";
import { Button, ErrorNote, Skeleton } from "../../components/ui";
import { daysBetween, formatDate, weekday } from "../../lib/dates";
import { useLocale } from "../../lib/locale";
import { formatMoney, formatNumber, type Locale } from "../../lib/money";

function useCountdown(expiresAt?: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  if (!expiresAt) return null;
  return Math.max(0, Math.floor((Date.parse(expiresAt) - now) / 1000));
}

function Gate({ seconds, locale }: { seconds: number; locale: Locale }) {
  const m = Math.floor(seconds / 60), s = seconds % 60;
  const pad = (n: number) => formatNumber(n, locale).padStart(2, locale === "en-IN" ? "0" : formatNumber(0, locale));
  return <span className="num text-[34px] leading-none tracking-tight text-ink" aria-live="off">{pad(m)}:{pad(s)}</span>;
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

  if (quote.isLoading) return <div className="card p-8"><Skeleton lines={7} /></div>;
  if (err) return (
    <div className="space-y-4">
      <Link to="/" className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft size={14} strokeWidth={1.5} /> {t("nav.stays")}</Link>
      <ErrorNote error={{ ...err, message: t(`errors.${err.error_code}`, { defaultValue: err.message }) }} />
    </div>
  );
  if (!q) return null;
  const nights = daysBetween(q.checkin_date, q.checkout_date);
  const expired = seconds === 0;
  const booked = book.data?.status === "confirmed";

  return (
    <div className="space-y-6">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink">
        <ArrowLeft size={14} strokeWidth={1.5} /> {t("nav.stays")}
      </button>

      <article className="card flex flex-col overflow-hidden md:flex-row" aria-label={t("quote.boarding")}>
        <div className="flex-1 p-6 sm:p-8">
          <div className="flex items-center justify-between">
            <p className="eyebrow">{t("quote.boarding")}</p>
            {booked && <span className="stamp stamp-floor">{t("quote.booked")}</span>}
          </div>
          <h1 className="mt-2 text-[30px] leading-tight">{q.entity_id && roomTitle(q)}</h1>
          <dl className="mt-5 grid grid-cols-3 gap-4 border-y border-rule py-4">
            <div><dt className="eyebrow">{t("quote.stay")}</dt>
              <dd className="num mt-1 text-[15px]">{formatDate(q.checkin_date, locale)} → {formatDate(q.checkout_date, locale)}</dd></div>
            <div><dt className="eyebrow">{t("search.nights", { count: nights })}</dt><dd className="num mt-1 text-[15px]">{formatNumber(nights, locale)}</dd></div>
            <div><dt className="eyebrow">{t("quote.guests")}</dt><dd className="num mt-1 text-[15px]">{formatNumber(q.party_size, locale)}</dd></div>
          </dl>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="eyebrow">{t("quote.total")}</p>
              <p className="display-price mt-1 text-[44px] leading-none text-ink">{formatMoney(q.total.amount, q.total.currency, locale)}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="quiet" onClick={() => window.open(window.location.href, "_blank", "noopener")}
                title={t("quote.compare_note")}><ExternalLink size={14} strokeWidth={1.5} />{t("quote.compare")}</Button>
              <Button variant="primary" disabled={expired || booked || book.isPending} onClick={() => book.mutate(q.quote_id)}>
                {booked ? t("quote.booked") : t("quote.book")}
              </Button>
            </div>
          </div>
          {bookErr && <div className="mt-3"><ErrorNote error={{ ...bookErr, message: t(`errors.${bookErr.error_code}`, { defaultValue: bookErr.message }) }} /></div>}
          {booked && <p className="mt-3 text-[13px] text-teal">{t("quote.booked_note")}</p>}

          <div className="mt-6">
            <p className="eyebrow mb-2">{t("quote.nightly")}</p>
            <ul className="ledger rounded-[6px] border border-rule">
              {q.nightly.map((n) => (
                <li key={n.for_date} className="flex items-center justify-between px-3 py-2 text-[13px]">
                  <span className="num text-ink-muted">{weekday(n.for_date, locale)} {formatDate(n.for_date, locale)}</span>
                  <span className="num">{formatMoney(n.price.amount, n.price.currency, locale)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="perforation hidden md:block" aria-hidden />
        <div className="perforation perforation-h md:hidden" aria-hidden />

        <aside className="flex w-full flex-col justify-between gap-6 bg-paper-deep/60 p-6 md:w-[260px]">
          <div>
            <p className="eyebrow">{t("quote.pass_no")}</p>
            <p className="num mt-1 break-all text-[13px] text-ink">{q.quote_id}</p>
          </div>
          <div>
            <p className="eyebrow">{expired ? t("quote.expired") : t("quote.held")}</p>
            <div className="mt-2">{seconds !== null && <Gate seconds={seconds} locale={locale} />}</div>
            {!expired && <p className="mt-2 text-[12px] leading-snug text-ink-muted">{t("quote.held_note")}</p>}
          </div>
          <div className="h-10 w-full opacity-70" aria-hidden
            style={{ backgroundImage: "repeating-linear-gradient(90deg, var(--ink) 0 1px, transparent 1px 3px, var(--ink) 3px 5px, transparent 5px 8px)" }} />
        </aside>
      </article>

      <section className="card p-6" aria-labelledby="why">
        <div className="flex items-center justify-between">
          <h2 id="why" className="text-[22px]">{t("quote.why")}</h2>
          <Button variant="ghost" onClick={() => setShowWhy(!showWhy)} aria-expanded={showWhy}>{showWhy ? t("quote.hide") : t("quote.why")}</Button>
        </div>
        {showWhy && (
          <>
            <ol className="ledger mt-3">
              {q.reasons.map((r, i) => (
                <li key={i} className="flex gap-3 py-2.5 text-[15px] leading-relaxed">
                  <span className="num w-5 shrink-0 pt-0.5 text-[12px] text-ink-faint">{formatNumber(i + 1, locale)}</span>
                  <span>{r.text}</span>
                </li>
              ))}
            </ol>
            {q.warnings.includes("low_confidence") && <p className="mt-3 text-[13px] text-saffron-text">{t("quote.low_confidence")}</p>}
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

function roomTitle(q: Quote) {
  return <RoomTitle roomId={q.entity_id} />;
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
      <span className="block text-[15px] font-normal text-ink-muted" style={{ fontFamily: "var(--font-ui)" }}>
        {meta.data.room_name} · {meta.data.city_name}
      </span>
    </span>
  );
}
