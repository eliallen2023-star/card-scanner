"""Turn messy eBay titles into a 'card key' so we can compare like with like.

Example:
  "2025 Bowman Chrome Jesus Made 1st Auto Gold Refractor /50 PSA 10"
  -> jesus made|2025|bowman chrome|auto|1st|gold refractor|/50|PSA 10
"""
import re
import unicodedata
from dataclasses import dataclass

PRODUCTS = [  # most specific first
    "bowman chrome draft", "bowman draft", "bowman sterling", "bowman's best",
    "bowmans best", "bowman platinum", "bowman inception", "bowman chrome",
    "topps pro debut", "topps chrome", "topps heritage minors", "bowman",
]
COLORS = ["superfractor", "gold", "orange", "red", "purple", "blue", "green",
          "aqua", "black", "yellow", "pink", "sapphire", "atomic", "speckle",
          "mojo", "shimmer", "wave", "lava", "raywave", "x-fractor", "xfractor"]

# Team names that contain a color word. We blank these out before looking for
# parallel colors, so "Red Sox" isn't mistaken for a Red parallel.
TEAM_COLOR_WORDS = ["red sox", "white sox", "blue jays"]


def norm(text: str) -> str:
    """lowercase, strip accents (Jesús -> jesus), collapse spaces."""
    # Curly apostrophes (Bowman’s) -> straight ones (Bowman's)
    text = text.replace("’", "'").replace("‘", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9/#.' -]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Card:
    player: str
    year: str
    product: str
    auto: bool
    first: bool          # title says "1st" / "first" (1st Bowman cards are worth more)
    parallel: str
    serial: str
    grade: str
    is_lot: bool
    players_in_title: list
    # Title says "RC"/"rookie". Not part of the card key: sellers often call prospect
    # cards "RC" when they aren't official rookie cards, so it's used only for ranking.
    rookie: bool = False

    @property
    def key(self) -> str:
        return "|".join([self.player, self.year, self.product,
                         "auto" if self.auto else "base",
                         "1st" if self.first else "-",
                         self.parallel, self.serial, self.grade])

    @property
    def key_noyear(self) -> str:
        # Still saved in the database, but no longer used to pick comps: ignoring the
        # year mixed up 1st Bowman cards with later (cheaper) cards of the same player.
        return "|".join([self.player, self.product,
                         "auto" if self.auto else "base",
                         "1st" if self.first else "-",
                         self.parallel, self.serial, self.grade])


class Parser:
    def __init__(self, prospects, exclude_words):
        # name variants -> canonical name
        self.names = {}
        for p in prospects:
            canon = norm(p["name"])
            self.names[canon] = canon
            for a in p.get("aliases", []) or []:
                self.names[norm(a)] = canon
        self.exclude = [norm(w) if w.strip() == w else w.lower() for w in exclude_words]

    def players_in(self, t: str) -> list:
        # Blank out team names first, so "Frank Thomas White Sox" isn't read as
        # the prospect "Thomas White".
        for team in TEAM_COLOR_WORDS:
            t = t.replace(team, " ")
        found = []
        for variant, canon in self.names.items():
            if re.search(rf"\b{re.escape(variant)}\b", t) and canon not in found:
                found.append(canon)
        return found

    def parse(self, title: str):
        t = norm(title)
        padded = f" {t} "
        if any(w in padded for w in self.exclude):
            return None
        players = self.players_in(t)
        if not players:
            return None

        is_lot = bool(re.search(r"\blots?\b|\b\d+\s*(card|cards|ct)\b|\bbundle\b", t)) \
            or len(players) > 1

        year = (re.search(r"\b(20[12]\d)\b", t) or [None, "?"])[1]
        product = next((p for p in PRODUCTS if p in t), "?")
        product = product.replace("bowmans best", "bowman's best")
        # "Bowman Draft Chrome" (BDC- cards) is the chrome product, worth more than
        # paper "Bowman Draft" (BD- cards). Keep them apart so prices don't mix.
        if product == "bowman draft" and ("chrome" in t or re.search(r"\bbdc-", t)):
            product = "bowman chrome draft"

        # "auto", but not "non-auto" / "no auto"
        auto = bool(re.search(r"\b(auto|autos|autograph|autographed|signed|au)\b", t)) \
            and not re.search(r"\b(non|no)[ -]?auto", t)
        # "1st" / "first", but not "Bowman 1st Edition" (a product name, not a 1st card)
        first = bool(re.search(r"\b(1st|first)\b(?! edition)", t))

        color_text = t
        for team in TEAM_COLOR_WORDS:
            color_text = color_text.replace(team, " ")
        colors = [c for c in COLORS if re.search(rf"\b{c}\b", color_text)]
        refr = bool(re.search(r"refractor|\bref\b", t))
        parallel = " ".join(colors[:1] + (["refractor"] if refr else [])) or "base"

        # serial numbering: "/50", "#/50", "12/50", "1/1"
        m = re.search(r"(?:^|[\s#])(?:\d{1,4})?\s?/\s?(\d{1,4})\b", t)
        serial = "/" + m.group(1) if m else ""
        if "superfractor" in t:
            serial = "/1"

        g = re.search(r"\b(psa|bgs|sgc|cgc|tag)\s?(10|9\.5|9|8\.5|8|7)\b", t)
        grade = f"{g.group(1).upper()} {g.group(2)}" if g else "raw"

        rookie = bool(re.search(r"\b(rc|rookie|rookies)\b", t))

        return Card(players[0], year, product, auto, first, parallel, serial, grade,
                    is_lot, players, rookie)
