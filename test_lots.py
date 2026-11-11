"""Tests for reading lots card by card (lots.py). Run: python test_lots.py"""
from lots import card_count, cards_in_lot
from parse import Parser

P = Parser([{"name": "Jesus Made"}, {"name": "Eli Willits"}, {"name": "Leo De Vries"},
            {"name": "Kade Anderson"}], ["reprint"])


def test_same_card_lot_is_copies():
    # The real lot from the sample API call: 18 copies of one card
    title = "2025 Bowman Draft - Eli Willits 1st Bowman Lot of (18) #BD-1 Nationals Prospect"
    details = {"count": 18, "players": ["Eli Willits"],
               "lines": ["The product is a lot of 18 2025 Bowman Draft baseball trading cards "
                         "featuring Eli Willits, a prospect for the Washington Nationals."]}
    cards, unnamed, source = cards_in_lot(title, details, P)
    assert source == "title" and len(cards) == 18 and unnamed == 0
    assert cards[0].key == "eli willits|2025|bowman draft|base|1st|base||raw"


def test_description_checklist_wins():
    details = {"count": 5, "players": [],
               "lines": ["Includes:", "2025 Bowman Chrome Jesus Made 1st Refractor",
                         "Eli Willits 2025 Bowman Draft Chrome 1st", "plus 3 commons"]}
    cards, unnamed, source = cards_in_lot("Bowman prospect lot (5)", details, P)
    assert source == "description" and unnamed == 3
    assert [c.player for c in cards] == ["jesus made", "eli willits"]
    assert cards[0].parallel == "refractor" and cards[1].product == "bowman chrome draft"


def test_item_specifics_add_players():
    details = {"count": None, "players": ["Jesus Made", "Kade Anderson"], "lines": []}
    cards, _, _ = cards_in_lot("2025 Bowman Jesus Made prospect lot", details, P)
    assert sorted(c.player for c in cards) == ["jesus made", "kade anderson"]


def test_card_count_from_title():
    assert card_count("Leo De Vries 3-Card Lot 2026 Bowman Chrome", None) == 3
    assert card_count("Jesus Made Lot of (12) Bowman", None) == 12
    assert card_count("Jesus Made Bowman lot", None) is None
    assert card_count("1993 Leaf Card Lot (2)", None) == 2             # 2 cards, not 1,993
    assert card_count("Lot (25) Jesus Made 2025 Bowman", None) == 25
    assert card_count("X100 2026 Bowman Luis Pena Card Lot", None) == 100


def test_frank_thomas_is_not_thomas_white():
    p = Parser([{"name": "Thomas White"}], [])
    assert p.parse("Leaf Frank Thomas White Sox 1993 Card Lot") is None
    assert p.parse("2025 Bowman Chrome Thomas White 1st Marlins").player == "thomas white"


def test_bulk_lot_rule():
    import os, tempfile, yaml
    from lots import bulk_lot
    from store import Store
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    s = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
    ranks = {"jesus made": 1, "eli willits": 4}

    def lot(title, price, ship=0.0, item_id="x"):
        it = {"item_id": item_id, "title": title, "buying": "BIN", "price": price,
              "shipping": ship, "shipping_known": True}
        return bulk_lot(it, P.parse(title), s, cfg, P, ranks)

    a = lot("2025 Bowman 1st Bowman Lot (25) Jesus Made Eli Willits + Base", 18.0, 4.0)
    assert a and a["count"] == 25 and round(a["per_card"], 2) == 0.88 and a["tags"] == ["1st"]
    assert a["unnamed"] == 23          # 25 cards; the title names 2 (Made and Willits)
    # too expensive per card ($2 each)
    assert lot("2025 Bowman 1st Bowman Lot (10) Jesus Made", 20.0) is None
    # cheap, but no 1st or RC mentioned
    assert lot("2025 Bowman Lot (30) Jesus Made base cards", 15.0) is None
    # RC only is fine
    assert lot("Eli Willits RC lot of 40 rookies 2026", 30.0)["tags"] == ["RC"]
    # card count unknown -> can't price per card
    assert lot("Jesus Made 1st Bowman lot", 3.0) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
