"""Sold prices YOU typed into manual_comps.csv, turned into lot-scoring hints.

manual_comps.csv columns: title,total_price,sold_date[,sell_through]
  * title        the card that sold, e.g. "Jesus Made 2025 Bowman Chrome 1st Auto"
  * total_price  price + shipping it sold for
  * sold_date    YYYY-MM-DD
  * sell_through optional, e.g. 65 for 65% (from eBay Product Research: how many of the
                 listings for this player sold). Faster-selling players score a bit higher.

Nothing here is fetched from any website: it's only what you type in.
"""
import csv
import os
import statistics

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_comps.csv")


def load(parser, path=FILE):
    """Returns {player: {"median": $ or None, "sales": n, "sell_through": % or None}}."""
    if not os.path.exists(path):
        return {}
    prices, through = {}, {}
    with open(path, newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel's CSVs too
        for row in csv.DictReader(f):
            players = parser.players_in((row.get("title") or "").lower())
            if len(players) != 1:
                continue                  # one player per row, so the price is theirs
            p = players[0]
            try:
                prices.setdefault(p, []).append(float(row.get("total_price") or ""))
            except ValueError:
                pass
            try:
                through.setdefault(p, []).append(float(str(row.get("sell_through") or "").strip("% ")))
            except ValueError:
                pass
    out = {}
    for p in set(prices) | set(through):
        out[p] = {"median": statistics.median(prices[p]) if prices.get(p) else None,
                  "sales": len(prices.get(p, [])),
                  "sell_through": statistics.mean(through[p]) if through.get(p) else None}
    return out


def points(info, market):
    """(points, reasons) for a lot from your sold prices. Conservative: each named
    prospect counts as ONE card at the median price you recorded."""
    if not market:
        return 0, []
    pts, reasons = 0, []
    known = [market[p]["median"] for p in info["players"]
             if p in market and market[p]["median"] is not None]
    if known:
        value = sum(known)
        if value >= 1.5 * info["total"]:
            pts += 10
            reasons.append(f"your sold prices: named cards ~${value:.0f} vs ${info['total']:.0f} +10")
        elif value >= info["total"]:
            pts += 5
            reasons.append(f"your sold prices: named cards ~${value:.0f} vs ${info['total']:.0f} +5")
    # sell-through: 50% = average, each 10 points above it +1, at most +3 for the lot
    st = [market[p]["sell_through"] for p in info["players"]
          if p in market and market[p]["sell_through"] is not None]
    if st:
        add = max(0, min(3, int((max(st) - 50) // 10)))
        if add:
            pts += add
            reasons.append(f"sells fast ({max(st):.0f}% sell-through) +{add}")
    return pts, reasons
