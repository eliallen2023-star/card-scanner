"""Write the scan results as a single web page (docs/index.html) for GitHub Pages.

Plain HTML + CSS, no JavaScript. Every listing gets a "View on eBay" button plus
links to look up sold prices yourself (eBay sold items, 130point, PSA) - clicking
those by hand is fine; we never scrape them.
"""
import html
import os
from urllib.parse import quote_plus


def search_words(card):
    """The words to type into a sold-price search for this card, e.g.
    'jesus made 2025 bowman chrome 1st auto refractor /499'."""
    words = [card.player,
             card.year if card.year != "?" else "",
             card.product if card.product != "?" else "",
             "1st" if card.first else "",
             "auto" if card.auto else "",
             card.parallel if card.parallel != "base" else "",
             card.serial,
             card.grade if card.grade != "raw" else ""]
    return " ".join(w for w in words if w)


def card_label(card):
    """A readable card name, e.g. 'Eli Willits 2025 Bowman Chrome 1st Gold Refractor /50 PSA 10'."""
    parts = [card.player.title(),
             card.year if card.year != "?" else "",
             card.product.title() if card.product != "?" else "",
             "1st" if card.first else "",
             "Auto" if card.auto else "",
             card.parallel.title() if card.parallel != "base" else "",
             card.serial,
             card.grade if card.grade != "raw" else ""]     # grade is already "PSA 10"
    return " ".join(p for p in parts if p)


def lookup_links(card):
    """(label, url) pairs for checking sold prices by hand."""
    q = quote_plus(search_words(card))
    return [
        ("eBay sold", f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1"),
        ("130point", "https://130point.com/sales/"),
        ("PSA prices", "https://www.psacard.com/auctionprices"),
    ]


def e(text):
    """Escape text so a listing title can't break (or inject into) the page."""
    return html.escape(str(text), quote=True)


def money(x):
    return f"${x:,.2f}" if x is not None else "-"


def shipping_text(it):
    """eBay's display rules: show shipping separately from the price."""
    if not it.get("shipping_known", True):
        return "not listed"
    return "Free" if it["shipping"] == 0 else money(it["shipping"])


def listing_html(it, card, a):
    # eBay's display rules: full title, price and shipping shown separately,
    # eBay's own photo, and a link to the listing.
    img = (f'<img src="{e(it["image"])}" alt="" loading="lazy">'
           if it.get("image") else '<div class="noimg">no photo</div>')
    known = it.get("shipping_known", True)
    price_cells = f"""
        <div><dt>{"Current bid" if it["buying"] == "AUCTION" else "Price"}</dt><dd>{money(it["price"])}</dd></div>
        <div><dt>Shipping</dt><dd>{shipping_text(it)}</dd></div>"""
    ship_warn = ("" if known else
                 '<p class="warn">Shipping isn\'t listed in search results, so the numbers '
                 'below assume free shipping. Check the listing for the real cost.</p>')
    if a["kind"] == "deal":
        stats = f"""
      <dl class="stats">{price_cells}
        <div><dt>Comp median</dt><dd>{money(a["median"])}</dd></div>
        <div><dt>Est. profit</dt><dd class="good">{money(a["profit"])}</dd></div>
        <div><dt>Comps</dt><dd>{a["comps"]}</dd></div>
      </dl>{ship_warn}"""
        badge = f'<span class="badge good">{a["discount"]:.0%} under</span>'
    elif a["kind"] == "rec":
        sold = f'{money(a["sold_median"])} ({a["sold_n"]})' if a["sold_n"] else "none yet"
        stats = f"""
      <dl class="stats">{price_cells}
        <div><dt>Typical ask ({a["asks"]})</dt><dd>{money(a["ask_median"])}</dd></div>
        <div><dt>Under typical ask</dt><dd class="good">{a["under"]:.0%}</dd></div>
        <div><dt>Est. profit (at ask)</dt><dd class="good">{money(a["ask_profit"])}</dd></div>
        <div><dt>Sold comps</dt><dd>{sold}</dd></div>
      </dl>{ship_warn}
      <p class="names">{e(" · ".join(a["tags"]))}</p>"""
        badge = f'<span class="badge rec">Recommended · score {a["score"]}</span>'
    elif a["kind"] == "cheap":
        ask = (f'{money(a["ask_median"])} ({a["asks"]})' if a["ask_median"] is not None
               else "not enough yet")
        stats = f"""
      <dl class="stats">{price_cells}
        <div><dt>Typical ask</dt><dd>{ask}</dd></div>
      </dl>{ship_warn}
      <p class="names">{e(" · ".join(a["tags"]))}</p>"""
        badge = f'<span class="badge rec">{e(a["headline"])} · score {a["score"]}</span>'
    else:  # a lot, valued card by card (lots.py)
        def qty_text(r):
            # e.g. "100 (3 valued)" when only some copies count toward the value
            return f'{r["qty"]} ({r["valued"]} valued)' if r["valued"] < r["qty"] else str(r["qty"])

        rows = "".join(
            f'<tr><td>{e(card_label(r["card"]))}</td><td>{qty_text(r)}</td>'
            f'<td>{money(r["value"])}</td><td class="muted">{e(r["source"])}</td></tr>'
            for r in a["rows"])
        if a["unnamed"]:
            other = "other players' cards" if a.get("bulk") else "cards not named"
            rows += (f'<tr><td class="muted">+ {a["unnamed"]} {other}</td>'
                     f'<td>{a["unnamed"]}</td><td>$0.00</td><td class="muted">counted as $0</td></tr>')
        table = (f'<table class="lot"><tr><th>Card</th><th>Qty</th><th>Single value</th>'
                 f'<th>Source</th></tr>{rows}</table>')

    if a["kind"] == "lot" and a.get("bulk"):
        # Cheap 1st/RC lot: judged on price per card, not on singles value.
        stats = f"""
      <dl class="stats">{price_cells}
        <div><dt>Cards</dt><dd>{a["count"]}</dd></div>
        <div><dt>Per card</dt><dd class="good">{money(a["per_card"])}</dd></div>
        <div><dt>Singles value (est.)</dt><dd>{money(a["singles"])}</dd></div>
      </dl>{ship_warn}
      <p class="names">Prospects named: {e(", ".join(a["players"]))}</p>
      {table}
      <p class="names muted">Read from the {e(a["source"])}{"" if a["looked_up"] else " (full description not checked yet)"}.
      Check the photos to see which 1st/RC cards are really in it, and their condition.</p>"""
        badge = (f'<span class="badge good">{e(" + ".join(a["tags"]))} lot · '
                 f'{money(a["per_card"])}/card · score {a["score"]}</span>')
    elif a["kind"] == "lot":
        profit_class = "good" if a["profit"] >= 0 else ""
        stats = f"""
      <dl class="stats">{price_cells}
        <div><dt>Singles value</dt><dd>{money(a["singles"])}</dd></div>
        <div><dt>Est. profit (sell singles)</dt><dd class="{profit_class}">{money(a["profit"])}</dd></div>
      </dl>{ship_warn}
      {table}
      <p class="names muted">Cards read from the {e(a["source"])}{"" if a["looked_up"] else " (full description not checked yet)"}.
      Cards worth under $6 count $0 toward profit: selling them one at a time doesn't pay.
      Check the photos: the cards may be a cheaper version than described.</p>"""
        badge = (f'<span class="badge good">lot · {a["discount"]:.0%} under singles</span>'
                 if a["alert"] else
                 f'<span class="badge">lot · {a["discount"]:.0%} under singles · no resale profit</span>')

    lookups = ""
    if a["kind"] != "lot":
        links = " · ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(l)}</a>'
                           for l, u in lookup_links(card))
        lookups = (f'<p class="lookup">Check sold prices: {links}<br>'
                   f'<span class="muted">search for: <code>{e(search_words(card))}</code></span></p>')

    auction = " auction" if it["buying"] == "AUCTION" else ""
    # Each listing is a collapsible <details> block. Closed, it's one line (badge,
    # title, total price); open, it shows the full card.
    return f"""
    <details class="item" open>
      <summary>{badge}<span class="sum-title">{e(it["title"])}</span>
        <span class="sum-hint muted">Collapse</span>
        <span class="sum-price">{money(a["total"])}</span></summary>
      <article class="card{auction}">
        <div class="photo">{img}</div>
        <div class="info">
          <div class="top">{badge}<span class="when">{e(a["when"])}</span></div>
          <h3>{e(it["title"])}</h3>{stats}{lookups}
          <a class="btn" href="{e(it["url"])}" target="_blank" rel="noopener">View on eBay</a>
        </div>
      </article>
    </details>"""


CSS = """
:root { --bg:#f6f7f9; --panel:#fff; --text:#1b1f24; --muted:#5f6b7a; --line:#dde2e8;
        --accent:#0b5fff; --accent-text:#fff; --good:#0a7a3d; --good-bg:#e3f5ea;
        --warn-bg:#fff4d6; --warn:#8a5a00; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111418; --panel:#1a1f25; --text:#e8ecf1; --muted:#9aa6b4; --line:#2c333c;
          --accent:#5b93ff; --accent-text:#0b0f14; --good:#5fd08f; --good-bg:#15301f;
          --warn-bg:#33290f; --warn:#f0c25a; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
.layout { display:grid; grid-template-columns:230px minmax(0,1fr); gap:28px;
          max-width:1180px; margin:0 auto; padding:24px 16px 48px; }
main { min-width:0; }
header h1 { margin:0 0 4px; font-size:26px; }

/* ---- left sidebar: Singles / Lots groups, each a dropdown of section tabs ---- */
.side { position:sticky; top:16px; align-self:start; }
.side .title { font-weight:700; font-size:18px; margin:0 0 12px; }
.group { background:var(--panel); border:1px solid var(--line); border-radius:12px;
         margin-bottom:10px; overflow:hidden; }
.group > summary { cursor:pointer; padding:10px 14px; font-weight:700; font-size:14px;
                   text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.group a { display:flex; justify-content:space-between; gap:8px; padding:8px 14px;
           color:var(--text); text-decoration:none; font-size:14px; border-top:1px solid var(--line); }
.group a:hover { background:var(--bg); }
.group a.active { background:var(--accent); color:var(--accent-text); }
.count { font-variant-numeric:tabular-nums; font-weight:600; opacity:.8; }
.tools { display:flex; gap:8px; margin-top:4px; }
.tools button { flex:1; font:inherit; font-size:13px; padding:7px 8px; border-radius:8px; cursor:pointer;
                background:var(--panel); color:var(--text); border:1px solid var(--line); }
.tools button:hover { background:var(--bg); }

/* ---- collapsible sections and listings ---- */
.sec > summary { cursor:pointer; list-style-position:inside; }
.sum-hint { display:none; font-size:13px; }
.item[open] > summary .sum-hint { display:inline; }
.sec > summary h2 { display:inline; }
.item { margin-bottom:10px; }
.item > summary { cursor:pointer; display:flex; align-items:center; gap:10px; padding:8px 12px;
                  background:var(--panel); border:1px solid var(--line); border-radius:12px; }
.item > summary::-webkit-details-marker { display:none; }
.item > summary::before { content:"▸"; color:var(--muted); }
.item[open] > summary::before { content:"▾"; }
.item[open] > summary { border-bottom-left-radius:0; border-bottom-right-radius:0; border-bottom:none; }
.item[open] > summary .sum-title, .item[open] > summary .badge { display:none; }
.item[open] > .card { border-top-left-radius:0; border-top-right-radius:0; margin-bottom:0; }
.sum-title { flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:14px; }
.item[open] > summary .sum-price { margin-left:auto; }
.sum-price { font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
@media (max-width:820px) {
  .layout { grid-template-columns:1fr; gap:16px; }
  .side { position:static; }
}
.muted { color:var(--muted); }
.summary { display:flex; flex-wrap:wrap; gap:8px 20px; margin:12px 0 4px; color:var(--muted); }
.summary b { color:var(--text); }
.demo { background:var(--warn-bg); color:var(--warn); padding:10px 14px; border-radius:8px; margin:16px 0; }
h2 { font-size:18px; margin:20px 0 12px; }
.card { display:flex; gap:16px; background:var(--panel); border:1px solid var(--line);
        border-radius:12px; padding:14px; margin-bottom:12px; }
.photo { flex:0 0 120px; }
.photo img, .noimg { width:120px; height:160px; object-fit:contain; border-radius:6px; background:var(--bg); }
.noimg { display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:12px; }
.info { flex:1; min-width:0; }
.top { display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:13px; color:var(--muted); }
.badge { background:var(--bg); border:1px solid var(--line); border-radius:999px; padding:2px 10px;
         font-weight:600; color:var(--text); }
.badge.good { background:var(--good-bg); border-color:transparent; color:var(--good); }
.badge.rec { color:var(--accent); }
.intro { margin:-4px 0 12px; font-size:14px; }
.auction .when { color:var(--warn); font-weight:600; }
h3 { font-size:15px; margin:8px 0; overflow-wrap:anywhere; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:8px; margin:0 0 10px; }
.stats div { background:var(--bg); border-radius:8px; padding:6px 10px; }
dt { font-size:12px; color:var(--muted); }
dd { margin:0; font-weight:600; font-variant-numeric:tabular-nums; }
dd.good { color:var(--good); }
.names, .lookup { font-size:13px; margin:0 0 10px; }
.warn { font-size:13px; margin:0 0 10px; background:var(--warn-bg); color:var(--warn);
        padding:6px 10px; border-radius:8px; }
.lookup a { color:var(--accent); }
code { font-size:12px; overflow-wrap:anywhere; }
table.lot { width:100%; border-collapse:collapse; font-size:13px; margin:0 0 10px; }
table.lot th, table.lot td { text-align:left; padding:4px 6px; border-bottom:1px solid var(--line); }
table.lot th { color:var(--muted); font-weight:600; font-size:12px; }
table.lot td:nth-child(2), table.lot td:nth-child(3) { font-variant-numeric:tabular-nums; white-space:nowrap; }
.btn { display:inline-block; background:var(--accent); color:var(--accent-text); text-decoration:none;
       font-weight:600; padding:8px 16px; border-radius:8px; }
.empty { background:var(--panel); border:1px dashed var(--line); border-radius:12px; padding:20px; color:var(--muted); }
footer { margin-top:40px; font-size:13px; color:var(--muted); }
@media (max-width:520px) {
  .card { flex-direction:column; }
  .photo { flex:none; }
  .photo img, .noimg { width:100%; height:200px; }
}
"""


# Tabs: show one section at a time. The open tab is kept in the address (#cheap-lots)
# and remembered in this browser, so it survives the 15-minute auto-refresh.
# Sections are named "tab-cheap-lots" (not "cheap-lots") so the browser doesn't
# jump down the page to them. Without JavaScript, every section shows on one long page.
TABS_JS = """
(function () {
  var links = document.querySelectorAll('[data-tab]');
  var sections = document.querySelectorAll('section.tab');
  function exists(id) { return id && document.getElementById('tab-' + id); }
  function show(id) {
    sections.forEach(function (s) { s.hidden = (s.dataset.tabId !== id); });
    links.forEach(function (a) { a.classList.toggle('active', a.dataset.tab === id); });
    try { localStorage.setItem('card-scanner-tab', id); } catch (e) {}
  }
  links.forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      show(a.dataset.tab);
      history.replaceState(null, '', '#' + a.dataset.tab);
      window.scrollTo(0, 0);
    });
  });
  // Which tab to open: the address (#...), else the last one used, else the first non-empty one.
  var start = location.hash.slice(1), saved = null;
  try { saved = localStorage.getItem('card-scanner-tab'); } catch (e) {}
  if (!exists(start)) start = saved;
  if (!exists(start)) {
    start = sections[0].dataset.tabId;
    for (var i = 0; i < sections.length; i++) {
      if (+sections[i].dataset.count > 0) { start = sections[i].dataset.tabId; break; }
    }
  }
  show(start);
  // Expand all / Collapse all: every section and listing on the page.
  function setAll(open) { document.querySelectorAll('main details').forEach(function (d) { d.open = open; }); }
  document.getElementById('expand-all').addEventListener('click', function () { setAll(true); });
  document.getElementById('collapse-all').addEventListener('click', function () { setAll(false); });
})();
"""


def build(path, found, updated, listings, comps, demo=False):
    """found = list of (listing, card, result_dict) from main.py."""
    deals = [x for x in found if x[2]["kind"] == "deal"]
    recs = [x for x in found if x[2]["kind"] == "rec"]
    cheap = [x for x in found if x[2]["kind"] == "cheap"]
    bulk = [x for x in found if x[2]["kind"] == "lot" and x[2].get("bulk")]
    lots = [x for x in found if x[2]["kind"] == "lot" and not x[2].get("bulk")]

    # Every section: (tab id, sidebar group, title, items, message when empty, intro text)
    sections = [
        ("deals", "Singles", "Deals", deals,
         "No deals right now. Deals need at least 3 recorded sales of the exact same card, "
         "so expect a quiet first few weeks while comps build up.",
         "Priced at least 30% under recent sales of the exact same card, with $10+ estimated "
         "profit after fees and shipping. These send phone alerts."),
        ("recommended", "Singles", "Recommended", recs,
         "Nothing yet. Picks need at least 3 other Buy It Now listings of the same card, "
         "which takes a few days of scanning.",
         "Priced well under what other sellers are asking for the exact same card, ranked by "
         "how desirable the card is. Asking prices run higher than sale prices, so check sold "
         "prices before you buy. No phone alerts."),
        ("cheap-singles", "Singles", "Cheap 1st Bowman &amp; rookies", cheap,
         "No cheap 1st Bowman or rookie cards right now.",
         "Buy It Now, up to $6 including shipping. All 1st Bowman cards come first, then "
         "rookies; each group is ranked by prospect rank and card type. Not checked against "
         "comps: these are cheap cards to look at or hold, not quick flips. One listing per "
         "card: the cheapest. Sellers often call prospect cards \"RC\" when they aren't "
         "official rookie cards."),
        ("cheap-lots", "Lots", "Cheap 1st &amp; RC lots", bulk,
         "No cheap 1st/RC lots right now.",
         "Lots that cost about $1 or less per card (price + shipping), name at least one of "
         "your prospects (the other cards can be anyone), and mention 1st or RC cards. Ranked "
         "by 1sts first, then RCs, then how many prospects and how highly ranked. No phone alerts."),
        ("lots-vs-singles", "Lots", "Lots vs. singles", lots,
         "No lots priced well under their singles right now.",
         "Each card in the lot is priced like a single (sold comps first, then asking prices), "
         "using the seller's description. Shown when the lot costs 30%+ less than its singles; "
         "a green badge means reselling the singles should also make $10+, and only those "
         "send phone alerts."),
    ]

    def section_html(sid, group, title, items, empty_msg, intro):
        body = "".join(listing_html(*x) for x in items) or f'<p class="empty">{empty_msg}</p>'
        return f"""
  <section class="tab" id="tab-{sid}" data-tab-id="{sid}" data-count="{len(items)}">
    <details class="sec" open>
      <summary><h2>{title} ({len(items)})</h2></summary>
      <p class="muted intro">{intro}</p>
      {body}
    </details>
  </section>"""

    def group_html(group):
        links = "".join(f'<a href="#{sid}" data-tab="{sid}">{title}<span class="count">{len(items)}</span></a>'
                        for sid, g, title, items, _, _ in sections if g == group)
        return f'<details class="group" open><summary>{group}</summary>{links}</details>'

    demo_note = ('<p class="demo">Demo page: these are fake listings, so the eBay links '
                 'go nowhere.</p>') if demo else ""
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="900"><!-- reload every 15 min to pick up the newest scan -->
<title>Card Scanner</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
  <nav class="side" aria-label="Sections">
    <p class="title">Card Scanner</p>
    {group_html("Singles")}
    {group_html("Lots")}
    <div class="tools">
      <button type="button" id="expand-all">Expand all</button>
      <button type="button" id="collapse-all">Collapse all</button>
    </div>
  </nav>
  <main>
    <header>
      <h1>Card Scanner</h1>
      <div class="muted">Underpriced top-prospect cards on eBay · updated {e(updated)}</div>
      <div class="summary">
        <span><b>{listings}</b> listings checked</span>
        <span><b>{comps}</b> sales recorded as comps</span>
      </div>
    </header>
    {demo_note}
    {"".join(section_html(*s) for s in sections)}
    <footer>
      Prices are estimates from recent auction results and asking prices. Before buying,
      check the photos (condition, centering, fakes), the seller's feedback, and recent sold
      prices yourself. Auction prices will still rise before they end.
    </footer>
  </main>
</div>
<script>{TABS_JS}</script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
