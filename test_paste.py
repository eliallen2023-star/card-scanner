"""Tests for paste mode (paste.py). Run: python test_paste.py"""
from paste import find_price, read_cards
from parse import Parser

P = Parser([{"name": "Jesus Made"}, {"name": "Eli Willits"}, {"name": "Leo De Vries"}], [])


def test_prices():
    assert find_price("Made 1st auto /499 $80 shipped")[0] == 80        # not 499
    assert find_price("Willits BDC 1st 25 + ship")[0] == 25
    assert find_price("De Vries 1st 40$")[0] == 40
    assert find_price("Made 1st 35 obo")[0] == 35
    assert find_price("Made 1st #BD-12 /50")[0] is None                 # no price at all


def test_post():
    post = """Prices below!
2025 Bowman Chrome Jesus Made 1st Auto /499 $80 shipped
Eli Willits BDC 1st refractor 25 + ship
2025 Bowman Leo De Vries 1st Gold /50
$40 shipped
Made + Willits lot $20
DM me"""
    cards, notes = read_cards(post, P, "2025", 5.0)
    assert [c["card"].player for c in cards] == ["jesus made", "eli willits", "leo de vries"]
    made, willits, devries = cards
    assert made["price"] == 80 and made["ship"] == 0                   # "shipped"
    assert made["card"].auto and made["card"].serial == "/499"
    assert willits["ship"] == 5 and willits["card"].product == "bowman chrome draft"
    assert devries["price"] == 40 and devries["card"].parallel == "gold"   # price on next line


def test_all_shipped_and_chrome_shorthand():
    cards, _ = read_cards("All prices shipped\nJesus Made 1st chrome $6", P, None, 5.0)
    assert cards[0]["ship"] == 0 and cards[0]["card"].product == "bowman chrome"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
