"""Value a lot card by card: which prospect cards are in it, and what would each
one sell for on its own?

We can't see the photos, so we trust the seller's words:
  1. If the description lists the cards (2+ lines that name a prospect, like a
     checklist), each of those lines is one card.
  2. Otherwise we read the title, plus any extra players eBay's "Player/Athlete"
     item specific names.
  3. "Number of Cards" (or "lot of 18" in the title) tells us how many cards there
     are. If the lot names just ONE card, we assume that many copies of it
     (e.g. "Eli Willits 1st Bowman Lot of (18)"). Otherwise extra cards the seller
     didn't name count as $0.
"""
import re
import statistics
from dataclasses import replace

from parse import norm


def card_count(title, details):
    """How many cards are in the lot, or None if we can't tell."""
    if details and details.get("count"):
        return details["count"]
    t = norm(title)
    for pattern in (r"\blot of (\d{1,4})\b", r"\blot (\d{1,4})\b",   # "Lot (25)" reads as "lot 25"
                    r"\b(\d{1,4})\s?-?\s?(?:card|cards|ct)\b",
                    r"\b(\d{1,4})\s?x\b|\bx\s?(\d{1,4})\b"):
        for m in re.finditer(pattern, t):
            n = int(next(g for g in m.groups() if g))
            if not 1900 <= n <= 2099:        # "1993 card lot" is a year, not 1,993 cards
                return n
    return None


def _cards_from(text, parser):
    """Cards named in one line of text: one card per prospect it names."""
    c = parser.parse(text)
    if not c:
        return []
    return [replace(c, player=p, is_lot=False) for p in c.players_in_title]


def cards_in_lot(title, details, parser):
    """Returns (list of Card, how many unnamed extra cards, where the cards came from)."""
    details = details or {}
    desc = [cards for line in details.get("lines", []) if (cards := _cards_from(line, parser))]
    if len(desc) >= 2:                       # the description is a checklist: trust it
        cards = [c for line_cards in desc for c in line_cards]
        source = "description"
    else:
        cards = _cards_from(title, parser)
        source = "title"
    if not cards:
        return [], 0, source

    # Players eBay's item specifics name that we haven't found yet: one plain card each,
    # with the year/product the title gives.
    named = {c.player for c in cards}
    for name in details.get("players", []):
        for p in parser.players_in(norm(name)):
            if p not in named:
                cards.append(replace(cards[0], player=p, auto=False, first=False,
                                     parallel="base", serial="", grade="raw"))
                named.add(p)

    count, unnamed = card_count(title, details), 0
    if count and count > len(cards):
        if len({c.key for c in cards}) == 1:
            cards = cards * count            # "lot of 18" of one card -> 18 copies
        else:
            unnamed = count - len(cards)     # cards the seller didn't name: count as $0
    return cards, unnamed, source


def low_ask(prices):
    """The low end (25th percentile) of asking prices. A buyer can always pick the
    cheap copies, so this is closer to what a single really resells for than the
    middle of the asks, and one or two overpriced listings can't drag it up."""
    return statistics.quantiles(prices, n=4, method="inclusive")[0]


def single_value(card, store, cfg):
    """What this one card would resell for on its own, and where that number comes
    from. Best evidence first; not enough evidence -> $0 (stay conservative)."""
    d, L, days = cfg["deal"], cfg["lots"], cfg["recommend"]["ask_days"]
    sold, n = store.comp_stats(card, d["comp_days"])
    if sold is not None and n >= d["min_comps"]:       # same rule as deals: 3+ sales
        return sold, f"{n} sold"
    if card.product != "?":
        prices = store.ask_prices(card, days)
        if len(prices) >= L["min_asks"]:
            return low_ask(prices), f"low ask of {len(prices)}"
    prices = store.player_floor_prices(card.player, days)
    if len(prices) >= L["min_asks"]:
        return low_ask(prices), f"low ask, player's base cards ({len(prices)})"
    return 0.0, "not enough data"


def value_rows(cards, store, cfg):
    """Value each distinct card once, then count copies. Only the first few copies
    count: nobody buys 100 of the same common, so extra copies are worth ~$0.
    Returns (rows, total singles value)."""
    rows = {}
    for c in cards:
        if c.key not in rows:
            value, src = single_value(c, store, cfg)
            rows[c.key] = {"card": c, "qty": 0, "value": value, "source": src}
        rows[c.key]["qty"] += 1
    for r in rows.values():
        r["valued"] = min(r["qty"], cfg["lots"]["max_copies_valued"])
    rows = sorted(rows.values(), key=lambda r: -r["value"])
    return rows, sum(r["value"] * r["valued"] for r in rows)


FIRST = r"\b(1st|first)\b(?! edition)"      # "Bowman 1st Edition" is a product, not a 1st
ROOKIE = r"\b(rc|rcs|rookie|rookies)\b"


def bulk_lot(it, card, store, cfg, parser, ranks):
    """A cheap bulk lot: about $1 or less per card, at least one of your prospects
    named, and 1st or RC cards mentioned. The other cards can be any players.
    Page only (no alerts). Returns a dict, or None."""
    B = cfg["lots"]["bulk"]
    if not B["enabled"]:
        return None
    details = store.get_lot_details(it["item_id"]) or {}
    count = card_count(it["title"], details)
    if not count or count < B["min_cards"]:
        return None                       # can't work out a price per card
    total = it["price"] + it["shipping"]
    per_card = total / count
    if per_card > B["max_price_per_card"]:
        return None

    cards, unnamed, source = cards_in_lot(it["title"], details, parser)
    if not cards:
        return None
    text = norm(it["title"] + " " + " ".join(details.get("lines", [])))
    has_first = any(c.first for c in cards) or bool(re.search(FIRST, text))
    has_rc = any(c.rookie for c in cards) or bool(re.search(ROOKIE, text))
    if not (has_first or has_rc):
        return None

    # Rank: 1sts matter most, then RCs; each named prospect adds points by rank
    # (#1 = 50 ... #50 = 1); cheaper per card breaks ties.
    players = sorted({c.player for c in cards}, key=lambda p: ranks.get(p, 50))
    score = (30 if has_first else 0) + (15 if has_rc else 0) \
        + sum(51 - ranks.get(p, 50) for p in players)
    rows, singles = value_rows(cards, store, cfg)
    tags = (["1st"] if has_first else []) + (["RC"] if has_rc else [])
    return {"kind": "lot", "bulk": True, "alert": False,
            "headline": f"LOT: {count} cards at ${per_card:.2f} each ({' + '.join(tags)})",
            "count": count, "per_card": per_card, "tags": tags, "score": round(score),
            "players": [f"#{ranks.get(p, '?')} {p.title()}" for p in players],
            "rows": rows, "unnamed": max(0, count - sum(r["qty"] for r in rows)),
            "source": source, "looked_up": bool(details),
            "singles": singles, "total": total, "profit": None, "discount": None,
            "median": None, "comps": 0}


def evaluate_lot(it, card, store, cfg, parser):
    """Return a dict describing the lot if it's priced well under the sum of its
    singles, else None. "alert" says whether it also clears the profit rule."""
    d, L = cfg["deal"], cfg["lots"]
    cards, unnamed, source = cards_in_lot(it["title"], store.get_lot_details(it["item_id"]), parser)
    if not cards:
        return None

    rows, singles = value_rows(cards, store, cfg)
    total = it["price"] + it["shipping"]
    if singles <= 0:
        return None
    discount = 1 - total / singles
    if discount < d["min_discount"]:
        return None

    # Resale profit: cards worth less than min_single_value can't be sold one at a
    # time for a profit (fees + shipping eat it all), so they count $0 here.
    net = sum((r["value"] * (1 - d["ebay_fee_rate"]) - L["ship_per_card"]) * r["valued"]
              for r in rows if r["value"] >= L["min_single_value"])
    profit = net - total
    return {"kind": "lot",
            "headline": f"LOT: {discount:.0%} under singles value (${total:.2f} vs ${singles:.2f})",
            "rows": rows, "unnamed": unnamed, "source": source,
            "looked_up": store.get_lot_details(it["item_id"]) is not None,
            "singles": singles, "total": total, "profit": profit, "discount": discount,
            "median": None, "comps": 0, "alert": profit >= d["min_profit"]}
