"""Check one card by hand: is this price a good deal?

  python check.py "2025 Bowman Chrome Jesus Made 1st Auto Refractor /499" 80
  python check.py "2025 Bowman Chrome Jesus Made 1st Auto Refractor /499" 75 --ship 4.99

It reads the title the same way the scanner does, shows the sales it has recorded
for that exact card (from auctions it tracked + your manual_comps.csv), estimates
your profit, and prints links to look up sold prices yourself.

It first downloads the scanner's latest database from your GitHub repo (the
scanner-data branch), so it uses the same prices as the live site. No eBay keys
needed. Add --offline to skip the download and use the local data\\cards.db.
"""
import argparse
import os
import statistics
import subprocess

from main import load, HERE
from parse import Parser
from store import Store
import webpage


def open_store(offline=False):
    """Open the newest price database we can get.

    Normally: download data/cards.db from the scanner-data branch on GitHub (what the
    live site uses) into data/github.db. If that fails (offline, no git), use the local
    data/cards.db from your own dry runs instead.
    """
    copy = os.path.join(HERE, "data", "github.db")
    if not offline:
        try:
            # "git fetch" downloads the branch; "git show" gives us the file inside it.
            subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", "scanner-data"],
                           cwd=HERE, check=True, capture_output=True, timeout=60)
            data = subprocess.run(["git", "show", "origin/scanner-data:data/cards.db"],
                                  cwd=HERE, check=True, capture_output=True,
                                  timeout=60).stdout
            with open(copy, "wb") as f:
                f.write(data)
            print("Using the latest prices from GitHub.")
            return Store(copy)
        except (OSError, subprocess.SubprocessError):
            print("Couldn't download the latest prices from GitHub; using local data.")
    return Store(os.path.join(HERE, "data", "cards.db"))


def assess(card, total, store, cfg):
    """Judge one card at a price (price + shipping). Used by check.py and paste.py.

    Returns a dict:
      comps    recorded sales of this exact card (list of rows)
      median   median sale, or None
      ask, n_asks   median Buy It Now asking price of this exact card, and how many
      profit   est. profit reselling on eBay (at the median sale, else at the ask)
      under    how far under that price you'd pay (0.30 = 30% under)
      verdict  a short word or two, e.g. "DEAL"
    """
    d, rec = cfg["deal"], cfg["recommend"]
    comps = store.recent_comps(card, d["comp_days"])
    median = statistics.median(r["total"] for r in comps) if comps else None
    ask, n_asks = store.ask_stats(card, rec["ask_days"])

    def profit_at(value):
        # what you'd keep after selling at `value`: eBay fee, shipping it out, your cost
        return value * (1 - d["ebay_fee_rate"]) - d["ship_out_cost"] - total

    profit = under = None
    if median and len(comps) >= d["min_comps"]:
        profit, under = profit_at(median), 1 - total / median
        good = under >= d["min_discount"] and profit >= d["min_profit"]
        verdict = "DEAL" if good else "not a deal"
    elif ask is not None and n_asks >= rec["min_asks"]:
        # Not enough sales yet: compare with what other sellers ask (runs high).
        profit, under = profit_at(ask), 1 - total / ask
        good = under >= rec["min_under_ask"] and profit >= d["min_profit"]
        verdict = "good vs. asking prices" if good else "not cheap vs. asking prices"
    else:
        verdict = "no data yet: look it up"
    return {"comps": comps, "median": median, "ask": ask, "n_asks": n_asks,
            "profit": profit, "under": under, "verdict": verdict}


def main():
    ap = argparse.ArgumentParser(description="Is this card price a good deal?")
    ap.add_argument("title", help="the listing title, in quotes")
    ap.add_argument("price", type=float, help="the price you'd pay")
    ap.add_argument("--ship", type=float, default=0.0, help="shipping cost (default 0)")
    ap.add_argument("--offline", action="store_true",
                    help="don't download the latest prices from GitHub")
    args = ap.parse_args()

    cfg = load("config.yaml")
    d = cfg["deal"]
    parser = Parser(load("prospects.yaml")["prospects"], cfg["exclude_words"])
    card = parser.parse(args.title)
    if not card:
        print("That title didn't match any player in prospects.yaml "
              "(or it contains an excluded word like 'reprint').")
        return
    if card.is_lot:
        print("That looks like a lot. Lots can't be valued automatically - "
              "look up each card separately.")
        return

    print(f"Card key: {card.key}")
    store = open_store(args.offline)
    store.import_manual_comps(os.path.join(HERE, "manual_comps.csv"), parser)
    store.commit()

    total = args.price + args.ship
    a = assess(card, total, store, cfg)
    print(f"You'd pay: ${total:.2f}\n")

    if a["comps"]:
        print(f"Recorded sales in the last {d['comp_days']} days ({len(a['comps'])}):")
        for r in a["comps"]:
            print(f"  ${r['total']:>8.2f}  {r['sold_at'][:10]}  ({r['source']})")
        print(f"Median sale: ${a['median']:.2f}")
    else:
        print("No recorded sales for this exact card yet.")
    if a["ask"] is not None:
        print(f"Other sellers are asking: median ${a['ask']:.2f} across {a['n_asks']} "
              f"Buy It Now listings. Asking prices run higher than sales.")
    if a["profit"] is not None:
        print(f"\nYou'd pay {a['under']:.0%} under | est. profit after fees and "
              f"shipping: ${a['profit']:.2f}")
    print(f"Verdict: {a['verdict']}")

    print("\nLook up sold prices yourself:")
    print(f"  search for: {webpage.search_words(card)}")
    for label, url in webpage.lookup_links(card):
        print(f"  {label}: {url}")
    print("\nFound sales? Add them to manual_comps.csv (title,total_price,sold_date) "
          "and the scanner will use them too.")


if __name__ == "__main__":
    main()
