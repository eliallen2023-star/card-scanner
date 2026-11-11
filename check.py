"""Check one card by hand: is this price a good deal?

  python check.py "2025 Bowman Chrome Jesus Made 1st Auto Refractor /499" 80
  python check.py "2025 Bowman Chrome Jesus Made 1st Auto Refractor /499" 75 --ship 4.99

It reads the title the same way the scanner does, shows the sales it has recorded
for that exact card (from auctions it tracked + your manual_comps.csv), estimates
your profit, and prints links to look up sold prices yourself.

Works offline - no eBay keys needed.
"""
import argparse
import os
import statistics

from main import load, HERE
from parse import Parser
from store import Store
import webpage


def main():
    ap = argparse.ArgumentParser(description="Is this card price a good deal?")
    ap.add_argument("title", help="the listing title, in quotes")
    ap.add_argument("price", type=float, help="the price you'd pay")
    ap.add_argument("--ship", type=float, default=0.0, help="shipping cost (default 0)")
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
    store = Store(os.path.join(HERE, "data", "cards.db"))
    store.import_manual_comps(os.path.join(HERE, "manual_comps.csv"), parser)
    store.commit()

    rows = store.recent_comps(card, d["comp_days"])
    total = args.price + args.ship
    print(f"You'd pay: ${total:.2f}\n")

    if rows:
        print(f"Recorded sales in the last {d['comp_days']} days ({len(rows)}):")
        for r in rows:
            print(f"  ${r['total']:>8.2f}  {r['sold_at'][:10]}  ({r['source']})")
        median = statistics.median(r["total"] for r in rows)
        profit = median * (1 - d["ebay_fee_rate"]) - d["ship_out_cost"] - total
        discount = 1 - total / median
        print(f"\nMedian sale: ${median:.2f} | you'd pay {discount:.0%} under | "
              f"est. profit after fees and shipping: ${profit:.2f}")
        good = discount >= d["min_discount"] and profit >= d["min_profit"] \
            and len(rows) >= d["min_comps"]
        if good:
            print("Verdict: looks like a DEAL by your config.yaml rules.")
        elif len(rows) < d["min_comps"]:
            print(f"Verdict: not enough sales to trust yet (need {d['min_comps']}). "
                  "Check the links below.")
        else:
            print("Verdict: not a deal by your rules.")
    else:
        print("No recorded sales for this exact card yet.")

    ask, n_asks = store.ask_stats(card, cfg["recommend"]["ask_days"])
    if ask is not None:
        print(f"\nOther sellers are asking: median ${ask:.2f} across {n_asks} Buy It Now "
              f"listings (last {cfg['recommend']['ask_days']} days) - you'd pay "
              f"{1 - total / ask:.0%} under. Asking prices run higher than sales.")

    print("\nLook up sold prices yourself:")
    print(f"  search for: {webpage.search_words(card)}")
    for label, url in webpage.lookup_links(card):
        print(f"  {label}: {url}")
    print("\nFound sales? Add them to manual_comps.csv (title,total_price,sold_date) "
          "and the scanner will use them too.")


if __name__ == "__main__":
    main()
