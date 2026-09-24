import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type { CatalogCities, Room } from "../../api/types";
import { Button, Empty, ErrorNote, Skeleton } from "../../components/ui";
import { Sparkline } from "../../charts/Sparkline";
import { addDays, daysBetween, formatDate } from "../../lib/dates";
import { useLocale } from "../../lib/locale";
import { formatMoney, formatNumber } from "../../lib/money";

const DEMO_CITY = "Udaipur";

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

  return (
    <div className="space-y-10">
      <section className="grid gap-8 lg:grid-cols-[1fr_1.35fr] lg:items-end">
        <div>
          <p className="eyebrow">{t("tagline")}</p>
          <h1 className="mt-2 text-[40px] leading-[1.05] sm:text-[48px]">{t("search.where")}</h1>
          {catalog.data && (
            <p className="mt-3 text-[13px] text-ink-muted">
              {t("search.window", { from: formatDate(catalog.data.bookable_from, locale), to: formatDate(catalog.data.bookable_to, locale) })}
            </p>
          )}
        </div>
        <form onSubmit={onSubmit} className="card grid grid-cols-2 gap-3 p-4 sm:grid-cols-[1.3fr_1fr_1fr_auto] sm:items-end" aria-label={t("search.where")}>
          <label className="field col-span-2 sm:col-span-1">
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
            <div className="flex h-9 items-center gap-1 rounded-[5px] border border-rule-strong bg-surface px-1">
              <button type="button" aria-label="fewer guests" className="rounded p-1.5 text-ink-muted hover:text-ink" onClick={() => setGuests(Math.max(1, guests - 1))}><Minus size={14} strokeWidth={1.5} /></button>
              <span className="num w-6 text-center">{formatNumber(guests, locale)}</span>
              <button type="button" aria-label="more guests" className="rounded p-1.5 text-ink-muted hover:text-ink" onClick={() => setGuests(Math.min(8, guests + 1))}><Plus size={14} strokeWidth={1.5} /></button>
            </div>
          </div>
          <div className="col-span-2 flex items-center justify-between gap-3 border-t border-rule pt-3 sm:col-span-4">
            <span className="text-[13px] text-ink-muted">{nights > 0 ? t("search.nights", { count: nights }) : " "}</span>
            <Button variant="primary" type="submit" disabled={!city || nights < 1}>{t("search.find")}<ArrowRight size={15} strokeWidth={1.5} /></Button>
          </div>
        </form>
      </section>

      {catalog.isError && <ErrorNote error={catalog.error} />}
      {submitted && (
        <section aria-live="polite">
          <h2 className="mb-4 text-[24px]">{t("results.title", { city: cityName })}</h2>
          {rooms.isLoading && <Skeleton lines={5} />}
          {rooms.isError && <ErrorNote error={rooms.error} />}
          {rooms.data && rooms.data.rooms.length === 0 && <Empty title={t("results.empty")} />}
          <ul className="grid gap-4 md:grid-cols-2">
            {rooms.data?.rooms.map((r) => (
              <li key={r.room_type_id} className="card flex flex-col gap-4 p-5 transition-colors hover:border-rule-strong">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="eyebrow">{t("results.stars", { count: r.star_rating })} · {r.property_type}</p>
                    <h3 className="mt-1 truncate text-[20px]">{r.hotel_name}</h3>
                    <p className="text-[13px] text-ink-muted">{r.room_name} · {t("results.centre", { km: formatNumber(r.distance_to_centre_km, locale, 1) })}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] text-ink-muted">{t("results.from")}</p>
                    <p className="display-price text-[24px] text-ink">{formatMoney(r.from_price, r.currency, locale)}</p>
                    <p className="text-[11px] text-ink-muted">{t("results.per_night")}</p>
                  </div>
                </div>
                <div className="flex items-end justify-between gap-4 border-t border-rule pt-3">
                  <div>
                    <p className="eyebrow mb-1">{t("results.price_trail")}</p>
                    <Sparkline points={r.sparkline} label={t("results.price_trail")} />
                  </div>
                  <Link to={`/pass/${r.room_type_id}?in=${params.get("in")}&out=${params.get("out")}&g=${params.get("g")}`}
                    className="inline-flex h-9 items-center gap-2 rounded-[5px] border border-indigo px-3.5 text-[13px] font-medium text-indigo hover:bg-indigo-wash">
                    {t("results.choose")}<ArrowRight size={15} strokeWidth={1.5} />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
