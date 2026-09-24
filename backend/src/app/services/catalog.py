"""Traveller catalogue: cities that have priced rooms, their hotels (via the synthetic catalog link) and rooms."""
from __future__ import annotations

import sqlite3

from app.core.money import dec, money_str
from app.services.errors import invalid_id


def cities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT c.city_id, c.name, c.state, c.country_code, c.primary_language, c.region, COUNT(l.room_type_id) AS rooms "
        "FROM dp_catalog_link l JOIN cities c ON c.city_id = l.city_id WHERE l.status = 'active' "
        "GROUP BY c.city_id ORDER BY rooms DESC, c.name").fetchall()
    return [dict(r) for r in rows]


def rooms(conn: sqlite3.Connection, city_id: str) -> dict:
    city = conn.execute("SELECT city_id, name, state, primary_language, timezone FROM cities WHERE city_id = ?", (city_id,)).fetchone()
    if city is None:
        raise invalid_id("city")
    out = []
    for r in conn.execute(
        "SELECT l.room_type_id, l.room_name, h.hotel_id, h.name AS hotel_name, h.star_rating, h.guest_score, h.review_count, "
        "h.property_type, h.distance_to_centre_km, h.address_line, h.checkin_time, h.checkout_time "
        "FROM dp_catalog_link l JOIN hotels h ON h.hotel_id = l.hotel_id WHERE l.city_id = ? AND l.status = 'active' "
        "ORDER BY h.star_rating DESC, h.name", (city_id,)):
        spark = conn.execute(
            "SELECT for_date, published_price, currency FROM dp_price_decision WHERE entity_type = 'room_type' "
            "AND entity_id = ? AND is_live = 1 ORDER BY for_date", (r["room_type_id"],)).fetchall()
        if not spark:
            continue
        prices = [dec(s["published_price"]) for s in spark]
        out.append({**dict(r), "currency": spark[0]["currency"],
                    "from_price": money_str(min(prices)),
                    "sparkline": [{"d": s["for_date"], "p": s["published_price"]} for s in spark]})
    return {"city": dict(city), "rooms": out}


def room_meta(conn: sqlite3.Connection, room_id: str) -> dict:
    r = conn.execute(
        "SELECT l.room_type_id, l.room_name, l.link_source, h.hotel_id, h.name AS hotel_name, h.star_rating, c.city_id, "
        "c.name AS city_name, c.primary_language FROM dp_catalog_link l JOIN hotels h ON h.hotel_id = l.hotel_id "
        "JOIN cities c ON c.city_id = l.city_id WHERE l.room_type_id = ?", (room_id,)).fetchone()
    return dict(r) if r else {"room_type_id": room_id, "room_name": "Room", "hotel_name": None, "city_name": None}
