"""Paste mode: judge every card in a Facebook (or any) sale post at once.

  python paste.py                  # paste the post, then type done on its own line
  python paste.py --file post.txt  # or read the post from a text file
  python paste.py --year 2025      # year to assume for cards that don't say one
  python paste.py --ship 5         # shipping to add when a price isn't "shipped" (default $5)

You copy the post yourself; nothing here touches Facebook (it doesn't allow
automated access). Each line with a prospect's name and a price is one card:

  2025 Bowman Chrome Jesus Made 1st Auto /499 $80 shipped
  Eli Willits BDC 1st refractor 25 + ship

A name on one line with the price on the next line works too. Prices are judged
against the scanner's latest data from GitHub, the same way check.py does.
"""
import argparse
import os
import re
import sys

from check import assess, open_store
from main import load, HERE
from parse import Parser
import webpage

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

# Shorthand card collectors use in posts, spelled out so the parser understands it.
SHORTHAND = [
    (r"\bbdc\b", "bowman draft chrome"),
    (r"\bbcp\b", "bowman chrome prospects"),
    (r"\bbd\b", "bowman draft"),
    (r"\bref\b", "refractor"),
    (r"\bauto'?d\b", "auto"),
]


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


def read_cards(text, parser, default_year, extra_ship):
    """Split a post into cards. Returns a list of dicts, plus notes for skipped lines."""
    all_shipped = bool(re.search(r"\ball\b.*\bshipped\b|\bprices? (are |include )?shipped\b",
                                 text, re.I))
    cards, notes = [], []
    pending = None              # a line naming a player whose price comes on a later line
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        price, rest = find_price(line)
        words = expand(rest)
        if default_year and not re.search(r"\b20[12]\d\b", words):
            words = f"{default_year} {words}"
        card = parser.parse(words)

        if card is None and price is not None and pending:
            # price-only line ("$40 shipped") for the card on the line above
            card, words, line = pending["card"], pending["words"], pending["line"] + " " + line
        if card is None:
            continue                    # chit-chat, emojis, "DM me", players not on your list
        if card.is_lot:
            notes.append(f"skipped (more than one player, or a lot - check by hand): {line}")
            pending = None
            continue
        if price is None:
            pending = {"card": card, "words": words, "line": line}
            continue

        pending = None
        shipped = all_shipped or bool(SHIPPED.search(line))
        ship = 0.0 if shipped else extra_ship
        cards.append({"line": line, "card": card, "price": price, "ship": ship,
                      "ship_note": "shipped" if shipped else
                      (f"+ ${ship:.2f} ship (assumed)" if ship else "no shipping added")})
    if pending:
        notes.append(f"skipped (no price found): {pending['line']}")
    return cards, notes


def read_post(path):
    if path:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    print("Paste the post below. When you're done, type  done  on its own line and press Enter.")
    lines = []
    for line in sys.stdin:
        if line.strip().lower() == "done":
            break
        lines.append(line)
    return "".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Judge every card in a pasted sale post.")
    ap.add_argument("--file", help="read the post from this text file instead of pasting")
    ap.add_argument("--year", help="year for cards that don't say one, e.g. 2025")
    ap.add_argument("--ship", type=float, default=5.0,
                    help="shipping to add when a price doesn't say shipped (default 5)")
    ap.add_argument("--offline", action="store_true",
                    help="don't download the latest prices from GitHub")
    args = ap.parse_args()

    cfg = load("config.yaml")
    parser = Parser(load("prospects.yaml")["prospects"], cfg["exclude_words"])
    text = read_post(args.file)
    cards, notes = read_cards(text, parser, args.year, args.ship)
    if not cards:
        print("\nNo cards found. Each card needs a prospect's full name (as in prospects.yaml)"
              " and a price like $80 or 80 shipped.")
        for n in notes:
            print("  " + n)
        return

    store = open_store(args.offline)
    store.import_manual_comps(os.path.join(HERE, "manual_comps.csv"), parser)
    store.commit()

    results = []
    for c in cards:
        total = c["price"] + c["ship"]
        results.append((c, total, assess(c["card"], total, store, cfg)))
    # best first: deals, then by estimated profit (cards with no data last)
    order = {"DEAL": 0, "good vs. asking prices": 1}
    results.sort(key=lambda r: (order.get(r[2]["verdict"], 2),
                                -(r[2]["profit"] if r[2]["profit"] is not None else -1e9)))

    print(f"\nFound {len(results)} card(s):\n")
    for i, (c, total, a) in enumerate(results, 1):
        card = c["card"]
        print(f"{i}. {webpage.card_label(card)}")
        print(f"   post: {c['line']}")
        print(f"   you'd pay ${total:.2f}  (${c['price']:.2f}, {c['ship_note']})")
        if card.year == "?":
            print("   ! no year in the post - add --year 2025 (or the right year) for exact prices")
        if a["median"] is not None:
            print(f"   sold: median ${a['median']:.2f} from {len(a['comps'])} sale(s)")
        if a["ask"] is not None:
            print(f"   asking: median ${a['ask']:.2f} from {a['n_asks']} eBay listing(s)")
        if a["profit"] is not None:
            side = "under" if a["under"] >= 0 else "over"
            print(f"   {abs(a['under']):.0%} {side} | est. profit if resold on eBay: "
                  f"${a['profit']:.2f}")
        print(f"   VERDICT: {a['verdict']}")
        for label, url in webpage.lookup_links(card)[:2]:
            print(f"   {label}: {url}")
        print()
    for n in notes:
        print(n)
    print("Before you pay: use PayPal Goods & Services (not Friends & Family), ask for a "
          "photo with the seller's name and date, and check their references.")


if __name__ == "__main__":
    main()
