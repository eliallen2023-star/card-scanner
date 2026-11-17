"""Tests for ratings and learning (feedback.py, notify.py). Run: python test_feedback.py"""
import feedback
import notify


def rated(label, text, players=(), search="1st bowman lot"):
    return {"label": label, "search": search,
            "tokens": sorted(feedback.tokens(text, list(players)))}


def test_tokens():
    t = feedback.tokens("2025 Bowman Chrome Mojo 1st Bowman lot PSA 10 /99 Red Sox", ["jesus made"])
    assert ("player", "jesus made") in t and ("year", "2025") in t
    assert ("product", "bowman chrome") in t
    for f in ("mojo", "1st bowman", "psa 10", "numbered"):
        assert ("feature", f) in t
    assert ("feature", "red") not in t                   # "Red Sox" is a team, not a parallel


def test_learn_builds_searches():
    rows = [rated("good", "2025 Bowman Chrome Mojo lot", ["sebastian walcott"]),
            rated("good", "2025 Bowman Chrome Mojo refractor lot", ["sebastian walcott", "max clark"]),
            rated("medium", "Max Clark 2025 Bowman Chrome lot", ["max clark"]),
            rated("bad", "baseball card collection binder", search="binder search"),
            rated("bad", "baseball card collection binder box", search="binder search")]
    L = feedback.learn(rows, existing_queries=["2025 bowman chrome lot"], max_searches=4)
    liked = [t for t, _ in L["liked"]]
    assert "Sebastian Walcott" in liked and "Max Clark" in liked and "mojo" in liked
    assert "lot (Sebastian Walcott, Max Clark)" in L["queries"] or \
        "lot (Max Clark, Sebastian Walcott)" in L["queries"]
    assert "2025 bowman chrome mojo lot" in L["queries"]
    assert "2025 bowman chrome lot" not in L["queries"]       # you already search for it
    assert len(L["queries"]) <= 4 and L["rated"] == 5


def test_one_good_lot_is_not_enough():
    L = feedback.learn([rated("good", "2025 Bowman Chrome Mojo lot", ["max clark"])], [], 4)
    assert L["queries"] == []                               # needs 2+ lots to agree


def test_search_ratings():
    rows = [rated("bad", "x", search="a"), rated("bad", "y", search="a"), rated("good", "z", search="b")]
    by = feedback.search_ratings(rows)
    assert by["a"]["bad"] == 2 and by["b"]["good"] == 1


def test_alert_buttons():
    a = notify.rating_buttons("topic123", "v1|555|0")
    assert a.count("http, ") == 3 and "body='good v1|555|0'" in a and "body='bad v1|555|0'" in a


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
