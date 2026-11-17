"""Write the lot spotter's results as one web page (docs/index.html) for GitHub Pages.

Plain HTML + CSS, with a little JavaScript for the sidebar tabs. eBay's display
rules: full title, price and shipping shown separately, eBay's own photo, and a
link to the listing. The helpers at the top are also used by paste.py and check.py.
"""
import html
import os
from urllib.parse import quote_plus

from store import now, parse_time


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


def ago(iso_time):
    """'5 min ago', '3.2 h ago', or '' if unknown."""
    t = parse_time(iso_time)
    if not t:
        return ""
    m = (now() - t).total_seconds() / 60
    if m < 1:
        return "just now"
    return f"{m:.0f} min ago" if m < 90 else f"{m / 60:.1f} h ago" if m < 48 * 60 else f"{m / 1440:.0f} days ago"


def lot_html(it):
    """One lot: a collapsible block. Closed it's one line (score, title, price)."""
    info = it["info"]
    img = (f'<img src="{e(it["image"])}" alt="" loading="lazy">'
           if it.get("image") else '<div class="noimg">no photo</div>')
    level = "good" if it["score"] >= 60 else "rec" if it["score"] >= 40 else ""
    badge = f'<span class="badge {level}">Score {it["score"]}</span>'
    new = '<span class="badge new">NEW</span>' if it.get("new") else ""
    warn = ""
    if not it["shipping_known"]:
        warn += ('<p class="warn">Shipping isn\'t listed in the search results, so the per-card '
                 'price leaves it out. Check the listing.</p>')
    players = (f'<p class="names">Prospects named: <b>{e(" · ".join(it["players"]))}</b></p>'
               if it["players"] else '<p class="names muted">No prospects from your list named.</p>')
    checked = ("Item specifics and description checked." if info["looked_up"] else
               "Title only so far: item specifics and description not checked yet.")
    return f"""
    <details class="item" open>
      <summary>{badge}{new}<span class="sum-title">{e(it["title"])}</span>
        <span class="sum-hint muted">Collapse</span>
        <span class="sum-price">{money(it["price"])}</span></summary>
      <article class="card{" auction" if it["buying"] == "AUCTION" else ""}">
        <div class="photo">{img}</div>
        <div class="info">
          <div class="top">{badge}{new}<span class="when">{e(it["when"])}</span></div>
          <h3>{e(it["title"])}</h3>
          <dl class="stats">
            <div><dt>{"Current bid" if it["buying"] == "AUCTION" else "Price"}</dt><dd>{money(it["price"])}</dd></div>
            <div><dt>Shipping</dt><dd>{shipping_text(it)}</dd></div>
            <div><dt>Cards</dt><dd>{info["count"] or "?"}</dd></div>
            <div><dt>Per card</dt><dd class="{"good" if (info["per_card"] or 99) <= 1 else ""}">{money(info["per_card"]) if info["per_card"] is not None else "?"}</dd></div>
          </dl>{warn}
          {players}
          <p class="names muted">Score: {e(" · ".join(it["reasons"]))}</p>
          <p class="names muted">Found by: <code>{e(it["search"])}</code> · first seen {e(ago(it["first_seen"]))}.
          {checked} Check the photos: lots often hold cheaper cards than the title suggests.</p>
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

/* ---- left sidebar: groups, each a dropdown of section tabs ---- */
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
         font-weight:600; color:var(--text); white-space:nowrap; }
.badge.good { background:var(--good-bg); border-color:transparent; color:var(--good); }
.badge.rec { color:var(--accent); }
.badge.new { background:var(--warn-bg); border-color:transparent; color:var(--warn); }
.intro { margin:-4px 0 12px; font-size:14px; }
.auction .when { color:var(--warn); font-weight:600; }
h3 { font-size:15px; margin:8px 0; overflow-wrap:anywhere; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:8px; margin:0 0 10px; }
.stats div { background:var(--bg); border-radius:8px; padding:6px 10px; }
dt { font-size:12px; color:var(--muted); }
dd { margin:0; font-weight:600; font-variant-numeric:tabular-nums; }
dd.good { color:var(--good); }
.names { font-size:13px; margin:0 0 10px; }
.warn { font-size:13px; margin:0 0 10px; background:var(--warn-bg); color:var(--warn);
        padding:6px 10px; border-radius:8px; }
a { color:var(--accent); }
code { font-size:12px; overflow-wrap:anywhere; }
table.searches { width:100%; border-collapse:collapse; font-size:13px; margin:0 0 10px;
                 background:var(--panel); border:1px solid var(--line); border-radius:12px; }
table.searches th, table.searches td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }
table.searches th { color:var(--muted); font-weight:600; font-size:12px; }
table.searches td.n { font-variant-numeric:tabular-nums; white-space:nowrap; }
.table-wrap { overflow-x:auto; }
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


# Tabs: show one section at a time. The open tab is kept in the address (#new)
# and remembered in this browser, so it survives the auto-refresh.
# Sections are named "tab-new" (not "new") so the browser doesn't jump down the page
# to them. Without JavaScript, every section shows on one long page.
TABS_JS = """
(function () {
  var links = document.querySelectorAll('[data-tab]');
  var sections = document.querySelectorAll('section.tab');
  function exists(id) { return id && document.getElementById('tab-' + id); }
  function show(id) {
    sections.forEach(function (s) { s.hidden = (s.dataset.tabId !== id); });
    links.forEach(function (a) { a.classList.toggle('active', a.dataset.tab === id); });
    try { localStorage.setItem('lot-spotter-tab', id); } catch (e) {}
  }
  links.forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      show(a.dataset.tab);
      history.replaceState(null, '', '#' + a.dataset.tab);
      window.scrollTo(0, 0);
    });
  });
  // Which tab to open: the address (#...), else the last one used, else the first one.
  var start = location.hash.slice(1), saved = null;
  try { saved = localStorage.getItem('lot-spotter-tab'); } catch (e) {}
  if (!exists(start)) start = saved;
  if (!exists(start)) start = sections[0].dataset.tabId;
  show(start);
  // Expand all / Collapse all: every section and listing on the page.
  function setAll(open) { document.querySelectorAll('main details').forEach(function (d) { d.open = open; }); }
  document.getElementById('expand-all').addEventListener('click', function () { setAll(true); });
  document.getElementById('collapse-all').addEventListener('click', function () { setAll(false); });
})();
"""

GROUP_NAMES = {"every_scan": "every scan", "my_searches": "my searches",
               "every_30_min": "every 30 min", "every_2_hours": "every 2 hours",
               "teams": "team (auto)", "players": "players (auto)"}


def searches_html(rows, cfg):
    """The Searches tab: what each search found last time, and how to change them."""
    body = "".join(
        f'<tr><td><code>{e(r["q"])}</code></td><td>{e(GROUP_NAMES.get(r["group"], r["group"]))}</td>'
        f'<td class="n">{e(ago(r["last"]) or "not yet")}</td>'
        f'<td class="n">{e(r["found"] or "-")}</td><td class="n">{e(r["kept"] or "-")}</td></tr>'
        for r in rows)
    repo = cfg["spotter"].get("repo")
    edit = (f'<a href="https://github.com/{e(repo)}/edit/main/searches.yaml" target="_blank" '
            f'rel="noopener">Edit your searches on GitHub</a> (sign in, change the list, then '
            f'"Commit changes"; the next scan uses it).' if repo else
            "Edit searches.yaml to change them.")
    return f"""
      <p class="intro">{edit} Spaces mean AND; <code>(a, b)</code> means either one.
      Every search looks at newly listed Buy It Now lots and auctions ending in the next
      {cfg["spotter"]["auction_hours"]} hours.</p>
      <div class="table-wrap"><table class="searches">
        <tr><th>Search</th><th>How often</th><th>Last run</th><th>eBay results</th><th>Lots kept</th></tr>
        {body}
      </table></div>"""


def build(path, lots, search_rows, cfg, updated, tracked, demo=False):
    """lots = scored lot dicts from main.py, best score first."""
    S = cfg["spotter"]
    cap = S["max_per_tab"]
    day_ago = now().timestamp() - 24 * 3600
    newest = sorted([x for x in lots if parse_time(x["first_seen"]).timestamp() >= day_ago],
                    key=lambda x: x["first_seen"], reverse=True)
    ending = sorted([x for x in lots if x["buying"] == "AUCTION"], key=lambda x: x["end_time"])
    cheap = sorted([x for x in lots if x["info"]["per_card"] is not None
                    and x["info"]["per_card"] <= 1.00],
                   key=lambda x: (-x["score"], x["info"]["per_card"]))

    # Every section: (tab id, sidebar group, title, items, message when empty, intro text)
    sections = [
        ("top", "Lots", "Top lots", lots[:cap],
         "No lots scored high enough yet.",
         f"Every lot found, best score first (0-100). Points come from top prospects named, "
         f"1st Bowman / auto / numbered cards, price per card, and how fresh the listing is. "
         f"New lots scoring {S['alert_min_score']}+ send a phone alert."),
        ("new", "Lots", "New (last 24 h)", newest[:cap],
         "Nothing new in the last 24 hours.",
         "Lots first seen in the last 24 hours, newest first: the ones other buyers may not have seen yet."),
        ("ending", "Lots", "Auctions ending soon", ending[:cap],
         "No auctions ending soon.",
         f"Auctions ending in the next {S['auction_hours']} hours, soonest first. "
         "The current bid will still rise."),
        ("cheap", "Lots", "$1 a card or less", cheap[:cap],
         "No lots at $1 a card or less right now.",
         "Price + shipping divided by the number of cards (when the listing says how many)."),
    ]

    def section_html(sid, group, title, items, empty_msg, intro):
        body = "".join(lot_html(x) for x in items) or f'<p class="empty">{empty_msg}</p>'
        return f"""
  <section class="tab" id="tab-{sid}" data-tab-id="{sid}" data-count="{len(items)}">
    <details class="sec" open>
      <summary><h2>{title} ({len(items)})</h2></summary>
      <p class="muted intro">{intro}</p>
      {body}
    </details>
  </section>"""

    links = "".join(f'<a href="#{sid}" data-tab="{sid}">{title}<span class="count">{len(items)}</span></a>'
                    for sid, _, title, items, _, _ in sections)
    links_settings = (f'<a href="#searches" data-tab="searches">Searches'
                      f'<span class="count">{len(search_rows)}</span></a>')
    demo_note = ('<p class="demo">Demo page: these are fake listings, so the eBay links '
                 'go nowhere.</p>') if demo else ""
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600"><!-- reload every 10 min to pick up the newest scan -->
<title>Lot Spotter</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
  <nav class="side" aria-label="Sections">
    <p class="title">Lot Spotter</p>
    <details class="group" open><summary>Lots</summary>{links}</details>
    <details class="group" open><summary>Settings</summary>{links_settings}</details>
    <div class="tools">
      <button type="button" id="expand-all">Expand all</button>
      <button type="button" id="collapse-all">Collapse all</button>
    </div>
  </nav>
  <main>
    <header>
      <h1>Lot Spotter</h1>
      <div class="muted">Baseball card lots on eBay, scored for top prospects · updated {e(updated)}</div>
      <div class="summary">
        <span><b>{tracked}</b> lots tracked</span>
        <span><b>{len(lots)}</b> scored {S["page_min_score"]}+</span>
        <span><b>{len(newest)}</b> new today</span>
      </div>
    </header>
    {demo_note}
    {"".join(section_html(*s) for s in sections)}
    <section class="tab" id="tab-searches" data-tab-id="searches" data-count="{len(search_rows)}">
      <details class="sec" open>
        <summary><h2>Searches ({len(search_rows)})</h2></summary>
        {searches_html(search_rows, cfg)}
      </details>
    </section>
    <footer>
      Scores are a quick guide, not a price check: eBay doesn't share sold prices through its
      free API. Before buying, look at the photos (which cards are really in the lot, condition,
      fakes), the seller's feedback, and recent sold prices yourself.
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
