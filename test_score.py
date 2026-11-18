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
    assert a > b + 12                      # #1 = 30 points, #50 = 15


def test_price_per_card_points():
    it, info = lot("1st Bowman lot of 50", price=20, ship=5)      # $0.50 a card
    s, reasons = score.score_lot(it, info, RANKS)
    assert info["per_card"] == 0.5 and "$0.50/card +20" in reasons


def test_first_bowman_counted_once():
    _, reasons = score.score_lot(*lot("2025 Bowman 1st Bowman Chrome lot of 5"), RANKS)
    assert "1st Bowman +20" in reasons and not any(r.startswith("1st +") for r in reasons)
    _, reasons = score.score_lot(*lot("Topps Chrome 1st Ed. Rookie lot of 7"), RANKS)
    assert not any(r.startswith("1st") for r in reasons)


def test_stale_listing_loses_points():
    from datetime import timedelta
    it, info = lot("Jesus Made 1st Bowman lot of 10")
    it["listed"] = iso(now() - timedelta(days=2))
    fresh = score.score_lot(it, info, RANKS)[0]
    it["listed"] = iso(now() - timedelta(days=12))
    stale, reasons = score.score_lot(it, info, RANKS)
    assert stale == fresh - 10 and any("12 days ago" in r for r in reasons)


def test_same_card_bulk():
    for title in ("x100 Jesus Made 2025 Bowman 1st", "Jesus Made lot of 50 same card",
                  "Jesus Made 1st Bowman Lot of (18) #BD-1"):
        it, info = lot(title, price=20, ship=0)
        assert info["same_card"], title
        _, reasons = score.score_lot(it, info, RANKS)
        assert any(r.startswith("same-card bulk") for r in reasons)
    # a mixed lot (two prospects) and a small one are not same-card bulk
    assert not lot("Jesus Made Eli Willits 1st Bowman lot of 50")[1]["same_card"]
    assert not lot("Jesus Made 1st Bowman x3")[1]["same_card"]
    # same price per card: the mixed lot ranks higher
    mixed = score.score_lot(*lot("Jesus Made 1st Bowman prospect lot of 50", price=25, ship=0), RANKS)[0]
    same = score.score_lot(*lot("x50 Jesus Made 1st Bowman", price=25, ship=0), RANKS)[0]
    assert mixed > same


def test_new_seller_and_late_night():
    from datetime import datetime, timezone
    it, info = lot("Jesus Made 1st Bowman lot of 10")
    base = score.score_lot(it, info, RANKS)[0]
    it["seller_feedback"] = 12
    assert score.score_lot(it, info, RANKS)[0] == base + 5
    # an auction ending 3 AM Eastern (8 AM UTC in November) with 1 bid
    a, ainfo = lot("Jesus Made 1st Bowman lot of 10", buying="AUCTION")
    a["end_time"], a["bid_count"] = "2026-11-20T08:00:00Z", 1
    assert score.late_night(a)
    a["bid_count"] = 5                                     # lots of bids: no bonus
    assert not score.late_night(a)
    a["end_time"], a["bid_count"] = "2026-11-20T20:00:00Z", 0   # 3 PM Eastern
    assert not score.late_night(a)


def test_manual_sold_prices_and_sell_through():
    import os, tempfile
    import manual
    path = os.path.join(tempfile.mkdtemp(), "comps.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("title,total_price,sold_date,sell_through\n"
                "Jesus Made 2025 Bowman 1st,20,2026-11-01,75\n"
                "Jesus Made 2025 Bowman 1st,30,2026-11-02,\n")
    p = Parser([{"rank": 1, "name": "Jesus Made"}], [])
    market = manual.load(p, path)
    assert market["jesus made"]["median"] == 25 and market["jesus made"]["sell_through"] == 75
    it, info = lot("Jesus Made 1st Bowman lot of 10", price=10, ship=5)   # $15 for ~$25 of cards
    base = score.score_lot(it, info, RANKS)[0]
    s, reasons = score.score_lot(it, info, RANKS, market=market)
    assert s == base + 10 + 2, reasons                    # 1.5x covered +10, 75% sell-through +2


def test_riser_boost_and_tag():
    p = Parser([{"rank": 1, "name": "Jesus Made"}, {"rank": 0, "name": "Rainiel Rodriguez"}], [])
    it = {"title": "Rainiel Rodriguez 1st Bowman lot of 10", "buying": "BIN", "price": 10.0,
          "shipping": 0.0, "listed": iso(now())}
    info = score.read_lot(it, None, p)
    s, reasons = score.score_lot(it, info, RANKS, risers={"rainiel rodriguez": "hot"})
    assert any(r.startswith("riser Rainiel") for r in reasons)
    assert not any(r.startswith("#") for r in reasons)     # no rank points for a non-prospect
    assert "Riser" in score.tags(it, info, reasons)
    out = all_searches({"risers": [{"name": "Rainiel Rodriguez"}]}, [], CFG)
    assert ("risers", "lot Rainiel Rodriguez") in out


def test_january_banner():
    from datetime import date
    import webpage
    assert webpage.january_banner(date(2027, 1, 15))
    assert not webpage.january_banner(date(2026, 11, 17))


def test_other_sports():
    # football / basketball in the title, no prospect: skipped before any detail lookup
    for title in ("2026 Bowman Chrome Football 1st Bowman lot of 29",
                  "Topps 2024 Bowman U Chrome 1st Bowman RC lot (15)",
                  "Lakers Celtics rookie lot 50 cards"):
        it, info = lot(title)
        assert score.skip_reason(it, info, CFG, [])
    # baseball words win, and baseball-only team names (Bulls, Giants) are fine
    for title in ("Bowman 1st lot 20 cards baseball football mixed", "Durham Bulls 1st Bowman lot of 10",
                  "Giants prospect 1st Bowman lot of 10"):
        it, info = lot(title)
        assert not score.skip_reason(it, info, CFG, []), title
    # names a prospect: kept but marked down
    it, info = lot("Jesus Made 1st Bowman + NFL rookie lot of 10")
    s, reasons = score.score_lot(it, info, RANKS)
    assert any(r.startswith("other-sport word") for r in reasons)


def test_prospect_first_bowman_bonus():
    a, ainfo = lot("Jesus Made 1st Bowman lot of 10")
    _, reasons = score.score_lot(a, ainfo, RANKS)
    assert "prospect + 1st Bowman +10" in reasons
    b, binfo = lot("Prospect 1st Bowman lot of 10")          # no prospect from the list
    assert "prospect + 1st Bowman +10" not in score.score_lot(b, binfo, RANKS)[1]


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


def test_name_typos():
    p = Parser([{"rank": 4, "name": "Eli Willits", "typos": ["Eli Willets"]}], [])
    assert p.players_in("eli willets 1st bowman lot") == ["eli willits"]   # scored as Willits
    out = all_searches({"player_searches": True},
                       [{"rank": 4, "name": "Eli Willits", "typos": ["Eli Willets", "Eli Willitts"]}], CFG)
    assert ("typos", "lot (Eli Willets, Eli Willitts)") in out


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
