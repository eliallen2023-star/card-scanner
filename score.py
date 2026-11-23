"""Score a lot from 0 to 100: how worth a look is it?

Plain code on purpose (no AI): each part adds points, and every point is explained
on the web page so you can see WHY a lot scored what it did. Change the numbers
here if your experience says otherwise.

  Prospects named   up to 40   #1 prospect = 30, #25 = 23, #50 = 15, #100 = 0.3 (added up)
  Card types        up to 35   1st Bowman 20, auto 10, numbered 6, graded 4, refractor/color 4, ...
                               (1st Bowman only in the description, not the title: 8)
  Prospect 1st        +10      a prospect from your list AND a 1st Bowman in the title
  Bowman Chrome       +10      the title says Bowman Chrome (or BCP / BDC card numbers)
  Not Bowman          -10      the title doesn't say Bowman at all (mostly Topps / other sets)
  Team lot            -15      the title names one MLB team and it's 10+ cards (mostly base
                               cards of that team with a prospect or two mixed in)
  Other sets          -10      the title names another set (Pro Debut, Heritage, Mosaic,
                               Donruss, Stars of MLB...): a mixed pile, not a Bowman lot
  Price per card    up to 12   the sweet spot is $1-4 a card: $0.50 or less = 3 (very cheap
                               lots are mostly bulk that doesn't resell), $1 = 8, $2 = 12,
                               $4 = 10, $7 = 6, $12 = 3
  Fresh             up to  5   Buy It Now listed in the last hour, or an auction ending
                               within the hour with no bids
  Stale               -10      Buy It Now listed over 7 days ago (still unsold: likely overpriced)
  Same-card bulk      -20      many copies of one card (and stricter price-per-card points)
  New seller           +5      seller feedback under 50 (new sellers often underprice)
  Late-night auction   +5      ends 1-6 AM Eastern with 0-2 bids
  Your sold prices  +5 / +10   named cards' sold prices (manual_comps.csv) cover the price / 1.5x
  Sell-through      up to  3   a named player's sell_through over 50% (+1 per 10 points)
  Riser                +8      each player from risers.yaml
  Other sport         -15      football/basketball words, but a prospect is named (no prospect:
                               the lot is skipped)
"""
import re
from zoneinfo import ZoneInfo

import lots
import manual
from parse import norm, TEAM_COLOR_WORDS
from store import now, parse_time

# Words that mean "this is more than one card" (for listings in the Singles category).
LOT_WORDS = re.compile(r"\blots?\b|\bbundle\b|\bcollection\b|\b\d+\s*(card|cards|ct)\b|\bx\s?\d+\b")

COLORS = r"gold|orange|red|purple|blue|green|aqua|black|pink|sapphire|atomic|speckle|mojo|shimmer|wave|lava|superfractor"
FEATURES = [  # (name, points, pattern) - checked against the title + item specifics + description
    # "1st Edition" / "1st Ed." is a product name, not a first card
    ("1st Bowman", 20, r"\b1st\b(?! ?ed\b| ?edition).{0,20}\bbowman\b|\bbowman\b.{0,30}\b1st\b(?! ?ed\b| ?edition)"),
    ("1st", 8, r"\b(1st|first)\b(?! ?ed\b| ?edition)"),   # only counts if not already 1st Bowman
    ("Auto", 10, r"\b(auto|autos|autograph|autographs|autographed)\b"),
    ("Numbered", 6, r"(?<![\w$])/\s?\d{1,4}\b|#'?d\b|\bnumbered\b|\bserial\b"),
    ("Graded", 4, r"\b(psa|bgs|sgc|cgc)\s?\d"),
    ("Refractor/color", 4, r"\brefractors?\b|\bx-?fractor\b|\b(" + COLORS + r")\b"),
    ("Chrome", 3, r"\bchrome\b"),
    ("RC", 3, r"\b(rc|rcs|rookie|rookies)\b"),
]
# Same-card bulk: many copies of ONE card ("x100 Caleb Bonemer", "lot of 50 same card",
# "Lot of (18) ... #BD-1"). Harder to resell than a mixed lot, so it's scored on its own.
SAME_CARD = re.compile(r"\bsame (card|player)\b|\bidentical\b|\bcopies\b"
                       r"|\b\d{1,4}\s?x\b|\bx\s?\d{1,4}\b"       # 100x / x100
                       r"|#?\b[a-z]{1,4}-\d{1,4}\b"              # a card number: #BD-1, BDC-12
                       r"|\b(bcp|bdc|bd|bp)\d{1,4}\b")            # ... or without the dash: BCP115
SAME_CARD_MIN = 5
SAME_CARD_PENALTY = 20

MAX = {"prospects": 40, "cards": 35, "price": 12, "fresh": 5}
PROSPECT_1ST = 10                      # a prospect AND a 1st Bowman in the title: +10
FIRST_BOWMAN_DESC = 8                  # "1st Bowman" only in the description / item specifics

# What you said resells best: Bowman Chrome lots. Checked in the TITLE only (descriptions
# often say "Bowman" for one card in a pile of Topps).
BOWMAN_CHROME = re.compile(r"\bbowman\b.{0,25}\bchrome\b|\bchrome\b.{0,15}\bbowman\b"
                           r"|\b(bcp|bdc)\b|\b(bcp|bdc)-?\d")
ANY_BOWMAN = re.compile(r"\bbowman\b|\b(bcp|bdc|bd|bp)-?\d|\b(bcp|bdc)\b")
BOWMAN_CHROME_POINTS, NOT_BOWMAN_PENALTY = 10, 10

# Team lots ("Brewers 94 Card Lot ... Yelich"): mostly that team's base cards. Only when ONE
# team is named (two or more teams = a mixed prospect lot) and the lot has 10+ cards
# (a small team lot like "Guardians Bowman Chrome 1st Auto 3-Card Lot" is fine).
MLB_TEAMS = re.compile(
    r"\b(yankees|red sox|blue jays|orioles|rays|white sox|guardians|indians|tigers|royals|"
    r"twins|astros|angels|athletics|mariners|rangers|braves|marlins|mets|phillies|nationals|"
    r"cubs|reds|brewers|pirates|cardinals|diamondbacks|d-?backs|rockies|dodgers|giants|padres)\b")
TEAM_LOT_MIN, TEAM_LOT_PENALTY = 10, 15

# Other sets in the title ("Bowman Chrome/Mosaic", "Pro Debut Heritage"): a mixed pile, not
# a Bowman lot. (Topps Chrome and Finest aren't here: you rated lots with those Good.)
OTHER_SETS = re.compile(
    r"\b(pro debut|heritage|update|mosaic|donruss|optic|prizm|panini|stars of mlb|"
    r"stadium club|ginter|archives|big league|opening day|gypsy queen|series [12]|score)\b")
OTHER_SETS_PENALTY = 10
STALE_DAYS, STALE_PENALTY = 7, 10      # Buy It Now listed over 7 days ago: -10
NEW_SELLER = 50                        # seller feedback under this: +5 (often underprice)
RISER_POINTS = 8                       # each player from risers.yaml in the lot: +8


# Other sports in the title. Bowman also makes football and basketball cards ("Bowman U",
# "Bowman Chrome Football") that say "1st Bowman", so the broad searches find them.
# Team names: only ones no baseball team or card set shares (no Giants, Cardinals, Rangers,
# Bulls = Durham Bulls, Heat, Thunder, Bears, Lions...).
OTHER_SPORTS = re.compile(
    r"\b(football|basketball|hockey|soccer|nfl|nba|wnba|nhl|ncaa|ncaaf|ncaab|ufc|wwe|f1|"
    r"bowman u|bowman university|bowman chrome u|bowman u chrome|panini prizm draft picks|"
    r"qb|quarterback|wide receiver|running back|touchdown|"
    r"cowboys|chiefs|eagles|packers|steelers|patriots|49ers|bengals|ravens|dolphins|"
    r"broncos|raiders|chargers|seahawks|vikings|saints|falcons|buccaneers|commanders|"
    r"jaguars|lakers|celtics|warriors|knicks|bucks|mavericks|nuggets|clippers|76ers|sixers|"
    r"raptors|grizzlies|pelicans|timberwolves|cavaliers|pistons|pacers|trail blazers)\b")
OTHER_SPORT_PENALTY = 15     # a baseball prospect named, but other-sport words too: -15


def other_sport(title):
    """'football', 'Bowman U', 'Lakers'... in a title that doesn't also say baseball."""
    t = norm(title)
    m = OTHER_SPORTS.search(t)
    return m.group(0) if m and "baseball" not in t and " mlb " not in f" {t} " else None


def late_night(it, tz="America/New_York"):
    """An auction ending 1-6 AM Eastern with 0-2 bids: few people are awake to bid."""
    ends = parse_time(it.get("end_time"))
    if it["buying"] != "AUCTION" or not ends or (it.get("bid_count") or 0) > 2:
        return False
    return 1 <= ends.astimezone(ZoneInfo(tz)).hour < 6


def read_lot(it, details, parser):
    """Everything we can tell about a lot from its title, plus the item specifics
    and description if we've looked them up. Returns a dict."""
    details = details or {}
    extra = [details.get("features") or "", details.get("set") or ""]
    text = norm(" ".join([it["title"]] + list(details.get("lines", [])) + extra))
    # players: the title, eBay's Player/Athlete item specific, and the description
    named = norm(" ".join([it["title"]] + list(details.get("players", []))
                          + list(details.get("lines", []))))
    for team in TEAM_COLOR_WORDS:            # "White Sox" isn't the prospect Thomas White
        named = named.replace(team, " ")
    count = lots.card_count(it["title"], details)
    total = it["price"] + it["shipping"]
    players = parser.players_in(named)
    same_card = bool(count and count >= SAME_CARD_MIN and len(players) == 1
                     and SAME_CARD.search(norm(it["title"])))
    return {"players": players, "count": count, "total": total, "same_card": same_card,
            "per_card": total / count if count else None, "text": text,
            "sport": (details.get("sport") or "").strip().lower(),
            "looked_up": bool(details)}


def skip_reason(it, info, cfg, exclude_words):
    """Why this listing isn't worth showing at all, or None if it's fine."""
    S = cfg["spotter"]
    title = f" {norm(it['title'])} "
    for w in exclude_words:
        if w in title:
            return f"excluded word: {w.strip()}"
    if info["sport"] and "baseball" not in info["sport"]:
        return f"sport is {info['sport']}"            # football/basketball lots get through keywords
    # Other sports in the title: skipped, unless it also names one of your prospects
    # (then it's only marked down, in score_lot, because a team word can be a coincidence).
    word = other_sport(it["title"])
    if word and not info["players"]:
        return f"looks like another sport ({word})"
    if info["total"] > S["max_price"]:
        return "over the max price"
    # Pricey per card is fine for a small lot of good prospect cards (2 autos at $20 each);
    # without any of your prospects it's just an expensive lot.
    if info["per_card"] is not None and info["per_card"] > S["max_price_per_card"] \
            and not info["players"]:
        return "too much per card"
    if info["count"] == 1:
        return "a single card"
    return None


def looks_like_lot(title):
    return bool(LOT_WORDS.search(norm(title))) or (lots.card_count(title, None) or 0) > 1


TAG_FROM_REASON = {"1st Bowman": "1st", "1st": "1st", "Auto": "Auto",
                   "Refractor/color": "Refractor", "Numbered": "Numbered", "Graded": "Graded"}


def tags(it, info, reasons, tz="America/New_York"):
    """Short labels for the page: 1st, Auto, Refractor, Best Offer, Same-card bulk, ..."""
    out = []
    for r in reasons:
        name = r.rsplit(" ", 1)[0]               # "1st Bowman +15" -> "1st Bowman"
        if name in TAG_FROM_REASON:
            out.append(TAG_FROM_REASON[name])
    if info.get("same_card"):
        out.append("Same-card bulk")
    if it.get("best_offer"):
        out.append("Best Offer")
    if late_night(it, tz):
        out.append("Late-night ending")
    fb = it.get("seller_feedback")
    if fb is not None and fb < NEW_SELLER:
        out.append("New seller")
    if any(r.startswith("riser ") for r in reasons):
        out.append("Riser")
    return list(dict.fromkeys(out))              # no duplicates, same order


def score_lot(it, info, ranks, tz="America/New_York", market=None, risers=None):
    """Returns (score 0-100, list of reasons like "#1 Jesus Made +25").
    market = your sold prices (manual.load), risers = {player: note} from risers.yaml."""
    reasons, parts = [], {}

    # 1. Prospects: higher-ranked prospects are worth more points.
    pts = 0
    for p in sorted(info["players"], key=lambda p: ranks.get(p, 99)):
        if p not in ranks:
            continue                  # a riser who isn't on the prospect list: see part 6
        rank = ranks[p]
        add = (101 - rank) / 100 * 30         # #1 = 30, #50 = 15, #100 = 0.3
        pts += add
        reasons.append(f"#{rank} {p.title()} +{add:.0f}")
    parts["prospects"] = min(pts, MAX["prospects"])

    # 2. Card types mentioned anywhere (title, item specifics, description).
    pts, text, found = 0, info["text"], set()
    for name, add, pattern in FEATURES:
        if name == "1st" and "1st Bowman" in found:
            continue                                  # don't count the same 1st twice
        if re.search(pattern, text):
            found.add(name)
            pts += add
            reasons.append(f"{name} +{add}")
    # "1st Bowman" only in the description: maybe one card out of the whole lot.
    title = norm(it["title"])
    first_in_title = bool(re.search(FEATURES[0][2], title))
    if "1st Bowman" in found and not first_in_title:
        pts -= FEATURES[0][1] - FIRST_BOWMAN_DESC
        reasons[reasons.index(f"1st Bowman +{FEATURES[0][1]}")] = \
            f"1st Bowman (description only) +{FIRST_BOWMAN_DESC}"
    parts["cards"] = min(pts, MAX["cards"])
    # The cards worth the most: a 1st Bowman of a ranked prospect.
    if first_in_title and any(p in ranks for p in info["players"]):
        parts["cards"] += PROSPECT_1ST
        reasons.append(f"prospect + 1st Bowman +{PROSPECT_1ST}")
    # Bowman Chrome lots resell best; lots that don't say Bowman are mostly other sets.
    if BOWMAN_CHROME.search(title):
        parts["cards"] += BOWMAN_CHROME_POINTS
        reasons.append(f"Bowman Chrome lot +{BOWMAN_CHROME_POINTS}")
    elif not ANY_BOWMAN.search(title):
        parts["cards"] -= NOT_BOWMAN_PENALTY
        reasons.append(f"title doesn't say Bowman -{NOT_BOWMAN_PENALTY}")
    other_set = OTHER_SETS.search(title)
    if other_set:
        parts["cards"] -= OTHER_SETS_PENALTY
        reasons.append(f"mixed with other sets ({other_set.group(0)}) -{OTHER_SETS_PENALTY}")
    teams = set(m.group(0) for m in MLB_TEAMS.finditer(title))
    if len(teams) == 1 and (info["count"] or 0) >= TEAM_LOT_MIN:
        parts["cards"] -= TEAM_LOT_PENALTY
        reasons.append(f"team lot ({teams.pop().title()}) -{TEAM_LOT_PENALTY}")

    # 3. Price per card (price + shipping, divided by the number of cards).
    per = info["per_card"]
    if per is None:
        parts["price"] = 0
        reasons.append("card count unknown +0")
    elif info.get("same_card"):
        # Many copies of one card: only really cheap copies are worth it, and you'd still
        # have to sell them one by one.
        add = 15 if per <= 0.3 else 10 if per <= 0.6 else 6 if per <= 1 else 3 if per <= 2 else 0
        parts["price"] = add - SAME_CARD_PENALTY
        reasons.append(f"${per:.2f}/card +{add}")
        reasons.append(f"same-card bulk ({info['count']} copies) -{SAME_CARD_PENALTY}")
    else:
        # Not "cheaper is better": very cheap lots are mostly bulk base cards.
        add = 3 if per <= 0.5 else 8 if per <= 1 else 12 if per <= 2 else 10 if per <= 4 \
            else 6 if per <= 7 else 3 if per <= 12 else 0
        parts["price"] = add
        reasons.append(f"${per:.2f}/card +{add}")

    # 4. Fresh: be one of the first to see it. Stale: listed over a week ago and still
    #    unsold usually means it's overpriced.
    parts["fresh"] = 0
    if it["buying"] == "BIN":
        listed = parse_time(it.get("listed") or it.get("first_seen"))
        age_h = (now() - listed).total_seconds() / 3600 if listed else 0
        if listed and age_h <= 1:
            parts["fresh"] = 5
            reasons.append("listed in the last hour +5")
        elif age_h > STALE_DAYS * 24:
            parts["fresh"] = -STALE_PENALTY
            reasons.append(f"listed {age_h / 24:.0f} days ago, likely overpriced -{STALE_PENALTY}")
    else:
        ends = parse_time(it.get("end_time"))
        if ends and it["bid_count"] == 0 and (ends - now()).total_seconds() <= 3600:
            parts["fresh"] = 5
            reasons.append("no bids, ends within the hour +5")

    # 5. Extras: where other buyers are less likely to be looking.
    parts["extra"] = 0
    fb = it.get("seller_feedback")
    if fb is not None and fb < NEW_SELLER:
        parts["extra"] += 5
        reasons.append(f"new seller ({fb} feedback), often underpriced +5")
    if late_night(it, tz):
        parts["extra"] += 5
        reasons.append("ends 1-6 AM Eastern with few bids +5")

    word = other_sport(it["title"])
    if word:
        parts["extra"] -= OTHER_SPORT_PENALTY
        reasons.append(f"other-sport word ({word}) -{OTHER_SPORT_PENALTY}")

    # 6. Your own research: sold prices / sell-through you typed in, and your risers.
    add, why = manual.points(info, market)
    parts["extra"] += add
    reasons += why
    for p in info["players"]:
        if p in (risers or {}):
            parts["extra"] += RISER_POINTS
            reasons.append(f"riser {p.title()} +{RISER_POINTS}")

    return round(max(0, min(100, sum(parts.values())))), reasons
