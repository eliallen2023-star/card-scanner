"""The Trending tab: what our own scans say about each prospect's market.

Only data the spotter already collected (no extra API calls, no other sites):
  * lots this week vs last week (by when we first saw them) and the median ASKING
    price of those lots, with the week-over-week change
  * auctions that ended in the last 7 days: how many, and the average number of bids
    (the last count we saw, so a little low)
Asking prices aren't sale prices, and lot sizes vary, so read this as a rough signal:
more lots at higher asks and more bids = more interest.
"""
import statistics

import score
from store import now, parse_time

MIN_LOTS = 3      # a prospect needs this many lots this week to show up


def build(store, parser, ranks):
    """Returns (rows, days of data we have). One row per prospect."""
    t = now()
    stats, oldest = {}, t
    for r in store.all_spotted():
        first = parse_time(r["first_seen"])
        oldest = min(oldest, first)
        info = score.read_lot(r, store.get_lot_details(r["item_id"]), parser)
        days = (t - first).total_seconds() / 86400
        for p in info["players"]:
            s = stats.setdefault(p, {"this": [], "last": [], "bids": []})
            if r["buying"] == "BIN":
                if days < 7:
                    s["this"].append(r["price"])
                elif days < 14:
                    s["last"].append(r["price"])
            else:
                ends = parse_time(r["end_time"])
                if ends and ends < t and (t - ends).total_seconds() < 7 * 86400:
                    s["bids"].append(r["bid_count"] or 0)

    rows = []
    for p, s in stats.items():
        if len(s["this"]) < MIN_LOTS and len(s["bids"]) < MIN_LOTS:
            continue
        this = statistics.median(s["this"]) if s["this"] else None
        last = statistics.median(s["last"]) if len(s["last"]) >= MIN_LOTS else None
        change = (this / last - 1) if this and last else None
        rows.append({"player": p.title(), "rank": ranks.get(p), "lots": len(s["this"]),
                     "median": this, "last_median": last, "change": change,
                     "auctions": len(s["bids"]),
                     "avg_bids": statistics.mean(s["bids"]) if s["bids"] else None})
    # biggest price rise first; prospects without a comparison yet after, by number of lots
    rows.sort(key=lambda x: (x["change"] is None, -(x["change"] or 0), -x["lots"]))
    return rows, (t - oldest).total_seconds() / 86400
