"""Your Good / Medium / Bad ratings, and what the spotter learns from them.

How a rating travels:
  1. You tap Good / Medium / Bad on the web page (or on a phone alert).
  2. That sends a tiny message, e.g. "good v1|1234567890|0", to your private ntfy
     ratings topic (NTFY_FEEDBACK_TOPIC). ntfy.sh keeps messages for about 12 hours.
  3. Every scan reads the new messages (fetch), saves each rating with the lot's
     title, and works out what you like (learn).

What it learns (plain counting, no AI):
  Each rated lot is broken into "tokens": prospects named, year, product,
  features (1st Bowman, auto, refractor, Mojo, PSA 10, ...). Good = +2,
  Medium = +1, Bad = -2. Tokens adding up to +2 or more, from at least 2 lots you
  rated Good or Medium, are things you like. Those become new searches.
"""
import json
import re
from collections import Counter

import requests

from parse import PRODUCTS, TEAM_COLOR_WORDS, norm

LABELS = {"good": 2, "medium": 1, "bad": -2}

# (name, pattern) checked against the lot's text. The name is also the search word.
FEATURE_WORDS = [
    ("1st bowman", r"\b1st\b(?! ?ed\b| ?edition).{0,20}\bbowman\b|\bbowman\b.{0,30}\b1st\b(?! ?ed\b| ?edition)"),
    ("auto", r"\b(auto|autos|autograph|autographs)\b"),
    ("refractor", r"\brefractors?\b"),
    ("mojo", r"\bmojo\b"), ("sapphire", r"\bsapphire\b"), ("wave", r"\bwave\b"),
    ("speckle", r"\bspeckle\b"), ("shimmer", r"\bshimmer\b"), ("lava", r"\blava\b"),
    ("gold", r"\bgold\b"), ("orange", r"\borange\b"), ("purple", r"\bpurple\b"),
    ("green", r"\bgreen\b"), ("blue", r"\bblue\b"), ("red", r"\bred\b"),
    ("psa 10", r"\bpsa ?10\b"), ("numbered", r"(?<![\w$])/\s?\d{1,4}\b|\bnumbered\b"),
    ("rc", r"\b(rc|rcs|rookie|rookies)\b"),
]
# How a feature is written inside a search (the product already says "bowman")
QUERY_WORD = {"1st bowman": "1st"}


def fetch(topic, since):
    """Ratings posted since last time. `since` is the last message id we read (or None).
    Returns ([(item_id, label, unix time), ...], newest message id)."""
    r = requests.get(f"https://ntfy.sh/{topic}/json",
                     params={"poll": "1", "since": since or "12h"}, timeout=20)
    r.raise_for_status()
    out, last = [], since
    for line in r.text.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("event") != "message":
            continue
        last = m.get("id", last)
        parts = (m.get("message") or "").strip().split(" ", 1)
        if len(parts) == 2 and parts[0] in LABELS:
            out.append((parts[1].strip(), parts[0], m.get("time")))
    return out, last


def tokens(text, players):
    """What a lot is 'made of': {("player", "jesus made"), ("year", "2025"), ...}"""
    t = norm(text)
    for team in TEAM_COLOR_WORDS:                 # "Red Sox" is not a red parallel
        t = t.replace(team, " ")
    out = {("player", p) for p in players}
    for y in set(re.findall(r"\b(20[12]\d)\b", t)):
        out.add(("year", y))
    product = next((p for p in PRODUCTS if p in t), None)
    if product and product != "bowman":           # plain "bowman" says too little
        out.add(("product", product))
    for name, pattern in FEATURE_WORDS:
        if re.search(pattern, t):
            out.add(("feature", name))
    return out


def label_text(token):
    kind, value = token
    return value.title() if kind == "player" else value


def learn(rows, existing_queries, max_searches):
    """rows: saved ratings, each {"label", "tokens", "search"}.
    Returns what you like / don't like, and new searches to try."""
    net, liked_count = Counter(), Counter()
    for r in rows:
        w = LABELS[r["label"]]
        for tok in map(tuple, r["tokens"]):
            net[tok] += w
            if w > 0:
                liked_count[tok] += 1
    ranked = sorted(net, key=lambda t: -net[t])
    liked = [t for t in ranked if net[t] >= 2 and liked_count[t] >= 2]
    disliked = [t for t in reversed(ranked) if net[t] <= -4]

    queries = []
    # 1. Prospects you keep liking: one OR search per 4 of them
    players = [v.title() for k, v in liked if k == "player"][:8]
    for i in range(0, len(players), 4):
        queries.append("lot (" + ", ".join(players[i:i + 4]) + ")")
    # 2. Your favorite year + product, with each feature you like
    year = next((v for k, v in liked if k == "year"), "")
    product = next((v for k, v in liked if k == "product"), "bowman")
    base = f"{year} {product}".strip()
    features = [QUERY_WORD.get(v, v) for k, v in liked if k == "feature"]
    for f in features[:3]:
        queries.append(f"{base} {f} lot")
    if not features and base != "bowman":
        queries.append(f"{base} lot")

    have = {norm(q) for q in existing_queries}
    queries = [q for q in dict.fromkeys(queries) if norm(q) not in have and len(q) <= 100]
    return {"liked": [(label_text(t), net[t]) for t in liked[:15]],
            "disliked": [(label_text(t), net[t]) for t in disliked[:15]],
            "queries": queries[:max_searches], "rated": len(rows),
            "counts": Counter(r["label"] for r in rows)}


def search_ratings(rows):
    """{search: Counter(good=.., medium=.., bad=..)} - how you rated each search's lots."""
    out = {}
    for r in rows:
        out.setdefault(r["search"], Counter())[r["label"]] += 1
    return out
