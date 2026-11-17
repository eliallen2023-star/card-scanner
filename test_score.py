"""Tests for lot scoring (score.py) and the search list (main.py). Run: python test_score.py"""
import yaml

import score
from main import all_searches, pack
from parse import Parser
from store import iso, now

PROSPECTS = [{"rank": 1, "name": "Jesus Made", "team": "Brewers"},
             {"rank": 4, "name": "Eli Willits", "team": "Nationals"},
             {"rank": 50, "name": "Thomas White", "team": "Marlins"}]
P = Parser(PROSPECTS, ["reprint"])
RANKS = {"jesus made": 1, "eli willits": 4, "thomas white": 50}
CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def lot(title, price=20.0, ship=5.0, buying="BIN", details=None, listed_min=600):
    it = {"item_id": "x", "title": title, "buying": buying, "price": price, "shipping": ship,
          "shipping_known": True, "bid_count": 0, "end_time": iso(now()),
          "listed": iso(now()) if listed_min == 0 else None, "first_seen": "2000-01-01T00:00:00Z"}
    info = score.read_lot(it, details, P)
    return it, info


def test_top_prospects_score_higher():
    a = score.score_lot(*lot("Jesus Made 1st Bowman lot of 10"), RANKS)[0]
    b = score.score_lot(*lot("Thomas White 1st Bowman lot of 10"), RANKS)[0]
    assert a > b + 20


def test_price_per_card_points():
    it, info = lot("1st Bowman lot of 50", price=20, ship=5)      # $0.50 a card
    s, reasons = score.score_lot(it, info, RANKS)
    assert info["per_card"] == 0.5 and "$0.50/card +20" in reasons


def test_first_bowman_counted_once():
    _, reasons = score.score_lot(*lot("2025 Bowman 1st Bowman Chrome lot of 5"), RANKS)
    assert "1st Bowman +15" in reasons and not any(r.startswith("1st +") for r in reasons)
    _, reasons = score.score_lot(*lot("Topps Chrome 1st Ed. Rookie lot of 7"), RANKS)
    assert not any(r.startswith("1st") for r in reasons)


def test_skips():
    it, info = lot("Prospect lot 1st Bowman 50 cards", details={"sport": "Football", "count": 50})
    assert score.skip_reason(it, info, CFG, P.exclude).startswith("sport")
    it, info = lot("Jesus Made REPRINT lot of 10")
    assert score.skip_reason(it, info, CFG, P.exclude).startswith("excluded")
    it, info = lot("Bowman lot of 4 base", price=40)                # $11 a card, no prospects
    assert score.skip_reason(it, info, CFG, P.exclude) == "too much per card"
    it, info = lot("Jesus Made Auto /99 + Willits 1st lot of 2", price=60)   # pricey but prospects
    assert score.skip_reason(it, info, CFG, P.exclude) is None


def test_details_add_players_and_count():
    details = {"players": ["Eli Willits"], "count": 30, "sport": "Baseball", "lines": []}
    it, info = lot("Bowman prospect lot", details=details)
    assert info["players"] == ["eli willits"] and info["count"] == 30


def test_white_sox_is_not_thomas_white():
    _, info = lot("Frank Thomas White Sox lot of 20")
    assert info["players"] == []


def test_singles_category_lot_check():
    assert score.looks_like_lot("Jesus Made 1st Bowman lot")
    assert score.looks_like_lot("Willits 1st Bowman x5")
    assert not score.looks_like_lot("2025 Bowman Chrome Jesus Made 1st Auto /499")


def test_search_list():
    searches = {"every_scan": ["1st bowman lot"], "team_searches": True, "player_searches": True}
    out = all_searches(searches, PROSPECTS, CFG)
    assert ("every_scan", "1st bowman lot") in out
    assert ("teams", "(Brewers, Nationals, Marlins) bowman lot") in out
    assert ("players", "lot (Jesus Made, Eli Willits, Thomas White)") in out
    assert all(len(q) <= 100 for _, q in out)
    assert pack([["A"], ["B"], ["C"], ["D"], ["E"]], "", 4) == ["(A, B, C, D)", "E"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
