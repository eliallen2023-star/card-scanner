"""Fake eBay lots so you can see the lot spotter work without API keys (python main.py --demo)."""
from datetime import timedelta
from store import now, iso

LIVE = [  # (title, type, price, shipping (None = not in search results), bids,
          #  hours until an auction ends, minutes since it was listed)
    # 0: top prospects, 1sts, ~$0.88 a card, brand new -> high score
    ("2025 Bowman 1st Bowman Prospect Lot (25) Jesus Made Eli Willits Leo De Vries",
     "FIXED_PRICE", 18.00, 4.00, 0, None, 8),
    # 1: shipping and card count only known after the detail lookup
    ("Bowman Chrome Refractor Lot Prospects 1st Bowman", "FIXED_PRICE", 40.00, None, 0, None, 35),
    # 2: auction ending soon, no bids yet, an auto of the #2 prospect
    ("Leo De Vries 1st Bowman Chrome Auto /499 + Kade Anderson 1st Lot", "AUCTION",
     35.00, 5.00, 0, 0.7, 600),
    # 3: the item specifics say Football -> skipped
    ("Prospect Lot 1st Bowman 50 cards", "FIXED_PRICE", 20.00, 5.00, 0, None, 20),
    # 4: vague bulk listing, no prospects named, very cheap per card
    ("Baseball card collection binder 300 cards Bowman Topps", "FIXED_PRICE", 55.00, 10.00, 0, None, 50),
    # 5: $8+ a card -> skipped (over max_price_per_card)
    ("Jesus Made 1st Bowman Lot of (18) BD-1 Brewers", "FIXED_PRICE", 150.00, 4.00, 0, None, 120),
    # 6: one prospect, $2 a card
    ("Eli Willits 1st Bowman lot x5 2025 Bowman Draft", "FIXED_PRICE", 9.00, 1.00, 0, None, 300),
    # 7: misspelled title (found by the misspelling search), auction with bids
    ("Bowmen 1st prospect lot 20 cards Max Clark Walker Jenkins", "AUCTION", 12.00, 4.50, 3, 2.5, 900),
    # 8: reprints -> skipped
    ("2025 Bowman REPRINT lot custom Jesus Made", "FIXED_PRICE", 5.00, 1.00, 0, None, 10),
]

# Pretend ratings (index into LIVE), so the demo page shows what learning looks like:
# you liked the 1st Bowman lots with top prospects, and passed on the vague binder.
DEMO_RATINGS = [(0, "good"), (2, "good"), (1, "medium"), (4, "bad"), (6, "bad")]

# What item_details() would return (index into LIVE)
DETAILS = {
    0: {"shipping": 4.00, "players": ["Jesus Made", "Eli Willits", "Leo De Vries"], "count": 25,
        "sport": "Baseball", "features": "Rookie", "set": "2025 Bowman",
        "lines": ["25 card lot, you get everything pictured:",
                  "Jesus Made 2025 Bowman 1st Bowman BP-50",
                  "Eli Willits 2025 Bowman Draft 1st BD-1",
                  "Leo De Vries 2025 Bowman 1st",
                  "plus 22 base cards"]},
    1: {"shipping": 5.00, "players": ["Sebastian Walcott", "Walker Jenkins"], "count": 10,
        "sport": "Baseball", "features": "Refractor", "set": "Bowman Chrome", "lines": []},
    2: {"shipping": 5.00, "players": ["Leo De Vries", "Kade Anderson"], "count": 2,
        "sport": "Baseball", "features": "Autograph, Serial Numbered", "set": "Bowman Chrome",
        "lines": []},
    3: {"shipping": 5.00, "players": [], "count": 50, "sport": "Football", "features": None,
        "set": None, "lines": []},
}


def fake_search(q, category_id, buying, sort, limit, max_price, ends_within_hours=None):
    """Acts like Ebay.search: every demo lot shows up in the Lots category."""
    if category_id != "261329":
        return []
    out = []
    for i, (title, b, price, ship, bids, hrs, listed_min) in enumerate(LIVE):
        if b != buying:
            continue
        end = now() + timedelta(hours=hrs) if hrs else now() + timedelta(days=20)
        out.append({"item_id": f"v1|demo{i}|0", "title": title,
                    "buying": "AUCTION" if b == "AUCTION" else "BIN",
                    "price": price, "shipping": ship or 0.0, "shipping_known": ship is not None,
                    "bid_count": bids, "end_time": iso(end),
                    "listed": iso(now() - timedelta(minutes=listed_min)),
                    "url": f"https://www.ebay.com/itm/demo{i}", "image": ""})
    return out


def fake_details(item_id):
    """Acts like Ebay.item_details."""
    idx = int(item_id.split("|")[1].replace("demo", ""))
    return DETAILS.get(idx, {"shipping": None, "lines": [], "players": [], "count": None,
                             "sport": "Baseball", "features": None, "set": None})
