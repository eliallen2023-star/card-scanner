from parse import Parser

P = Parser([{"name": "Jesús Made"}, {"name": "Leo De Vries", "aliases": ["Leo DeVries"]},
            {"name": "Eli Willits"}, {"name": "Franklin Arias"}],
           ["reprint", "custom", "you pick"])


def test_full_card():
    c = P.parse("2025 Bowman Chrome Jesús Made 1st Auto Gold Refractor /50 PSA 10")
    assert c.key == "jesus made|2025|bowman chrome|auto|1st|gold refractor|/50|PSA 10"


def test_alias_and_raw():
    c = P.parse("Leo DeVries 2024 Bowman Draft Chrome 1st Refractor")
    assert c.player == "leo de vries" and c.grade == "raw" and c.parallel == "refractor"
    assert c.product == "bowman chrome draft" and c.first   # "Draft Chrome" is chrome
    assert P.parse("2025 Bowman Draft Eli Willits 1st Bowman #BD-1").product == "bowman draft"
    assert P.parse("2025 Bowman Draft Eli Willits 1st #BDC-1").product == "bowman chrome draft"


def test_serial_formats():
    assert P.parse("Eli Willits 2025 Bowman Chrome Orange 12/25").serial == "/25"
    assert P.parse("Eli Willits Superfractor 1/1").serial == "/1"


def test_lot_and_excludes():
    assert P.parse("Jesus Made Eli Willits prospect lot").is_lot
    assert P.parse("Jesus Made reprint") is None
    assert P.parse("Mike Trout 2011 Topps") is None


def test_team_name_is_not_a_color():
    c = P.parse("2025 Bowman Chrome Franklin Arias Red Sox Refractor")
    assert c.parallel == "refractor"


def test_non_auto():
    assert not P.parse("Eli Willits 2025 Bowman Chrome 1st Non-Auto PSA 10").auto
    assert P.parse("Eli Willits 2025 Bowman Chrome 1st Auto").auto


def test_curly_apostrophe():
    assert P.parse("2025 Bowman’s Best Eli Willits Refractor").product == "bowman's best"


def test_hand_signed_excluded():
    import yaml
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    real = Parser([{"name": "Josiah Hartshorn"}], cfg["exclude_words"])
    assert real.parse("Signed On Card JOSIAH HARTSHORN CUBS RC 1st card 2025 BOWMAN DRAFT #BD-21") is None
    assert real.parse("Josiah Hartshorn TTM signed 2025 Bowman") is None
    assert real.parse("Josiah Hartshorn IP Auto 2025 Bowman Draft") is None
    # a real certified auto that says "on card" is kept
    assert real.parse("2025 Bowman Draft Chrome Josiah Hartshorn 1st On Card Auto CDA-JH").auto


def test_rookie():
    assert P.parse("2026 Topps Chrome Eli Willits RC Refractor").rookie
    assert P.parse("Eli Willits 2026 Bowman Rookie Card").rookie
    assert not P.parse("2025 Bowman Chrome Eli Willits 1st").rookie


def test_not_first():
    assert not P.parse("2026 Bowman Chrome Jesus Made Prospect Auto").first
    assert not P.parse("2023 Bowman 1st Edition Eli Willits Sky Blue Foil").first


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
