"""Fake eBay data so you can see the scanner work before you have API keys."""
from datetime import timedelta
from store import now, iso

SALES = [  # (title, total sold price, days ago)
    ("2025 Bowman Chrome Jesus Made 1st Auto Refractor /499", 120, 3),
    ("2025 Bowman Chrome Jesus Made 1st Auto Refractor #/499", 135, 6),
    ("Jesus Made 2025 Bowman Chrome 1st Bowman Auto Refractor 211/499", 128, 10),
    ("2025 Bowman Chrome Jesus Made 1st Auto Refractor /499 Brewers", 140, 15),
    ("2025 Bowman Chrome Eli Willits 1st Base Chrome PSA 10", 60, 4),
    ("Eli Willits 2025 Bowman Chrome 1st PSA 10 Nationals", 55, 8),
    ("2025 Bowman Chrome Eli Willits 1st Bowman PSA 10", 65, 12),
]

LIVE = [  # (title, type, price, shipping (None = not in search results), bids, hours until end)
    ("2025 Bowman Chrome Jesus Made 1st Auto Refractor /499 RC", "FIXED_PRICE", 74.99, 4.99, 0, None),
    ("Eli Willits 2025 Bowman Chrome 1st PSA 10 Gem Mint", "AUCTION", 22.00, 5.00, 4, 1.5),
    ("2025 Bowman Chrome Eli Willits 1st PSA 10", "AUCTION", 20.00, 5.00, 2, 20),  # ends too late
    ("Prospect lot Jesus Made Leo De Vries Eli Willits Kade Anderson 1st Bowman", "FIXED_PRICE", 15.00, 4.00, 0, None),
    ("2025 Bowman Jesus Made REPRINT custom card", "FIXED_PRICE", 2.00, 1.00, 0, None),
    # Shipping missing from search results; the lookup finds the real cost:
    ("2025 Bowman Chrome Eli Willits 1st PSA 10 Nationals", "FIXED_PRICE", 24.00, None, 0, None),
    ("Jesus Made 2025 Bowman Chrome 1st Auto Refractor /499 Brewers", "FIXED_PRICE", 70.00, None, 0, None),
    # No sales recorded for this card, but 4 other sellers are asking ~$95;
    # the $55 one shows up under "Recommended":
    ("2025 Bowman Chrome Franklin Arias 1st Auto Refractor /499", "FIXED_PRICE", 90.00, 4.00, 0, None),
    ("Franklin Arias 2025 Bowman Chrome 1st Auto Refractor 101/499 Red Sox", "FIXED_PRICE", 95.00, 4.00, 0, None),
    ("2025 Bowman Chrome Franklin Arias 1st Bowman Auto Refractor #/499", "FIXED_PRICE", 100.00, 4.00, 0, None),
    ("Franklin Arias 2025 Bowman Chrome 1st Auto Refractor /499 RC", "FIXED_PRICE", 85.00, 4.00, 0, None),
    ("2025 Bowman Chrome Franklin Arias 1st Auto Refractor /499 Rookie", "FIXED_PRICE", 55.00, 4.00, 0, None),
    # Cheap 1st Bowman card -> "Cheap 1st Bowman & rookie cards" section:
    ("2025 Bowman Draft Eli Willits 1st Bowman Paper #BD-1 Nationals", "FIXED_PRICE", 2.50, 1.00, 0, None),
    # #13: a lot of 10 copies of one cheap card (see LOT_DETAILS) -> under singles value,
    # but each card is worth < $6, so no resale profit: page only
    ("Eli Willits 1st Bowman Lot of (10) 2025 Bowman Draft Chrome #BDC-1", "FIXED_PRICE", 20.00, 4.00, 0, None),
    # #14-16: singles of that card, so the lot has something to compare with
    ("2025 Bowman Draft Chrome Eli Willits 1st #BDC-1", "FIXED_PRICE", 3.50, 1.00, 0, None),
    ("Eli Willits 2025 Bowman Draft Chrome 1st Bowman BDC-1", "FIXED_PRICE", 4.00, 1.00, 0, None),
    ("2025 Bowman Draft Chrome #BDC-1 Eli Willits 1st Nationals", "FIXED_PRICE", 4.50, 1.00, 0, None),
]

# What item_details() would return for the demo lots (index into LIVE).
LOT_DETAILS = {
    3: {"shipping": 4.00, "players": ["Jesus Made", "Leo De Vries", "Eli Willits", "Kade Anderson"],
        "count": 4,
        "lines": ["Prospect lot, 4 cards, shipped in toploaders:",
                  "2025 Bowman Chrome Eli Willits 1st PSA 10",
                  "2025 Bowman Chrome Jesus Made 1st Refractor",
                  "2024 Bowman Leo De Vries 1st",
                  "2025 Bowman Draft Kade Anderson 1st"]},
    13: {"shipping": 4.00, "players": ["Eli Willits"], "count": 10,
         "lines": ["Lot of 10 Eli Willits Bowman Draft cards, all the same card."]},
}
LOOKUP_SHIPPING = {5: 5.00,    # cheap shipping -> still a deal
                   6: 40.00}   # $40 shipping -> no longer a deal


def seed_comps(store, parser):
    for i, (title, price, days) in enumerate(SALES):
        c = parser.parse(title)
        store.db.execute("INSERT OR IGNORE INTO comps VALUES (?,?,?,?,?,?)",
                         (f"demo{i}", c.key, c.key_noyear, price,
                          iso(now() - timedelta(days=days)), "demo"))


def fake_search(q, category_id, buying, sort, limit, max_price, ends_within_hours=None):
    """Acts like Ebay.search. q looks like "(Jesus Made, Leo De Vries, ...)"."""
    inside = q[q.find("(") + 1:q.rfind(")")] if "(" in q else q
    names = [n.strip().lower() for n in inside.split(",")]
    out = []
    for i, (title, b, price, ship, bids, hrs) in enumerate(LIVE):
        if b != buying or not any(n in title.lower() for n in names):
            continue
        if ends_within_hours and hrs and hrs > ends_within_hours:
            continue   # the real search filters these out too
        end = now() + timedelta(hours=hrs) if hrs else now() + timedelta(days=20)
        out.append({"item_id": f"v1|demo{i}|0", "title": title,
                    "buying": "AUCTION" if b == "AUCTION" else "BIN",
                    "price": price, "shipping": ship or 0.0, "shipping_known": ship is not None,
                    "bid_count": bids,
                    "end_time": iso(end), "url": f"https://www.ebay.com/itm/demo{i}",
                    "image": ""})
    return out


def fake_details(item_id):
    """Acts like Ebay.item_details."""
    idx = int(item_id.split("|")[1].replace("demo", ""))
    return LOT_DETAILS.get(idx, {"shipping": None, "lines": [], "players": [], "count": None})


def fake_shipping(item_id):
    """Acts like Ebay.get_shipping. item_id looks like "v1|demo5|0"."""
    return LOOKUP_SHIPPING.get(int(item_id.split("|")[1].replace("demo", "")))
