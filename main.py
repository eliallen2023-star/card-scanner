"""Card Scanner: find underpriced top-prospect cards on eBay.

  python main.py            # real run (needs EBAY_CLIENT_ID, EBAY_CLIENT_SECRET; NTFY_TOPIC optional)
  python main.py --dry-run  # real eBay search, but print alerts instead of sending them
  python main.py --demo     # fake data, no internet, no keys - just to see it work

Every run also writes a web page:
  real run  -> docs/index.html   (published by GitHub Pages)
  dry run   -> docs/preview.html (local only)
  demo      -> docs/demo.html    (local only)
"""
import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

import lots
import notify
import webpage
from parse import Parser, norm
from store import Store, iso, parse_time, now

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    # encoding="utf-8" so accented names (Jesús) read correctly on Windows too
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def in_quiet_hours(cfg):
    a = cfg["alerts"]
    h = datetime.now(ZoneInfo(a["timezone"])).hour
    s, e = a["quiet_start"], a["quiet_end"]
    return (h >= s or h < e) if s > e else (s <= h < e)


def evaluate(it, card, store, cfg, parser):
    """Return a dict describing the deal if this listing looks underpriced, else None."""
    d = cfg["deal"]
    total = it["price"] + it["shipping"]
    ends = parse_time(it["end_time"])
    hours_left = (ends - now()).total_seconds() / 3600 if ends else None

    if it["buying"] == "AUCTION" and (hours_left is None or hours_left > d["auction_alert_hours"]):
        return None

    if card.is_lot:
        # Value the lot card by card (lots.py). Returns None unless it's priced at
        # least 30% under the sum of its singles.
        if not cfg["lots"]["enabled"]:
            return None
        a = lots.evaluate_lot(it, card, store, cfg, parser)
        if a:
            a["when"] = when(it, hours_left)
            top = ", ".join(f'{r["card"].player.title()} ${r["value"]:.0f}'
                            + (f' x{r["qty"]}' if r["qty"] > 1 else "") for r in a["rows"][:4])
            a["body"] = (f"{it['title']}\n{top}\n"
                         f"Est. profit ~${a['profit']:.0f} reselling the singles\n{a['when']}")
        return a

    if card.product == "?":
        return None   # unknown product (e.g. Panini): too many different cards share one key
    median, n = store.comp_stats(card, d["comp_days"])
    if median is None or n < d["min_comps"]:
        return None
    discount = 1 - total / median
    profit = median * (1 - d["ebay_fee_rate"]) - d["ship_out_cost"] - total
    if discount < d["min_discount"] or profit < d["min_profit"]:
        return None
    return {
        "kind": "deal",
        "headline": f"{discount:.0%} under comps: ${total:.2f} vs ${median:.2f}",
        "body": (f"{it['title']}\n"
                 f"Est. profit ~${profit:.0f} after fees | {n} comps\n"
                 + when(it, hours_left)),
        "when": when(it, hours_left),
        "total": total, "median": median, "profit": profit,
        "discount": discount, "comps": n}


def is_first_bowman(card):
    return card.first and card.product.startswith("bowman")


def desirability(card, ranks):
    """How much buyers want this card, 0-130, plus readable tags. Simple on purpose:
    change the points here if your experience says otherwise."""
    rank = ranks.get(card.player, 50)
    score = (51 - rank) * 0.8              # #1 prospect = 40 points ... #50 = 0.8
    tags = [f"#{rank} prospect"]
    if is_first_bowman(card):
        score += 30; tags.append("1st Bowman")   # the card collectors want most
    elif card.first:
        score += 10; tags.append("1st")          # e.g. 1st Topps Pro Debut
    if card.rookie:
        score += 10; tags.append("RC")
    if card.auto:
        score += 20; tags.append("Auto")
    if card.serial:
        score += 15 if int(card.serial[1:]) <= 99 else 8; tags.append(card.serial)
    if card.parallel not in ("base", "refractor"):
        score += 5; tags.append(card.parallel.title())
    elif card.parallel == "refractor":
        tags.append("Refractor")
    if card.grade.endswith(" 10"):
        score += 10; tags.append(card.grade)
    return score, tags


def recommend(it, card, store, cfg, ranks):
    """A 'worth a look' pick, judged against current asking prices (not sales).
    Returns a dict like evaluate() does, or None."""
    r, d = cfg["recommend"], cfg["deal"]
    if not r["enabled"] or card.is_lot or it["buying"] != "BIN" or card.product == "?":
        return None
    total = it["price"] + it["shipping"]
    ask, n_asks = store.ask_stats(card, r["ask_days"], it["item_id"])
    if ask is None or n_asks < r["min_asks"]:
        return None
    under = 1 - total / ask
    if under < r["min_under_ask"]:
        return None
    # Same profit rule as deals, using the typical ask as the resale price.
    # This drops cheap base cards: a $1.50 card can't clear $10 after fees + shipping.
    profit = ask * (1 - d["ebay_fee_rate"]) - d["ship_out_cost"] - total
    if profit < d["min_profit"]:
        return None
    # If we DO have a sale or two and this price isn't below them, skip it.
    sold, n_sold = store.comp_stats(card, cfg["deal"]["comp_days"])
    if sold is not None and total >= sold:
        return None
    score, tags = desirability(card, ranks)
    if score < r["min_score"]:
        return None
    return {"kind": "rec",
            "headline": f"{under:.0%} under typical asking price",
            "when": when(it, None), "tags": tags,
            "total": total, "ask_median": ask, "asks": n_asks, "under": under,
            "sold_median": sold, "sold_n": n_sold,
            "score": round(score * under * 2),   # desirability x how cheap, roughly 0-100
            "ask_profit": profit,
            # profit stays None so deals (backed by real sales) always sort first
            "median": None, "profit": None, "discount": None, "comps": n_sold}


def cheap_pick(it, card, store, cfg, ranks):
    """A cheap 1st Bowman / rookie card to look at. No profit rule: these are
    cards to hold or check out, not quick flips. Returns a dict, or None."""
    c = cfg["cheap_firsts"]
    if not c["enabled"] or card.is_lot or it["buying"] != "BIN":
        return None
    if not (card.first or card.rookie):
        return None
    total = it["price"] + it["shipping"]
    if total > c["max_total"]:
        return None
    score, tags = desirability(card, ranks)
    ask, n_asks = store.ask_stats(card, cfg["recommend"]["ask_days"], it["item_id"])
    return {"kind": "cheap", "headline": f"Cheap {tags[1] if len(tags) > 1 else 'card'}",
            "when": when(it, None), "tags": tags, "total": total,
            "score": round(score), "ask_median": ask, "asks": n_asks,
            "median": None, "profit": None, "discount": None, "comps": 0}


def when(it, hours_left):
    if it["buying"] == "AUCTION":
        return f"AUCTION, {it['bid_count']} bids, ends in {hours_left:.1f}h (price will rise)"
    return "Buy It Now"


def make_query(terms, extra=""):
    """eBay search text. Several names in parentheses means 'any of these':
    (Jesus Made, Leo De Vries, Leo DeVries) finds listings naming any of them."""
    q = terms[0] if len(terms) == 1 else "(" + ", ".join(terms) + ")"
    return f"{extra} {q}".strip()


def search_groups(prospects, extra, per_search, max_len=100):
    """Pack players into as few searches as possible: up to `per_search` players each,
    and eBay allows at most 100 characters of search text. Each player's aliases
    (other spellings) go in the same search."""
    groups, cur, n = [], [], 0
    for p in prospects:
        terms = [p["name"]] + list(p.get("aliases") or [])
        if cur and (n + 1 > per_search or len(make_query(cur + terms, extra)) > max_len):
            groups.append(cur)
            cur, n = [], 0
        cur += terms
        n += 1
    if cur:
        groups.append(cur)
    return groups


def lookup_lots(candidates, store, cfg, get_details):
    """Fetch full details (description, players, card count, shipping) for lots we
    haven't looked at yet - at most N per run, each lot only once. Lots naming the
    most prospects go first, then the cheapest. Returns how many lookups were made."""
    todo = [(it, card) for it, card in candidates.values()
            if card.is_lot and store.get_lot_details(it["item_id"]) is None]
    todo.sort(key=lambda x: (-len(x[1].players_in_title), x[0]["price"] + x[0]["shipping"]))
    done = 0
    for it, card in todo[: cfg["lots"]["detail_lookups_per_run"]]:
        try:
            details = get_details(it["item_id"])
        except Exception as e:
            print(f"  lot lookup failed for {it['item_id']}: {e}")
            continue
        done += 1
        store.save_lot_details(it["item_id"], details)   # never look this one up again
        if details.get("shipping") is not None and not it["shipping_known"]:
            it["shipping"], it["shipping_known"] = details["shipping"], True
            store.save_shipping(it["item_id"], details["shipping"])
            store.upsert_listing(it, card)
    return done


def fill_shipping(candidates, store, cfg, ranks, parser, get_shipping):
    """For listings with unknown shipping that WOULD be a deal (or a recommended
    pick) if shipping were free, look up the real cost - most promising first, at
    most N per run. Returns how many lookups were made."""
    maybe = []
    for it, card in candidates.values():
        if it["shipping_known"] or card.is_lot:   # lots get shipping from lookup_lots
            continue
        # assumes free shipping for now; deals sort before recommended picks
        a = evaluate(it, card, store, cfg, parser) or recommend(it, card, store, cfg, ranks)
        if a:
            maybe.append((a["profit"] or 0, it, card))
    maybe.sort(key=lambda x: -x[0])          # biggest possible profit first

    done = 0
    for _, it, card in maybe[: cfg["search"]["shipping_lookups_per_run"]]:
        try:
            cost = get_shipping(it["item_id"])
        except Exception as e:
            print(f"  shipping lookup failed for {it['item_id']}: {e}")
            continue
        done += 1
        if cost is not None:
            it["shipping"], it["shipping_known"] = cost, True
            store.save_shipping(it["item_id"], cost)   # never look this one up again
            store.upsert_listing(it, card)
    return done


def minutes_since(store, key):
    t = parse_time(store.get_meta(key))
    return (now() - t).total_seconds() / 60 if t else float("inf")


def run(args):
    cfg, prospects = load("config.yaml"), load("prospects.yaml")["prospects"]
    parser = Parser(prospects, cfg["exclude_words"])
    ranks = {norm(p["name"]): p["rank"] for p in prospects}   # "jesus made" -> 1
    testing = args.dry_run or args.demo   # testing = never send pushes or mark anything "alerted"

    db_path = os.path.join(HERE, "data", "demo.db" if args.demo else "cards.db")
    if args.demo and os.path.exists(db_path):
        os.remove(db_path)  # the demo starts from scratch every time
    store = Store(db_path)

    eb = None
    if args.demo:
        from demo import fake_search, fake_shipping, fake_details, seed_comps
        seed_comps(store, parser)
        search, get_shipping, get_details = fake_search, fake_shipping, fake_details
    else:
        from ebay import Ebay
        client_id = os.environ.get("EBAY_CLIENT_ID")
        client_secret = os.environ.get("EBAY_CLIENT_SECRET")
        if not client_id or not client_secret:
            sys.exit("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET aren't set. "
                     "See README step 2 for how to set them.")
        eb = Ebay(client_id, client_secret, str(cfg["search"]["ship_to_zip"]))
        search, get_shipping, get_details = eb.search, eb.get_shipping, eb.item_details

    # ---- 1. Search eBay ----
    # Auctions ending soon are searched EVERY run (every 15 min on GitHub), so we
    # see each one close to its end and record a realistic sale price.
    # Buy It Now listings are searched about once an hour (new ones aren't urgent).
    s, d = cfg["search"], cfg["deal"]
    do_bin = args.demo or minutes_since(store, "last_bin_search") >= s["bin_every_minutes"] - 5
    groups = search_groups(prospects, s["extra_keywords"], s["players_per_search"])
    candidates = {}  # item_id -> (listing, card); one entry even if several searches find it
    failed = []
    for terms in groups:
        q = make_query(terms, s["extra_keywords"])
        try:
            found_items = search(q, s["category_id"], "AUCTION", "endingSoonest",
                                 s["auctions_per_search"], d["max_price"],
                                 ends_within_hours=d["auction_alert_hours"])
            if do_bin:
                found_items += search(q, s["category_id"], "FIXED_PRICE", "newlyListed",
                                      s["bin_per_search"], d["max_price"])
                if cfg["lots"]["enabled"]:
                    # eBay's separate "Trading Card Lots" category, about hourly
                    found_items += search(q, s["lot_category_id"], "FIXED_PRICE", "newlyListed",
                                          s["bin_per_search"], d["max_price"])
                    found_items += search(q, s["lot_category_id"], "AUCTION", "endingSoonest",
                                          s["auctions_per_search"], d["max_price"],
                                          ends_within_hours=d["auction_alert_hours"])
        except Exception as e:
            # One bad search shouldn't throw away the whole run - note it and move on.
            print(f"  search failed for {q}: {e}")
            failed.append(q)
            continue
        for it in found_items:
            if it["item_id"] in candidates:
                continue
            card = parser.parse(it["title"])
            if not card:
                continue
            if not it["shipping_known"]:   # did we look this one up before?
                cached = store.cached_shipping(it["item_id"])
                if cached is not None:
                    it["shipping"], it["shipping_known"] = cached, True
            store.upsert_listing(it, card)
            candidates[it["item_id"]] = (it, card)

    if do_bin and len(failed) < len(groups):
        store.set_meta("last_bin_search", iso(now()))
    elif not do_bin:
        # Between Buy It Now searches, keep the Buy It Now listings from the last
        # search so their deals don't vanish from the page for 45 minutes.
        for it in store.recent_listings("BIN", s["bin_every_minutes"] + 15):
            card = parser.parse(it["title"])
            if card and it["item_id"] not in candidates:
                candidates[it["item_id"]] = (it, card)

    # ---- 2. Turn finished auctions (and your manual_comps.csv) into comps ----
    new_comps = store.record_finished_auctions(d["comp_max_gap_minutes"])
    new_comps += store.import_manual_comps(os.path.join(HERE, "manual_comps.csv"), parser)

    # ---- 2b. Lot details (description, card count), then real shipping ----
    lot_lookups = lookup_lots(candidates, store, cfg, get_details) if cfg["lots"]["enabled"] else 0
    lookups = fill_shipping(candidates, store, cfg, ranks, parser, get_shipping)

    # ---- 3. Find deals and recommended picks (all of them go on the web page) ----
    found, lot_watch, recs, cheap = [], [], [], {}
    for it, card in candidates.values():
        a = evaluate(it, card, store, cfg, parser)
        if a and a["kind"] == "lot" and not a["alert"]:
            # under singles value, but no resale profit: page only (skip tiny bulk lots)
            if a["singles"] >= cfg["lots"]["min_watch_value"]:
                lot_watch.append((it, card, a))
            continue
        if a:
            found.append((it, card, a))
            continue
        r = recommend(it, card, store, cfg, ranks)
        if r:
            recs.append((it, card, r))
            continue
        c = cheap_pick(it, card, store, cfg, ranks)
        # keep only the cheapest listing of each exact card
        if c and (card.key not in cheap or c["total"] < cheap[card.key][2]["total"]):
            cheap[card.key] = (it, card, c)
    found.sort(key=lambda x: -(x[2]["profit"] or 0))   # biggest estimated profit first
    lot_watch.sort(key=lambda x: -x[2]["discount"])
    lot_watch = lot_watch[: cfg["lots"]["max_watch"]]
    recs.sort(key=lambda x: -x[2]["score"])
    recs = recs[: cfg["recommend"]["max_items"]]
    # every 1st Bowman before any other card; then highest score; if tied, cheapest
    cheap = sorted(cheap.values(), key=lambda x: (not is_first_bowman(x[1]),
                                                  -x[2]["score"], x[2]["total"]))
    cheap = cheap[: cfg["cheap_firsts"]["max_items"]]

    # ---- 4. Push the new ones to your phone (unless it's quiet hours) ----
    quiet = in_quiet_hours(cfg) and not args.demo
    sent = 0
    if not quiet:
        new = [x for x in found if not store.already_alerted(x[0]["item_id"])]
        for it, card, a in new[: cfg["alerts"]["max_per_run"]]:
            notify.send(os.environ.get("NTFY_TOPIC"), a["headline"], a["body"], it["url"],
                        it["image"], dry_run=testing)
            if not testing:
                store.mark_alerted(it["item_id"], a["total"], a["median"], a["profit"])
            sent += 1

    store.prune()
    store.commit()

    # ---- 5. Write the web page ----
    page = "demo.html" if args.demo else "preview.html" if args.dry_run else "index.html"
    page_path = os.path.join(HERE, "docs", page)
    updated = datetime.now(ZoneInfo(cfg["alerts"]["timezone"])).strftime("%b %d, %Y %I:%M %p %Z")
    webpage.build(page_path, found + lot_watch + recs + cheap, updated=updated, listings=len(candidates),
                  comps=store.comp_count(), demo=args.demo)

    print(f"\nsearches: {len(groups)} groups ({'auctions + Buy It Now' if do_bin else 'auctions only'})"
          f" | listings matched: {len(candidates)} | new comps: {new_comps} | "
          f"lot lookups: {lot_lookups} | shipping lookups: {lookups} | "
          f"deals + lots: {len(found)} | lots (page only): {len(lot_watch)} | "
          f"recommended: {len(recs)} | "
          f"cheap 1sts/RCs: {len(cheap)} | "
          f"alerts sent: {sent}"
          + (" | quiet hours, alerts held" if quiet else "")
          + (f" | eBay API calls: {eb.calls}" if eb else ""))
    print(f"web page: {page_path}")
    if failed:
        print(f"{len(failed)} of {len(groups)} searches failed")
        if len(failed) == len(groups):
            sys.exit(1)  # everything failed (bad keys?) - make the GitHub run show red


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--demo", action="store_true")
    run(ap.parse_args())
