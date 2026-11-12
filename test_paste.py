"""Tests for paste mode (paste.py). Run: python test_paste.py"""
from paste import add_full_names, find_price, last_name_map, read_items
from parse import Parser

PROSPECTS = [{"name": "Jesus Made"}, {"name": "Eli Willits"},
             {"name": "Leo De Vries", "aliases": ["Leo DeVries"]}, {"name": "Thomas White"},
             {"name": "Seth Hernandez"}, {"name": "Luis Hernandez"}, {"name": "Eric Booth Jr"}]
P = Parser(PROSPECTS, [])
LAST = last_name_map(PROSPECTS)


def read(text, year="2025"):
    return read_items(text, P, LAST, year, 5.0)


def test_prices():
    assert find_price("Made 1st auto /499 $80 shipped")[0] == 80        # not 499
    assert find_price("Willits BDC 1st 25 + ship")[0] == 25
    assert find_price("De Vries 1st 40$")[0] == 40
    assert find_price("Made 1st 35 obo")[0] == 35
    assert find_price("Made 1st #BD-12 /50")[0] is None                 # no price at all


def test_last_names():
    assert "hernandez" not in LAST                  # two Hernandezes: can't tell them apart
    assert LAST["booth"] == "eric booth jr" and LAST["devries"] == "leo de vries"
    assert add_full_names("Made 1st auto /99", P, LAST)[0] == "jesus made 1st auto /99"
    assert add_full_names("De Vries 1st chrome", P, LAST)[0].startswith("leo de vries")
    assert add_full_names("made 1st auto", P, LAST)[1] == []      # everyday word, lowercase
    assert add_full_names("I made a trade today", P, LAST)[1] == []   # no card words
    assert add_full_names("Frank Thomas White Sox 1993 auto", P, LAST)[1] == []
    assert add_full_names("Jesus Made 1st", P, LAST)[1] == []     # full name already there


def test_post():
    post = """Prices below!
2025 Bowman Chrome Made 1st Auto /499 $80 shipped
Willits BDC 1st refractor 25 + ship
2025 Bowman Leo De Vries 1st Gold /50
$40 shipped
DM me"""
    items, _ = read(post)
    assert [i["card"].player for i in items] == ["jesus made", "eli willits", "leo de vries"]
    made, willits, devries = items
    assert made["price"] == 80 and made["ship"] == 0 and made["card"].auto
    assert willits["ship"] == 5 and willits["card"].product == "bowman chrome draft"
    assert devries["price"] == 40 and devries["card"].parallel == "gold"   # price on next line


def test_lots_in_a_page():
    page = """John Smith
2h
1st Bowman lot, 25 cards $20 shipped
Jesus Made 1st
Eli Willits 1st chrome
Like
Comment
Jane Doe
Made + Willits 1st lot
$15
Like
Junk lot of 50 Topps base $10
Marketplace
$30
2025 Bowman Chrome Made 1st Refractor"""
    items, _ = read(page)
    lot1, lot2, single = items
    assert lot1["kind"] == "lot" and lot1["price"] == 20 and len(lot1["checklist"]) == 2
    assert lot2["kind"] == "lot" and lot2["price"] == 15
    assert single["kind"] == "single" and single["price"] == 30    # price above the name
    assert len(items) == 3                         # the Topps lot names no prospect


def test_plus_ship_beats_all_shipped():
    items, _ = read("All prices shipped\nMade 1st chrome $6\nWillits 1st lot of 18 $12 + ship")
    assert items[0]["ship"] == 0 and items[1]["ship"] == 5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
