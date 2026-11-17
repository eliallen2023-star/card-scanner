"""Lot Spotter: find baseball card lots on eBay, score them, and alert you to new good ones.

  python main.py            # real run (needs EBAY_CLIENT_ID, EBAY_CLIENT_SECRET; NTFY_TOPIC optional)
  python main.py --dry-run  # real eBay search, but print alerts instead of sending them
  python main.py --demo     # fake data, no internet, no keys - just to see it work
  python main.py --budget   # how many eBay API calls a day your searches.yaml uses

One run:
  1. runs the searches in searches.yaml that are due (Buy It Now newly listed +
     auctions ending soon), and remembers every lot it finds
  2. looks up item specifics + description for the best-looking NEW lots
     (real shipping, Sport, players named, card count)
  3. scores every lot 0-100 (score.py): top prospects named, 1st/auto/numbered,
     price per card, how fresh it is
  4. sends a phone alert for new lots over your alert score, with the eBay link
  5. writes the web page: real run -> docs/index.html, dry run -> docs/preview.html,
     demo -> docs/demo.html
"""
import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

import feedback
import notify
import score
import webpage
from parse import Parser, norm
from store import Store, iso, parse_time, now

HERE = os.path.dirname(os.path.abspath(__file__))

# How often each group in searches.yaml runs (minutes), and whether it also
# searches the Singles category (where many small lots are listed).
GROUPS = {"every_scan": (0, True), "my_searches": (30, True),
          "every_30_min": (30, False), "every_2_hours": (120, False),
          "teams": (120, False), "players": (120, False),
          "learned": (30, False)}     # built from your Good / Medium / Bad ratings


def load(name):
    # encoding="utf-8" so accented names (Jesús) read correctly on Windows too
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def in_quiet_hours(cfg):
    a = cfg["alerts"]
    h = datetime.now(ZoneInfo(a["timezone"])).hour
    s, e = a["quiet_start"], a["quiet_end"]
    return (h >= s or h < e) if s > e else (s <= h < e)


def minutes_since(store, key):
    t = parse_time(store.get_meta(key))
    return (now() - t).total_seconds() / 60 if t else float("inf")


def make_query(terms, extra=""):
    """eBay search text. Several names in parentheses means 'any of these':
    (Jesus Made, Leo De Vries) finds listings naming either."""
    q = terms[0] if len(terms) == 1 else "(" + ", ".join(terms) + ")"
    return f"{extra} {q}".strip()


def pack(items, extra, per_search=4, max_len=100):
    """Pack names into as few OR searches as possible: up to `per_search` per search,
    under eBay's 100-character limit. Each item is a list of spellings kept together."""
    groups, cur, n = [], [], 0
    for terms in items:
        if cur and (n + 1 > per_search or len(make_query(cur + terms, extra)) > max_len):
            groups.append(cur)
            cur, n = [], 0
        cur += terms
        n += 1
    if cur:
        groups.append(cur)
    return [make_query(g, extra) for g in groups]


def all_searches(searches, prospects, cfg, learned=()):
    """Every search as (group, query). Team and player searches are built from
    prospects.yaml; `learned` searches come from your ratings (feedback.py)."""
    out = []
    for group in ("every_scan", "my_searches", "every_30_min", "every_2_hours"):
        for q in searches.get(group) or []:
            q = str(q).strip()
            if len(q) > 100:
                print(f"  skipped (over eBay's 100-character limit): {q}")
            elif q:
                out.append((group, q))
    if searches.get("team_searches"):
        # each team once, best-ranked prospects' teams first: "(Brewers, Athletics, ...) bowman lot"
        ordered = sorted(prospects, key=lambda p: p["rank"])
        teams = list(dict.fromkeys(p["team"] for p in ordered if p.get("team")))
        out += [("teams", f"{q} bowman lot") for q in pack([[t] for t in teams], "", 4, 89)]
    if searches.get("player_searches"):
        top = sorted(prospects, key=lambda p: p["rank"])[: cfg["spotter"]["player_search_top"]]
        names = [[p["name"]] + list(p.get("aliases") or []) for p in top]
        out += [("players", q) for q in pack(names, "lot", 4, 100)]
    out += [("learned", q) for q in learned]
    return out


def save_rating(store, parser, item_id, label):
    """Save one rating with what the lot was 'made of'. Only lots the spotter found
    count, so a made-up rating for some other item is ignored. Returns True if saved."""
    row = store.spotted_row(item_id)
    if not row or label not in feedback.LABELS:
        return False
    info = score.read_lot(row, store.get_lot_details(item_id), parser)
    store.save_rating(item_id, label, iso(now()), row["title"], row["search"],
                      feedback.tokens(info["text"], info["players"]))
    return True


def read_ratings(store, parser, topic):
    """New ratings from your ntfy ratings topic. Returns how many were saved."""
    try:
        new, last = feedback.fetch(topic, store.get_meta("ratings_since"))
    except Exception as e:
        print(f"  couldn't read ratings: {e}")
        return 0
    saved = sum(save_rating(store, parser, item_id, label) for item_id, label, _ in new)
    if last:
        store.set_meta("ratings_since", last)
    return saved


def learn(store, searches, prospects, cfg):
    """What your ratings say you like, and the new searches that come from it."""
    existing = [q for _, q in all_searches(searches, prospects, cfg)]
    return feedback.learn(store.all_ratings(), existing, cfg["spotter"]["learned_searches"])


def budget(cfg, searches, prospects):
    """Worst-case eBay API calls per day for the current settings (eBay allows 5,000)."""
    S, A = cfg["spotter"], cfg["alerts"]
    quiet = (A["quiet_end"] - A["quiet_start"]) % 24
    day_runs = (24 - quiet) * 60 / S["every_minutes"]
    night_runs = quiet * 60 / S["night_every_minutes"]
    lines, total = [], 0
    for group, (every, singles_too) in GROUPS.items():
        qs = [q for g, q in all_searches(searches, prospects, cfg) if g == group]
        if not qs:
            continue
        runs = day_runs + night_runs if every <= S["every_minutes"] else \
            (24 - quiet) * 60 / every + night_runs * min(1, S["night_every_minutes"] / every)
        calls = len(qs) * 2 * (2 if singles_too else 1) * runs
        total += calls
        lines.append(f"  {group:14} {len(qs):2} searches x 2 (BIN + auctions)"
                     f"{' x 2 categories' if singles_too else ''} x {runs:.0f} runs = {calls:,.0f}")
    n = S["learned_searches"]                   # learned from your ratings, up to this many
    runs = (24 - quiet) * 2 + night_runs
    total += n * 2 * runs
    lines.append(f"  learned        up to {n} searches x 2 (BIN + auctions) x {runs:.0f} runs = {n * 2 * runs:,.0f}")
    lookups = S["detail_lookups_per_run"] * (day_runs + night_runs)
    total += lookups
    lines.append(f"  detail lookups  up to {S['detail_lookups_per_run']} x {day_runs + night_runs:.0f} runs"
                 f" = {lookups:,.0f}")
    return total, lines


def when_text(it):
    """'Buy It Now, listed 12 min ago' or 'Auction, 0 bids, ends in 1h 20m'."""
    def ago(minutes):
        return f"{minutes:.0f} min" if minutes < 90 else f"{minutes / 60:.1f} h"
    if it["buying"] == "AUCTION":
        ends = parse_time(it["end_time"])
        left = (ends - now()).total_seconds() / 60 if ends else 0
        return f"Auction, {it['bid_count']} bids, ends in {ago(left)} (price will rise)"
    listed = parse_time(it.get("listed") or it.get("first_seen"))
    return "Buy It Now" + (f", listed {ago((now() - listed).total_seconds() / 60)} ago"
                           if listed else "")


def run(args):
    cfg, searches = load("config.yaml"), load("searches.yaml") or {}
    prospects = load("prospects.yaml")["prospects"]
    S = cfg["spotter"]
    if args.budget:
        total, lines = budget(cfg, searches, prospects)
        print("Worst-case eBay API calls per day:\n" + "\n".join(lines))
        print(f"  TOTAL about {total:,.0f} of eBay's 5,000"
              + ("  <-- TOO MANY: remove some searches" if total > 4800 else "  (OK)"))
        return

    parser = Parser(prospects, cfg["exclude_words"])
    ranks = {norm(p["name"]): p["rank"] for p in prospects}   # "jesus made" -> 1
    testing = args.dry_run or args.demo   # testing = never send pushes or mark anything "alerted"

    db_path = os.path.join(HERE, "data", "demo.db" if args.demo else "cards.db")
    if args.demo and os.path.exists(db_path):
        os.remove(db_path)  # the demo starts from scratch every time
    store = Store(db_path)

    eb = None
    if args.demo:
        from demo import fake_search, fake_details
        search, get_details = fake_search, fake_details
    else:
        from ebay import Ebay
        client_id = os.environ.get("EBAY_CLIENT_ID")
        client_secret = os.environ.get("EBAY_CLIENT_SECRET")
        if not client_id or not client_secret:
            sys.exit("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET aren't set. "
                     "See README step 2 for how to set them.")
        eb = Ebay(client_id, client_secret, str(S["ship_to_zip"]))
        search, get_details = eb.search, eb.item_details

    # ---- 0. Your ratings: read the new ones, and learn what you like ----
    fb_topic = None if args.demo else os.environ.get("NTFY_FEEDBACK_TOPIC")
    rated = read_ratings(store, parser, fb_topic) if fb_topic else 0
    learned = learn(store, searches, prospects, cfg)

    # ---- 1. Run the searches that are due ----
    quiet = in_quiet_hours(cfg) and not args.demo
    # The very first scan finds everything already listed: none of that is "new", so no alerts.
    first_run = store.get_meta("last_scan") is None and not args.demo
    night_skip = quiet and minutes_since(store, "last_scan") < S["night_every_minutes"] - 3
    new_ids, failed, ran = set(), [], []
    if night_skip:
        print("Quiet hours: searched less than an hour ago, so this run only rebuilds the page.")
    else:
        store.set_meta("last_scan", iso(now()))
        for group, q in all_searches(searches, prospects, cfg, learned["queries"]):
            every, singles_too = GROUPS[group]
            every = every or S["every_minutes"]   # "every scan" still waits ~10 min, in case
                                                  # two scans start close together
            key = f"last:{group}:{q}"
            # due? (a few minutes' slack, because the timer doesn't fire exactly on time)
            if not args.demo and minutes_since(store, key) < every - 3:
                continue
            cats = [S["lots_category"]] + ([S["singles_category"]] if singles_too else [])
            found = kept = 0
            try:
                for cat in cats:
                    results = search(q, cat, "FIXED_PRICE", "newlyListed",
                                     S["results_per_search"], S["max_price"])
                    results += search(q, cat, "AUCTION", "endingSoonest",
                                      S["results_per_search"], S["max_price"],
                                      ends_within_hours=S["auction_hours"])
                    found += len(results)
                    for it in results:
                        # in the Singles category, keep only listings that look like lots
                        if cat == S["singles_category"] and not score.looks_like_lot(it["title"]):
                            continue
                        kept += 1
                        if not it["shipping_known"]:
                            cached = store.cached_shipping(it["item_id"])
                            if cached is not None:
                                it["shipping"], it["shipping_known"] = cached, True
                        if store.upsert_spotted(it, q):
                            new_ids.add(it["item_id"])
            except Exception as e:
                # One bad search shouldn't throw away the whole run - note it and move on.
                print(f"  search failed: {q}: {e}")
                failed.append(q)
                continue
            store.set_meta(key, iso(now()))
            store.set_meta(f"stats:{q}", f"{found}|{kept}")
            ran.append(q)

    # ---- 2. Look up details for the best-looking new lots ----
    active = store.active_spotted(S["bin_show_hours"])
    todo = []
    for it in active:
        if store.get_lot_details(it["item_id"]) is None:
            info = score.read_lot(it, None, parser)
            if not score.skip_reason(it, info, cfg, parser.exclude):
                todo.append((score.score_lot(it, info, ranks)[0], it))
    todo.sort(key=lambda x: -x[0])                     # most promising first
    lookups = 0
    for _, it in todo[: S["detail_lookups_per_run"]]:
        try:
            details = get_details(it["item_id"])
        except Exception as e:
            print(f"  lookup failed for {it['item_id']}: {e}")
            continue
        lookups += 1
        store.save_lot_details(it["item_id"], details)   # never look this one up again
        if details.get("shipping") is not None and not it["shipping_known"]:
            store.save_shipping(it["item_id"], details["shipping"])
            store.set_shipping(it["item_id"], details["shipping"])
            it["shipping"], it["shipping_known"] = details["shipping"], True

    if args.demo:
        # pretend you rated some demo lots, so the demo page shows what learning looks like
        from demo import DEMO_RATINGS
        for idx, label in DEMO_RATINGS:
            save_rating(store, parser, f"v1|demo{idx}|0", label)
        learned = learn(store, searches, prospects, cfg)

    # ---- 3. Score every lot that's still around ----
    my_ratings = {r["item_id"]: r["label"] for r in store.all_ratings()}
    shown = []
    for it in active:
        details = store.get_lot_details(it["item_id"])
        info = score.read_lot(it, details, parser)
        if score.skip_reason(it, info, cfg, parser.exclude):
            continue
        it["rating"] = my_ratings.get(it["item_id"])
        if it["rating"] == "bad":
            continue                                   # you said it's not for you: hide it
        s, reasons = score.score_lot(it, info, ranks)
        store.set_score(it["item_id"], s, reasons)
        if s >= S["page_min_score"]:
            it.update(score=s, reasons=reasons, info=info, when=when_text(it),
                      new=it["item_id"] in new_ids)
            it["players"] = [f"#{ranks.get(p, '?')} {p.title()}"
                             for p in sorted(info["players"], key=lambda p: ranks.get(p, 99))]
            shown.append(it)
    shown.sort(key=lambda x: -x["score"])

    # ---- 4. Phone alerts for NEW good lots (Sport checked first) ----
    # Only lots first seen in the last 12 hours: the point is to be early. (Lots found
    # overnight during quiet hours are still new enough for the morning.)
    sent = 0
    if not quiet and not first_run:
        for it in shown:
            if sent >= cfg["alerts"]["max_per_run"]:
                break
            first_seen = parse_time(it["first_seen"])
            if it["score"] < S["alert_min_score"] or not it["info"]["looked_up"] \
                    or store.already_alerted(it["item_id"]) \
                    or (now() - first_seen).total_seconds() > 12 * 3600:
                continue
            info = it["info"]
            size = (f"{info['count']} cards, ${info['per_card']:.2f}/card" if info["count"]
                    else "card count unknown")
            ship = f"+ ${it['shipping']:.2f} ship" if it["shipping_known"] else "+ ship?"
            title = f"Lot score {it['score']}: ${it['price']:.2f} {ship} ({size})"
            body = (f"{it['title']}\n"
                    + (f"Prospects: {', '.join(it['players'][:4])}\n" if it["players"] else "")
                    + f"{it['when']}")
            notify.send(os.environ.get("NTFY_TOPIC"), title, body, it["url"], it["image"],
                        dry_run=testing, feedback_topic=os.environ.get("NTFY_FEEDBACK_TOPIC"),
                        item_id=it["item_id"])
            if not testing:
                store.mark_alerted(it["item_id"], info["total"], None, None)
            sent += 1

    store.prune()
    store.commit()

    # ---- 5. Write the web page ----
    page = "demo.html" if args.demo else "preview.html" if args.dry_run else "index.html"
    page_path = os.path.join(HERE, "docs", page)
    updated = datetime.now(ZoneInfo(cfg["alerts"]["timezone"])).strftime("%b %d, %Y %I:%M %p %Z")
    search_rows = []
    by_search = feedback.search_ratings(store.all_ratings())
    for group, q in all_searches(searches, prospects, cfg, learned["queries"]):
        stats = (store.get_meta(f"stats:{q}") or "|").split("|")
        search_rows.append({"group": group, "q": q, "every": GROUPS[group][0] or S["every_minutes"],
                            "last": store.get_meta(f"last:{group}:{q}"),
                            "found": stats[0], "kept": stats[1],
                            "ratings": by_search.get(q)})
    # The page's Good / Medium / Bad buttons post to your ratings topic. A demo page
    # gets buttons too, but they only show how it works (nothing is sent).
    webpage.build(page_path, shown, search_rows, cfg, updated=updated,
                  tracked=len(active), demo=args.demo, learned=learned,
                  feedback_topic=os.environ.get("NTFY_FEEDBACK_TOPIC") if not args.demo else "demo")

    print(f"\nsearches run: {len(ran)} | lots tracked: {len(active)} | new: {len(new_ids)} | "
          f"ratings read: {rated} (total {learned['rated']}) | learned searches: {len(learned['queries'])} | "
          f"detail lookups: {lookups} | on the page: {len(shown)} | alerts sent: {sent}"
          + (" | quiet hours, alerts held" if quiet else "")
          + (" | first scan: learning what's already listed, no alerts" if first_run else "")
          + (f" | eBay API calls: {eb.calls}" if eb else ""))
    print(f"web page: {page_path}")
    if failed:
        print(f"{len(failed)} of {len(failed) + len(ran)} searches failed")
        if not ran:
            sys.exit(1)  # everything failed (bad keys?) - make the GitHub run show red


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--budget", action="store_true")
    run(ap.parse_args())
