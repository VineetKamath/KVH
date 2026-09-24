import { useQuery } from "@tanstack/react-query";
import Decimal from "decimal.js";
import { ArrowRight, ArrowDownRight, ArrowUpRight, Check, Minus, Plus, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type { CatalogCities, Room } from "../../api/types";
import { Button, Empty, ErrorNote, Skeleton } from "../../components/ui";
import { Sparkline } from "../../charts/Sparkline";
import { addDays, daysBetween, formatDate } from "../../lib/dates";
import { useLocale } from "../../lib/locale";
import { formatNumber, formatPct, formatPrice as formatMoney, type Locale } from "../../lib/money";

const DEMO_CITY = "Udaipur";

/** signals → engine → bounded published price: the product's visual language */
function Pipeline() {
  const { t } = useTranslation();
  const steps = ["p_base", "p_demand", "p_forecast", "p_event", "p_limit", "p_publish"];
  return (
    <div>
      <p className="eyebrow mb-2.5">{t("home.pipeline_label")}</p>
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
        {steps.map((s, i) => (
          <li key={s} className="flex items-center gap-1.5">
            <span className={`chip ${s === "p_limit" ? "!border-teal !text-teal" : ""} ${s === "p_publish" ? "!border-ink !bg-ink !text-paper" : ""}`}>
              <span className="text-ink-faint">{String(i + 1).padStart(2, "0")}</span>{t(`home.${s}`)}
            </span>
            {i < steps.length - 1 && <ArrowRight size={12} strokeWidth={1.5} className="text-ink-faint" aria-hidden />}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Clearly-labelled illustration of a price breakdown (fixed example numbers, not live data). */
function Specimen() {
  const { t } = useTranslation();
  const rows: [string, string, string][] = [
    [t("home.p_base"), "", "₹5,200"], [t("home.p_demand"), "+2.1%", "+₹109"], [t("home.p_forecast"), "−1.4%", "−₹74"],
    [t("home.p_event"), "+12.0%", "+₹628"], [t("home.p_limit"), "✓", "₹0"],
  ];
  return (
    <figure className="panel relative overflow-hidden" aria-label={t("home.specimen")}>
      <div className="flex items-center justify-between border-b border-rule bg-paper-deep/50 px-5 py-2.5">
        <p className="eyebrow">{t("home.specimen")}</p>
      </div>
      <ul className="ledger px-5 text-[13px]">
        {rows.map(([k, m, v]) => (
          <li key={k} className="grid grid-cols-[1fr_auto_84px] items-center gap-3 py-2.5">
            <span className="text-ink-soft">{k}</span>
            <span className={`num text-[11.5px] ${m.startsWith("+") ? "text-saffron-text" : m.startsWith("−") ? "text-teal" : "text-ink-faint"}`}>{m}</span>
            <span className="num text-right">{v}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-end justify-between border-t border-ink px-5 py-4">
        <div><span className="eyebrow">{t("home.p_publish")}</span><div className="mt-2"><span className="stamp stamp-ok">{t("results.within")}</span></div></div>
        <span className="display-price text-[40px] leading-none">₹5,863</span>
      </div>
      <figcaption className="border-t border-rule px-5 py-2.5 text-[11.5px] text-ink-muted">{t("home.specimen_note")}</figcaption>
    </figure>
  );
}

function priceOn(r: Room, d: string | null) {
  if (!d) return null;
  const i = r.sparkline.findIndex((p) => p.d === d);
  if (i < 0) return null;
  return { price: r.sparkline[i].p, prev: i > 0 ? r.sparkline[i - 1].p : null };
}

function RoomRow({ r, locale, qs, checkin }: { r: Room; locale: Locale; qs: string; checkin: string | null }) {
  const { t } = useTranslation();
  const tonight = priceOn(r, checkin);
  const price = tonight?.price ?? r.from_price;
  const move = tonight?.prev ? new Decimal(tonight.price).div(tonight.prev).minus(1).times(100) : null;
  const all = r.sparkline.map((p) => new Decimal(p.p));
  const lo = all.length ? Decimal.min(...all) : null, hi = all.length ? Decimal.max(...all) : null;
  const lowest = lo !== null && new Decimal(price).equals(lo);
  return (
    <li className="rise group grid gap-5 py-6 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] md:items-center">
      <div className="min-w-0">
        <p className="eyebrow flex items-center gap-1.5">
          {Array.from({ length: r.star_rating }, (_, i) => <Star key={i} size={10} className="fill-brass text-brass" aria-hidden />)}
          <span className="sr-only">{t("results.stars", { count: r.star_rating })}</span>
          <span className="ml-1">{r.property_type}</span>
        </p>
        <h3 className="mt-1.5 truncate text-[23px] leading-tight">{r.hotel_name}</h3>
        <p className="mt-0.5 text-[13px] text-ink-muted">{r.room_name} · {t("results.centre", { km: formatNumber(r.distance_to_centre_km, locale, 1) })}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="inline-flex items-center gap-1 text-[11.5px] text-teal"><Check size={12} strokeWidth={2} />{t("results.within")}</span>
          {lowest && <span className="inline-flex items-center gap-1 text-[11.5px] text-brass">· {t("results.lowest")}</span>}
        </div>
      </div>
      <div className="min-w-0">
        <p className="eyebrow mb-1">{t("results.price_trail")}</p>
        <Sparkline points={r.sparkline} label={t("results.price_trail")} width={260} height={48} highlight={checkin} />
        {lo && hi && <p className="num mt-1 text-[11px] text-ink-faint">{t("results.range")}: {formatMoney(lo.toFixed(2), r.currency, locale)} – {formatMoney(hi.toFixed(2), r.currency, locale)}</p>}
      </div>
      <div className="flex items-end justify-between gap-6 md:flex-col md:items-end md:gap-2">
        <div className="md:text-right">
          <p className="text-[11px] text-ink-muted">{tonight ? t("results.first_night") : t("results.from")}</p>
          <p className="display-price text-[34px] leading-none text-ink">{formatMoney(price, r.currency, locale)}</p>
          <p className="mt-1 flex items-center gap-1 text-[11.5px] text-ink-muted md:justify-end">
            {move && !move.isZero() ? (<>
              {move.gt(0) ? <ArrowUpRight size={12} className="text-saffron-text" /> : <ArrowDownRight size={12} className="text-teal" />}
              <span className={`num ${move.gt(0) ? "text-saffron-text" : "text-teal"}`}>{formatPct(move.toFixed(1), locale)}</span> {t("results.vs_prev")}
            </>) : t("results.per_night")}
          </p>
        </div>
        <Link to={`/pass/${r.room_type_id}?${qs}`}
          className="inline-flex h-10 items-center gap-2 rounded-[3px] border border-ink px-4 text-[13px] font-medium text-ink transition-colors group-hover:bg-ink group-hover:text-paper">
          {t("results.pass")}<ArrowRight size={15} strokeWidth={1.5} />
        </Link>
      </div>
    </li>
  );
}

export default function Search() {
  const { t } = useTranslation();
  const [locale] = useLocale();
  const [params, setParams] = useSearchParams();
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api.get<CatalogCities>("/v1/catalog/cities") });

  const cities = catalog.data?.cities ?? [];
  const defaultCity = cities.find((c) => c.name === DEMO_CITY)?.city_id ?? cities[0]?.city_id ?? "";
  const from = catalog.data?.bookable_from;
  const [city, setCity] = useState(params.get("city") ?? "");
  const [checkin, setCheckin] = useState(params.get("in") ?? "");
  const [checkout, setCheckout] = useState(params.get("out") ?? "");
  const [guests, setGuests] = useState(Number(params.get("g") ?? 2));

  useEffect(() => {
    if (!catalog.data) return;
    if (!city) setCity(defaultCity);
    if (!checkin && from) { const ci = addDays(from, 41); setCheckin(ci); setCheckout(addDays(ci, 2)); }
  }, [catalog.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const nights = checkin && checkout ? daysBetween(checkin, checkout) : 0;
  const submitted = params.get("city");
  const rooms = useQuery({
    queryKey: ["rooms", submitted],
    queryFn: () => api.get<{ city: { name: string }; rooms: Room[] }>(`/v1/catalog/cities/${submitted}/rooms`),
    enabled: !!submitted,
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setParams({ city, in: checkin, out: checkout, g: String(guests) });
  };
  const cityName = useMemo(() => cities.find((c) => c.city_id === submitted)?.name ?? "", [cities, submitted]);
  const qs = `in=${params.get("in")}&out=${params.get("out")}&g=${params.get("g")}`;

  return (
    <div className="space-y-14">
      {/* hero: what this is, how a price is made */}
      <section className="grid gap-10 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] lg:items-center">
        <div className="rise">
          <p className="eyebrow text-brass">{t("home.kicker")}</p>
          <h1 className="display mt-4 text-[44px] leading-[1.02] sm:text-[64px]">
            {t("home.title_a")} <span className="italic-serif text-indigo">{t("home.title_b")}</span>
          </h1>
          <p className="mt-5 max-w-[58ch] text-[15.5px] leading-relaxed text-ink-soft">{t("home.lede")}</p>
          <div className="mt-7"><Pipeline /></div>
        </div>
        <div className="rise hidden sm:block" style={{ animationDelay: "90ms" }}><Specimen /></div>
      </section>

      {/* search: the front door */}
      <section aria-labelledby="search-title">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="search-title" className="text-[22px]">{t("home.search_title")}</h2>
          {catalog.data && (
            <p className="num text-[12px] text-ink-muted">
              {t("search.window", { from: formatDate(catalog.data.bookable_from, locale), to: formatDate(catalog.data.bookable_to, locale) })}
            </p>
          )}
        </div>
        <form onSubmit={onSubmit} className="panel grid grid-cols-2 gap-x-4 gap-y-4 p-4 sm:p-5 lg:grid-cols-[1.4fr_1fr_1fr_0.8fr_auto] lg:items-end" aria-label={t("search.where")}>
          <label className="field col-span-2 lg:col-span-1">
            <span>{t("search.city")}</span>
            <select className="input" value={city} onChange={(e) => setCity(e.target.value)} required>
              {cities.map((c) => <option key={c.city_id} value={c.city_id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>{t("search.checkin")}</span>
            <input className="input num" type="date" value={checkin} min={from} max={catalog.data?.bookable_to}
              onChange={(e) => { setCheckin(e.target.value); if (checkout <= e.target.value) setCheckout(addDays(e.target.value, 1)); }} required />
          </label>
          <label className="field">
            <span>{t("search.checkout")}</span>
            <input className="input num" type="date" value={checkout} min={checkin ? addDays(checkin, 1) : from} max={catalog.data?.bookable_to}
              onChange={(e) => setCheckout(e.target.value)} required />
          </label>
          <div className="field col-span-2 sm:col-span-1">
            <span>{t("search.guests")}</span>
            <div className="flex h-10 items-center justify-between rounded-[3px] border border-rule-strong bg-surface px-1">
              <button type="button" aria-label="fewer guests" className="rounded p-2 text-ink-muted hover:text-ink" onClick={() => setGuests(Math.max(1, guests - 1))}><Minus size={14} strokeWidth={1.5} /></button>
              <span className="num w-6 text-center">{formatNumber(guests, locale)}</span>
              <button type="button" aria-label="more guests" className="rounded p-2 text-ink-muted hover:text-ink" onClick={() => setGuests(Math.min(8, guests + 1))}><Plus size={14} strokeWidth={1.5} /></button>
            </div>
          </div>
          <div className="col-span-2 flex flex-col gap-1 sm:col-span-1 lg:items-end">
            <span className="num text-[11px] text-ink-muted">{nights > 0 ? t("search.nights", { count: nights }) : " "}</span>
            <Button variant="primary" type="submit" className="h-10 w-full px-6 lg:w-auto" disabled={!city || nights < 1}>
              {t("search.find")}<ArrowRight size={15} strokeWidth={1.5} />
            </Button>
          </div>
        </form>
      </section>

      {catalog.isError && <ErrorNote error={catalog.error} />}

      {submitted && (
        <section aria-live="polite">
          <div className="flex flex-wrap items-end justify-between gap-2 border-b border-ink pb-3">
            <h2 className="text-[30px] leading-tight">{t("results.title", { city: cityName })}</h2>
            {rooms.data && (
              <p className="num text-[12px] text-ink-muted">
                {formatDate(params.get("in") ?? "", locale)} → {formatDate(params.get("out") ?? "", locale)} · {t("results.meta", { count: rooms.data.rooms.length })}
              </p>
            )}
          </div>
          {rooms.isLoading && <div className="py-6"><Skeleton lines={6} /></div>}
          {rooms.isError && <ErrorNote error={rooms.error} />}
          {rooms.data && rooms.data.rooms.length === 0 && <div className="mt-6"><Empty title={t("results.empty")} /></div>}
          <ul className="ledger">
            {rooms.data?.rooms.map((r) => <RoomRow key={r.room_type_id} r={r} locale={locale} qs={qs} checkin={params.get("in")} />)}
          </ul>
        </section>
      )}

      {/* how it works: three principles, open layout */}
      <section className="double-rule grid gap-8 pt-8 md:grid-cols-3">
        {[1, 2, 3].map((n) => (
          <div key={n}>
            <p className="num text-[12px] text-brass">0{n}</p>
            <h3 className="mt-1 text-[20px]">{t(`home.how_${n}_t`)}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">{t(`home.how_${n}_d`)}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
