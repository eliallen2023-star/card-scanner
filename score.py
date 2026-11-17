"""Score a lot from 0 to 100: how worth a look is it?

Plain code on purpose (no AI): each part adds points, and every point is explained
on the web page so you can see WHY a lot scored what it did. Change the numbers
here if your experience says otherwise.

  Prospects named   up to 45   #1 prospect = 25, #25 = 13, #50 = 0.5 (added up for each one)
  Card types        up to 30   1st Bowman 15, auto 10, numbered 6, graded 4, refractor/color 4, ...
  Price per card    up to 20   $0.50 or less = 20, $1 = 15, $2 = 10, $3 = 6, $5 = 3
  Fresh             up to  5   Buy It Now listed in the last hour, or an auction ending
                               within the hour with no bids
"""
import re

import lots
from parse import norm, TEAM_COLOR_WORDS
from store import now, parse_time

# Words that mean "this is more than one card" (for listings in the Singles category).
LOT_WORDS = re.compile(r"\blots?\b|\bbundle\b|\bcollection\b|\b\d+\s*(card|cards|ct)\b|\bx\s?\d+\b")

COLORS = r"gold|orange|red|purple|blue|green|aqua|black|pink|sapphire|atomic|speckle|mojo|shimmer|wave|lava|superfractor"
FEATURES = [  # (name, points, pattern) - checked against the title + item specifics + description
    # "1st Edition" / "1st Ed." is a product name, not a first card
    ("1st Bowman", 15, r"\b1st\b(?! ?ed\b| ?edition).{0,20}\bbowman\b|\bbowman\b.{0,30}\b1st\b(?! ?ed\b| ?edition)"),
    ("1st", 8, r"\b(1st|first)\b(?! ?ed\b| ?edition)"),   # only counts if not already 1st Bowman
    ("Auto", 10, r"\b(auto|autos|autograph|autographs|autographed)\b"),
    ("Numbered", 6, r"(?<![\w$])/\s?\d{1,4}\b|#'?d\b|\bnumbered\b|\bserial\b"),
    ("Graded", 4, r"\b(psa|bgs|sgc|cgc)\s?\d"),
    ("Refractor/color", 4, r"\brefractors?\b|\bx-?fractor\b|\b(" + COLORS + r")\b"),
    ("Chrome", 3, r"\bchrome\b"),
    ("RC", 3, r"\b(rc|rcs|rookie|rookies)\b"),
]
MAX = {"prospects": 45, "cards": 30, "price": 20, "fresh": 5}


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
    return {"players": parser.players_in(named), "count": count, "total": total,
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


def score_lot(it, info, ranks):
    """Returns (score 0-100, list of reasons like "#1 Jesus Made +25")."""
    reasons, parts = [], {}

    # 1. Prospects: higher-ranked prospects are worth more points.
    pts = 0
    for p in sorted(info["players"], key=lambda p: ranks.get(p, 99)):
        rank = ranks.get(p, 50)
        add = (51 - rank) / 50 * 25
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
    parts["cards"] = min(pts, MAX["cards"])

    # 3. Price per card (price + shipping, divided by the number of cards).
    per = info["per_card"]
    if per is None:
        parts["price"] = 0
        reasons.append("card count unknown +0")
    else:
        add = 20 if per <= 0.5 else 15 if per <= 1 else 10 if per <= 2 else 6 if per <= 3 \
            else 3 if per <= 5 else 0
        parts["price"] = add
        reasons.append(f"${per:.2f}/card +{add}")

    # 4. Fresh: be one of the first to see it.
    parts["fresh"] = 0
    if it["buying"] == "BIN":
        listed = parse_time(it.get("listed") or it.get("first_seen"))
        if listed and (now() - listed).total_seconds() <= 3600:
            parts["fresh"] = 5
            reasons.append("listed in the last hour +5")
    else:
        ends = parse_time(it.get("end_time"))
        if ends and it["bid_count"] == 0 and (ends - now()).total_seconds() <= 3600:
            parts["fresh"] = 5
            reasons.append("no bids, ends within the hour +5")

    return round(min(100, sum(parts.values()))), reasons
