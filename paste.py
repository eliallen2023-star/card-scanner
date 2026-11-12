"""Paste mode: judge every single card AND lot in a copied sale post or a whole page.

  python paste.py                  # reads what you copied (the clipboard)
  python paste.py --type           # or paste it into the terminal, then type  done
  python paste.py --file post.txt  # or read it from a text file
  python paste.py --year 2025      # year to assume for cards that don't say one
  python paste.py --ship 5         # shipping to add when a price isn't "shipped" (default $5)

Typical use: open a Facebook group, press Ctrl+A then Ctrl+C to copy the whole page,
and run  python paste.py. You copy the page yourself; nothing here touches Facebook
(it doesn't allow automated access).

How it reads the text:
  * One line with a prospect and a price is one card:  "Jesus Made 1st Auto /499 $80 shipped".
    The price can also be on the line just below (or just above, the Marketplace layout).
  * Last names work too ("Made 1st auto"), see LAST NAMES below.
  * A line saying "lot", "25 cards", "bundle" or naming 2+ prospects is a lot. Card lines
    without prices right under it are the lot's checklist. Its price can be on the lot
    line or come after the checklist.
  * Everything else (Like, Comment, names, times, chit-chat) is skipped.
"""
import argparse
import os
import re
import subprocess
import sys
import unicodedata

import lots
import webpage
from check import assess, open_store
from main import load, HERE
from parse import Parser, norm

# ---------------------------------------------------------------------------
# Prices
# A price: "$80", "$80.50", "80$", or a number followed by a sale word ("80 shipped").
# Numbers after "/" (serials like /499) or "#" (card numbers) are never prices.
NUM = r"(\d{1,5}(?:\.\d{1,2})?)"
PRICE_RES = [
    re.compile(r"\$\s*" + NUM + r"\b"),
    re.compile(r"(?<![/#\d.])" + NUM + r"\s*\$"),
    re.compile(r"(?<![/#\d.])" + NUM + r"\s*(?:shipped|ship|obo|firm|or best|ono|each|ea)\b",
               re.I),
    re.compile(r"(?<![/#\d.])" + NUM + r"\s*(?:\+|plus)\s*(?:ship\w*|s/?h)\b", re.I),
    re.compile(r"(?:\bfor|\bat|@)\s*" + NUM + r"\b", re.I),
]
SHIPPED = re.compile(r"\b(shipped|free ship\w*|ship(ping)? included|ppd|postpaid)\b", re.I)
PLUS_SHIP = re.compile(r"(\+|plus)\s*(ship\w*|s/?h)\b", re.I)
ALL_SHIPPED = re.compile(r"\ball\b.*\bshipped\b|\bprices? (are |include )?shipped\b", re.I)

# Shorthand card collectors use in posts, spelled out so the parser understands it.
SHORTHAND = [
    (r"\bbdc\b", "bowman draft chrome"),
    (r"\bbcp\b", "bowman chrome prospects"),
    (r"\bbd\b", "bowman draft"),
    (r"\bref\b", "refractor"),
    (r"\bauto'?d\b", "auto"),
]

# A line that is a lot: "lot", "bundle", "25 cards", "x10".
LOT_WORDS = re.compile(r"\blots?\b|\bbundle\b|\b\d+\s*(card|cards|ct)\b", re.I)

# ---------------------------------------------------------------------------
# LAST NAMES: "Made 1st auto" means Jesus Made, but only when it's safe:
#   * the line also has card words (1st, Bowman, auto, /99 ...), so chat like
#     "I made a trade" never counts,
#   * no other prospect on the list has that last name (two Hernandezes -> skip),
#   * last names that are everyday words must be Capitalized ("Made", not "made").
CARD_WORDS = re.compile(
    r"\b(1st|first|bowman|chrome|auto|autos|autograph|refractor|rc|rookie|psa|bgs|sgc|"
    r"topps|draft|prospects?|lot|numbered|gold|orange|red|blue|green|purple|black|"
    r"superfractor|sapphire|parallel)\b|/\d", re.I)
EVERYDAY_WORDS = {"made", "white", "booth", "lackey", "clark", "green", "young", "king",
                  "rice", "price", "story", "may", "will", "banks", "walker", "wells",
                  "bell", "rose", "house", "mann", "cross", "short", "ford", "hill",
                  "little", "black", "brown", "gray", "grant", "cash", "law", "page"}
TEAMS = re.compile(r"\b(red|white)\s+sox\b|\bblue\s+jays\b", re.I)
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii"}


def strip_accents(text):
    """Jesús -> Jesus, Peña -> Pena (keeps upper/lower case)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def last_name_map(prospects):
    """{"made": "jesus made", "de vries": "leo de vries", "devries": ..., ...}
    Last names shared by two prospects are left out (we can't tell them apart)."""
    owners = {}
    for p in prospects:
        canon = norm(p["name"])
        for full in [p["name"]] + list(p.get("aliases") or []):
            words = [w for w in norm(full).split() if w not in SUFFIXES]
            if len(words) >= 2:
                owners.setdefault(" ".join(words[1:]), set()).add(canon)
    return {last: names.pop() for last, names in owners.items() if len(names) == 1}


def add_full_names(line, parser, lastnames):
    """Put the full name in front of a last name it's safe to match.
    Returns (new line, ["Made = Jesus Made", ...])."""
    if not CARD_WORDS.search(line):
        return line, []
    masked = TEAMS.sub(lambda m: " " * len(m.group()), line)   # "White Sox" isn't White
    already = set(parser.players_in(norm(line)))
    matched = []
    # longest last names first, so "de vries" wins over a shorter overlap
    for last in sorted(lastnames, key=len, reverse=True):
        canon = lastnames[last]
        if canon in already:
            continue
        rx = r"(?<![A-Za-z])" + r"\s+".join(map(re.escape, last.split())) + r"(?![A-Za-z])"
        for m in re.finditer(rx, masked, re.I):
            word = line[m.start():m.end()]
            if last in EVERYDAY_WORDS and not word[0].isupper():
                continue
            line = line[:m.start()] + canon + line[m.end():]
            masked = masked[:m.start()] + canon + masked[m.end():]
            matched.append(f"{word} = {canon.title()}")
            already.add(canon)
            break
    return line, matched


# ---------------------------------------------------------------------------
def find_price(line):
    """Return (price, text without the price) or (None, line). Uses the last price on the line."""
    best = None
    for rx in PRICE_RES:
        for m in rx.finditer(line):
            if best is None or m.start() > best.start():
                best = m
    if not best:
        return None, line
    return float(best.group(1)), line[:best.start()] + " " + line[best.end():]


def expand(text):
    for pattern, words in SHORTHAND:
        text = re.sub(pattern, words, text, flags=re.I)
    # "1st chrome auto" with no brand at all: a 1st is a Bowman card.
    if re.search(r"\b1st\b", text, re.I) and not re.search(r"bowman|topps", text, re.I):
        if re.search(r"\bchrome\b", text, re.I):
            text = re.sub(r"\bchrome\b", "bowman chrome", text, count=1, flags=re.I)
        else:
            text = "bowman " + text
    return text


def read_items(text, parser, lastnames, default_year, extra_ship):
    """Turn pasted text into a list of singles and lots. Returns (items, notes)."""
    all_shipped = bool(ALL_SHIPPED.search(text))
    items, notes, seen = [], [], set()
    pending = None      # a card line still waiting for its price (on the next lines)
    lot = None          # a lot being read: header, checklist lines, price
    loose_price = None  # a price-only line; may belong to the card on the next line
    n = 0               # counts non-empty lines, to know what "next line" means

    def shipping(raw_text):
        # "+ ship" on the line itself beats an "all prices shipped" from some other post
        shipped = not PLUS_SHIP.search(raw_text) and \
            (all_shipped or bool(SHIPPED.search(raw_text)))
        return 0.0 if shipped else extra_ship, "shipped" if shipped else \
            (f"+ ${extra_ship:.2f} ship (assumed)" if extra_ship else "no shipping added")

    def add(item):
        key = (item["kind"], item["line"], item["price"])
        if key not in seen:                     # the same post copied twice
            seen.add(key)
            item["ship"], item["ship_note"] = shipping(item["line"])
            items.append(item)

    def close_lot():
        nonlocal lot
        if lot and not parser.players_in(norm(" ".join([lot["head"]] + lot["checklist"]))):
            lot = None                          # a lot with none of your prospects: skip
        if lot:
            if lot["price"] is None:
                notes.append(f"skipped lot (no price found): {lot['line'][:90]}")
            else:
                add({"kind": "lot", **lot})
        lot = None

    for raw in text.splitlines():
        line = strip_accents(raw).strip()
        if not line:
            continue
        n += 1
        price, rest = find_price(line)
        words, matched = add_full_names(expand(rest), parser, lastnames)
        if default_year and not re.search(r"\b20[12]\d\b", words):
            words = f"{default_year} {words}"
        card = parser.parse(words)

        # --- a new lot starts here
        if (card and card.is_lot) or (card is None and LOT_WORDS.search(words)
                                      and CARD_WORDS.search(words)):
            close_lot()
            pending = None
            lot = {"line": line, "head": words, "checklist": [], "price": price,
                   "matched": matched, "quiet": 0}
            continue

        # --- inside a lot: collect its checklist and its price
        if lot:
            if card and price is None and lot["quiet"] == 0:   # "Jesus Made 1st" right under the lot
                lot["checklist"].append(words)
                lot["line"] += " | " + line
                lot["matched"] += matched
                lot["quiet"] = 0
                continue
            if card is None and price is not None and lot["price"] is None:
                lot["price"] = price                    # "$30 shipped for all"
                lot["line"] += " | " + line
                close_lot()
                continue
            if card is None and price is None:
                lot["quiet"] += 1                       # Like / Comment / names ...
                if lot["quiet"] >= 6:
                    close_lot()                         # nothing more about this lot
                continue
            # Anything else (another card, or a second price) starts something new.
            close_lot()

        # --- singles
        if card is None:
            if price is not None and pending and n - pending["n"] <= 2:
                card, words, matched = pending["card"], pending["words"], pending["matched"]
                line = pending["line"] + " | " + line   # name above, price below
                pending = None
            else:
                if price is not None:
                    loose_price = (price, n, line)
                continue
        elif price is None:
            if loose_price and loose_price[1] == n - 1:  # price above, name below
                price, line = loose_price[0], loose_price[2] + " | " + line
                loose_price = None
            else:
                pending = {"card": card, "words": words, "line": line, "n": n,
                           "matched": matched}
                continue
        pending = None
        add({"kind": "single", "line": line, "card": card, "price": price,
             "matched": matched})

    close_lot()
    return items, notes


# ---------------------------------------------------------------------------
def assess_lot(item, store, cfg, parser, ranks):
    """Value a pasted lot card by card (same rules as eBay lots on the website)."""
    d, B = cfg["deal"], cfg["lots"]["bulk"]
    head, checklist = item["head"], item["checklist"]
    if len(checklist) < 2:                  # one line isn't a checklist: read it with the header
        head, checklist = " ".join([head] + checklist), []
    details = {"lines": checklist, "count": None, "players": []}
    cards, unnamed, _ = lots.cards_in_lot(head, details, parser)
    count = lots.card_count(head, details)
    total = item["price"] + item["ship"]
    a = {"cards": cards, "total": total, "count": count, "rows": [], "singles": 0.0,
         "profit": None, "under": None, "per_card": None, "tags": []}
    if not cards:
        a["verdict"] = "names none of your prospects"
        return a

    rows, singles = lots.value_rows(cards, store, cfg)
    text = norm(item["line"])
    first = any(c.first for c in cards) or bool(re.search(lots.FIRST, text))
    rc = any(c.rookie for c in cards) or bool(re.search(lots.ROOKIE, text))
    a.update(rows=rows, singles=singles, profit=lots.resale_profit(rows, total, cfg),
             tags=(["1st"] if first else []) + (["RC"] if rc else []))
    if count:
        a["per_card"] = total / count
    if singles > 0:
        a["under"] = 1 - total / singles

    if a["under"] is not None and a["under"] >= d["min_discount"] \
            and a["profit"] >= d["min_profit"]:
        a["verdict"] = "LOT DEAL"
    elif a["per_card"] is not None and a["per_card"] <= B["max_price_per_card"] \
            and count >= B["min_cards"] and (first or rc):
        a["verdict"] = f"cheap 1st/RC lot (${a['per_card']:.2f} a card)"
    elif singles > 0:
        a["verdict"] = "not a deal"
    else:
        a["verdict"] = "no data yet: look it up"
    # sort the lot with the singles: rank of its best prospect
    a["players"] = sorted({c.player for c in cards}, key=lambda p: ranks.get(p, 99))
    return a


def read_clipboard():
    """What you copied (Ctrl+C), using Windows PowerShell's Get-Clipboard."""
    cmd = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                         capture_output=True, timeout=30)
    return out.stdout.decode("utf-8", errors="replace")


def read_text(args):
    if args.file:
        with open(args.file, encoding="utf-8-sig") as f:
            return f.read()
    if args.type:
        print("Paste below. When you're done, type  done  on its own line and press Enter.")
        lines = []
        for line in sys.stdin:
            if line.strip().lower() == "done":
                break
            lines.append(line)
        return "".join(lines)
    text = read_clipboard()
    print(f"Read {len(text.splitlines())} lines from what you copied.")
    return text


def print_single(i, it, a):
    card = it["card"]
    print(f"{i}. SINGLE  {webpage.card_label(card)}")
    print(f"   post: {it['line'][:150]}")
    if it["matched"]:
        print(f"   (matched by last name: {', '.join(it['matched'])} - check it)")
    print(f"   you'd pay ${it['price'] + it['ship']:.2f}  (${it['price']:.2f}, {it['ship_note']})")
    if card.year == "?":
        print("   ! no year in the post - add --year 2025 (or the right year) for exact prices")
    if a["median"] is not None:
        print(f"   sold: median ${a['median']:.2f} from {len(a['comps'])} sale(s)")
    if a["ask"] is not None:
        print(f"   asking: median ${a['ask']:.2f} from {a['n_asks']} eBay listing(s)")
    if a["profit"] is not None:
        side = "under" if a["under"] >= 0 else "over"
        print(f"   {abs(a['under']):.0%} {side} | est. profit if resold on eBay: ${a['profit']:.2f}")
    print(f"   VERDICT: {a['verdict']}")
    for label, url in webpage.lookup_links(card)[:2]:
        print(f"   {label}: {url}")


def print_lot(i, it, a):
    size = f"{a['count']} cards" if a["count"] else "card count not given"
    print(f"{i}. LOT  {size}" + (f", {' + '.join(a['tags'])}" if a["tags"] else ""))
    print(f"   post: {it['line'][:150]}")
    if it["matched"]:
        print(f"   (matched by last name: {', '.join(it['matched'])} - check it)")
    print(f"   you'd pay ${a['total']:.2f}  (${it['price']:.2f}, {it['ship_note']})"
          + (f" = ${a['per_card']:.2f} a card" if a["per_card"] else ""))
    for r in a["rows"][:6]:
        value = f"${r['value']:.2f}" if r["value"] else "no data"
        print(f"     {r['qty']}x {webpage.card_label(r['card'])}: {value} ({r['source']})")
    if len(a["rows"]) > 6:
        print(f"     ... and {len(a['rows']) - 6} more")
    if a["singles"]:
        side = "under" if a["under"] >= 0 else "over"
        print(f"   singles value ${a['singles']:.2f}: you'd pay {abs(a['under']):.0%} {side} | "
              f"est. profit selling the singles: ${a['profit']:.2f}")
    print(f"   VERDICT: {a['verdict']}")


def main():
    ap = argparse.ArgumentParser(description="Judge every card and lot in copied sale posts.")
    ap.add_argument("--file", help="read from this text file")
    ap.add_argument("--type", action="store_true", help="paste into the terminal instead")
    ap.add_argument("--year", help="year for cards that don't say one, e.g. 2025")
    ap.add_argument("--ship", type=float, default=5.0,
                    help="shipping to add when a price doesn't say shipped (default 5)")
    ap.add_argument("--offline", action="store_true",
                    help="don't download the latest prices from GitHub")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")    # odd characters can't crash the printout

    cfg = load("config.yaml")
    prospects = load("prospects.yaml")["prospects"]
    parser = Parser(prospects, cfg["exclude_words"])
    ranks = {norm(p["name"]): p["rank"] for p in prospects}
    items, notes = read_items(read_text(args), parser, last_name_map(prospects),
                              args.year, args.ship)
    if not items:
        print("\nNo cards or lots found. A card needs a prospect's name and a price "
              "like $80 or 80 shipped.")
        for n in notes:
            print("  " + n)
        return

    store = open_store(args.offline)
    store.import_manual_comps(os.path.join(HERE, "manual_comps.csv"), parser)
    store.commit()

    results = []
    for it in items:
        if it["kind"] == "single":
            a = assess(it["card"], it["price"] + it["ship"], store, cfg)
        else:
            a = assess_lot(it, store, cfg, parser, ranks)
        results.append((it, a))

    # best first: deals, then worth a look, then the rest by estimated profit
    def order(r):
        v = r[1]["verdict"]
        group = 0 if "DEAL" in v else 1 if v.startswith(("good", "cheap")) else 2
        return group, -(r[1]["profit"] if r[1]["profit"] is not None else -1e9)
    results.sort(key=order)

    singles = sum(1 for it, _ in results if it["kind"] == "single")
    deals = sum(1 for _, a in results if "DEAL" in a["verdict"])
    look = sum(1 for _, a in results if a["verdict"].startswith(("good", "cheap")))
    print(f"\nFound {singles} single(s) and {len(results) - singles} lot(s): "
          f"{deals} deal(s), {look} worth a look.\n")
    for i, (it, a) in enumerate(results, 1):
        (print_single if it["kind"] == "single" else print_lot)(i, it, a)
        print()
    for n in notes:
        print(n)
    print("Before you pay: use PayPal Goods & Services (not Friends & Family), ask for a "
          "photo with the seller's name and date, and check their references.")


if __name__ == "__main__":
    main()
