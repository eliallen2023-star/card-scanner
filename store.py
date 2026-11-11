"""SQLite storage: listings we've seen, comps (sales) we've recorded, alerts sent."""
import csv
import hashlib
import json
import os
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  item_id TEXT PRIMARY KEY, title TEXT, player TEXT, card_key TEXT, key_noyear TEXT,
  buying TEXT, price REAL, shipping REAL, bid_count INT, end_time TEXT,
  url TEXT, image TEXT, is_lot INT, first_seen TEXT, last_seen TEXT,
  shipping_known INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS shipping (item_id TEXT PRIMARY KEY, cost REAL, looked_up TEXT);
CREATE TABLE IF NOT EXISTS lot_details (item_id TEXT PRIMARY KEY, details TEXT, looked_up TEXT);
CREATE TABLE IF NOT EXISTS comps (
  comp_id TEXT PRIMARY KEY, card_key TEXT, key_noyear TEXT, total REAL,
  sold_at TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS alerts (
  item_id TEXT PRIMARY KEY, sent_at TEXT, total REAL, median REAL, profit REAL);
CREATE INDEX IF NOT EXISTS comps_key ON comps(card_key);
CREATE INDEX IF NOT EXISTS comps_key2 ON comps(key_noyear);
"""


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        # Databases made by an older version of this app lack this column; add it.
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(listings)")]
        if "shipping_known" not in cols:
            self.db.execute("ALTER TABLE listings ADD COLUMN shipping_known INT DEFAULT 1")

    # ---- small key/value notes, e.g. when we last searched Buy It Now ----
    def get_meta(self, k):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def set_meta(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))

    # ---- shipping costs we looked up one listing at a time (they don't change) ----
    def cached_shipping(self, item_id):
        r = self.db.execute("SELECT cost FROM shipping WHERE item_id=?", (item_id,)).fetchone()
        return r[0] if r else None

    def save_shipping(self, item_id, cost):
        self.db.execute("INSERT OR REPLACE INTO shipping VALUES (?,?,?)",
                        (item_id, cost, iso(now())))

    # ---- lot details we looked up (description lines, players, card count) ----
    def get_lot_details(self, item_id):
        r = self.db.execute("SELECT details FROM lot_details WHERE item_id=?", (item_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def save_lot_details(self, item_id, details):
        self.db.execute("INSERT OR REPLACE INTO lot_details VALUES (?,?,?)",
                        (item_id, json.dumps(details), iso(now())))

    def upsert_listing(self, it, card):
        t = iso(now())
        self.db.execute("""
          INSERT INTO listings (item_id, title, player, card_key, key_noyear, buying,
            price, shipping, bid_count, end_time, url, image, is_lot, first_seen,
            last_seen, shipping_known)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(item_id) DO UPDATE SET price=excluded.price,
            shipping=excluded.shipping, shipping_known=excluded.shipping_known,
            bid_count=excluded.bid_count, end_time=excluded.end_time,
            last_seen=excluded.last_seen""",
            (it["item_id"], it["title"], card.player, card.key, card.key_noyear,
             it["buying"], it["price"], it["shipping"], it["bid_count"],
             it["end_time"], it["url"], it["image"], int(card.is_lot), t, t,
             int(it.get("shipping_known", True))))

    def recent_listings(self, buying, minutes):
        """Listings of one type ("BIN" or "AUCTION") seen in the last `minutes`,
        in the same shape ebay.py returns."""
        since = iso(now() - timedelta(minutes=minutes))
        rows = self.db.execute("SELECT * FROM listings WHERE buying=? AND last_seen>=?",
                               (buying, since)).fetchall()
        return [{"item_id": r["item_id"], "title": r["title"], "buying": r["buying"],
                 "price": r["price"], "shipping": r["shipping"],
                 "shipping_known": bool(r["shipping_known"]), "bid_count": r["bid_count"],
                 "end_time": r["end_time"], "url": r["url"], "image": r["image"]}
                for r in rows]

    def record_finished_auctions(self, max_gap_minutes=30):
        """Auctions that have ended, had bids, and that we saw shortly before the
        end become comps. Their last-seen bid is a bit UNDER the final price
        (last-minute bidding), which keeps estimates conservative: you'll miss
        some deals rather than overpay."""
        rows = self.db.execute("""
          SELECT * FROM listings WHERE buying='AUCTION' AND is_lot=0 AND bid_count>0
            AND end_time < ? AND item_id NOT IN (SELECT comp_id FROM comps)""",
            (iso(now()),)).fetchall()
        added = 0
        for r in rows:
            end, seen = parse_time(r["end_time"]), parse_time(r["last_seen"])
            if end and seen and (end - seen) <= timedelta(minutes=max_gap_minutes):
                self.db.execute("INSERT OR IGNORE INTO comps VALUES (?,?,?,?,?,?)",
                    (r["item_id"], r["card_key"], r["key_noyear"],
                     r["price"] + r["shipping"], r["end_time"], "auction-tracked"))
                added += 1
        return added

    def import_manual_comps(self, path, parser):
        """Rows you typed in yourself (e.g. from looking at 130point by hand)."""
        if not os.path.exists(path):
            return 0
        added = 0
        # utf-8-sig also handles the hidden marker Excel adds when it saves a CSV
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if not row.get("title") or not row.get("total_price"):
                    continue
                card = parser.parse(row["title"])
                if not card or card.is_lot:
                    continue
                cid = "manual-" + hashlib.md5(
                    f'{row["title"]}{row["total_price"]}{row.get("sold_date")}'.encode()
                ).hexdigest()[:16]
                sold = row.get("sold_date") or iso(now())[:10]
                cur = self.db.execute("INSERT OR IGNORE INTO comps VALUES (?,?,?,?,?,?)",
                    (cid, card.key, card.key_noyear, float(row["total_price"]),
                     sold + ("T12:00:00Z" if len(sold) == 10 else ""), "manual"))
                added += cur.rowcount
        return added

    def recent_comps(self, card, days):
        """All recorded sales of this exact card in the last `days` days, newest first."""
        since = iso(now() - timedelta(days=days))
        return self.db.execute(
            "SELECT total, sold_at, source FROM comps WHERE card_key=? AND sold_at>=? "
            "ORDER BY sold_at DESC", (card.key, since)).fetchall()

    def comp_stats(self, card, days):
        """(median sale price, number of sales) for this exact card, or (None, 0)."""
        prices = [r["total"] for r in self.recent_comps(card, days)]
        return (statistics.median(prices), len(prices)) if prices else (None, 0)

    def ask_prices(self, card, days, exclude_item=None):
        """Asking prices (incl. shipping) of OTHER Buy It Now singles of this exact
        card seen in the last `days` days."""
        since = iso(now() - timedelta(days=days))
        return [r[0] for r in self.db.execute(
            "SELECT price + shipping FROM listings WHERE card_key=? AND buying='BIN' "
            "AND is_lot=0 AND last_seen>=? AND item_id<>?",
            (card.key, since, exclude_item or ""))]

    def ask_stats(self, card, days, exclude_item=None):
        """(median asking price, count) of other listings of this exact card, or (None, 0)."""
        prices = self.ask_prices(card, days, exclude_item)
        return (statistics.median(prices), len(prices)) if prices else (None, 0)

    def player_floor_prices(self, player, days):
        """Asking prices of a player's plain cards: Buy It Now singles that are base
        (no auto, no parallel, no serial number) and ungraded."""
        since = iso(now() - timedelta(days=days))
        prices = []
        for key, total in self.db.execute(
                "SELECT card_key, price + shipping FROM listings WHERE player=? AND buying='BIN' "
                "AND is_lot=0 AND last_seen>=?", (player, since)):
            p = key.split("|")   # player|year|product|auto|1st|parallel|serial|grade
            if len(p) == 8 and p[3] == "base" and p[5] == "base" and p[6] == "" and p[7] == "raw":
                prices.append(total)
        return prices

    def comp_count(self):
        return self.db.execute("SELECT COUNT(*) FROM comps").fetchone()[0]

    def already_alerted(self, item_id):
        return self.db.execute("SELECT 1 FROM alerts WHERE item_id=?",
                               (item_id,)).fetchone() is not None

    def mark_alerted(self, item_id, total, median, profit):
        self.db.execute("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?)",
                        (item_id, iso(now()), total, median, profit))

    def prune(self, keep_days=30):
        cutoff = iso(now() - timedelta(days=keep_days))
        self.db.execute("DELETE FROM listings WHERE last_seen < ?", (cutoff,))
        self.db.execute("DELETE FROM shipping WHERE item_id NOT IN (SELECT item_id FROM listings)")
        self.db.execute("DELETE FROM lot_details WHERE item_id NOT IN (SELECT item_id FROM listings)")
        self.db.execute("DELETE FROM comps WHERE sold_at < ?",
                        (iso(now() - timedelta(days=120)),))

    def commit(self):
        self.db.commit()
