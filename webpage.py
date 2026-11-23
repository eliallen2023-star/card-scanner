"""Write the lot spotter's results as one web page (docs/index.html) for GitHub Pages.

Plain HTML + CSS, with a little JavaScript for the sidebar tabs. eBay's display
rules: full title, price and shipping shown separately, eBay's own photo, and a
link to the listing. The helpers at the top are also used by paste.py and check.py.
"""
import html
import os
import re
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


def research_url(words):
    """eBay's Product Research (in Seller Hub): up to 3 years of sold prices. You open it
    yourself while signed in; eBay only lets accounts with at least one sale use it."""
    return ("https://www.ebay.com/sh/research?marketplace=EBAY-US&keywords="
            f"{quote_plus(words)}&tabName=SOLD")


def sold_links(words):
    """(label, url) pairs for checking sold prices BY HAND (just links, nothing is fetched)."""
    q = quote_plus(words)
    return [
        ("eBay sold", f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1"),
        ("130point", "https://130point.com/sales/"),
        ("Product Research", research_url(words)),
    ]


def lookup_links(card):
    """(label, url) pairs for checking a single card's sold prices by hand."""
    return sold_links(search_words(card)) + [("PSA prices", "https://www.psacard.com/auctionprices")]


def lot_words(it):
    """What to search sold prices for: the top prospect + year + 'lot', e.g.
    'jesus made 2025 bowman lot'. Without a prospect, the start of the title."""
    year = re.search(r"\b(19|20)\d\d\b", it["title"])
    if it.get("players"):
        name = re.sub(r"^(#\d+|Riser)\s+", "", it["players"][0])  # "#1 Jesus Made" -> "Jesus Made"
        return " ".join(w for w in (name, year.group(0) if year else "", "bowman lot") if w)
    return " ".join(it["title"].split()[:6])


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


def level(score):
    """Badge color: 70+ green, 50+ blue, 30+ amber, else gray."""
    return "s-hi" if score >= 70 else "s-good" if score >= 50 else "s-mid" if score >= 30 else "s-low"


def lot_html(it):
    """One lot. Two layouts in one block (the page shows one, see the List/Cards toggle):
    the full card, and a compact one-line row. data-* values are for sorting and filtering."""
    info = it["info"]
    img = (f'<button type="button" class="zoom" title="Click to enlarge">'
           f'<img src="{e(it["image"])}" alt="" loading="lazy"></button>'
           if it.get("image") else '<div class="noimg">no photo</div>')
    thumb = (f'<img class="thumb" src="{e(it["image"])}" alt="" loading="lazy">'
             if it.get("image") else '<span class="thumb noimg"></span>')
    badge = f'<span class="badge {level(it["score"])}">{it["score"]}</span>'
    new = '<span class="badge new">NEW</span>' if it.get("new") else ""
    per = info["per_card"]
    per_text = money(per) if per is not None else "?"
    top = it["players"][0] if it["players"] else "no prospect named"
    seen = parse_time(it["first_seen"])
    warn = ""
    if not it["shipping_known"]:
        warn += ('<p class="warn">Shipping is not listed in the search results, so the per-card '
                 'price leaves it out. Check the listing.</p>')
    players = (f'<p class="names">Prospects named: <b>{e(" · ".join(it["players"]))}</b></p>'
               if it["players"] else '<p class="names muted">No prospects from your list named.</p>')
    checked = ("Item specifics and description checked." if info["looked_up"] else
               "Title only so far: item specifics and description not checked yet.")
    links = " · ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a>'
                       for n, u in sold_links(lot_words(it)))
    ebay = f'<a class="btn" href="{e(it["url"])}" target="_blank" rel="noopener">View on eBay</a>'
    return f"""
    <div class="lot" data-score="{it["score"]}" data-per="{per if per is not None else 9999}"
         data-seen="{seen.timestamp() if seen else 0:.0f}" data-players="{e("|".join(it["players"]))}">
    <div class="row">
      {thumb}{badge}<span class="row-per" title="per card">{per_text}/card</span>
      <span class="row-name">{e(top)}</span>
      <span class="row-title muted">{e(it["title"])}</span>
      <a class="btn small" href="{e(it["url"])}" target="_blank" rel="noopener">eBay</a>
    </div>
    <details class="item" open>
      <summary>{badge}{new}<span class="sum-title">{e(it["title"])}</span>
        <span class="sum-hint muted">Collapse</span>
        <span class="sum-price">{money(it["price"])}</span></summary>
      <article class="card{" auction" if it["buying"] == "AUCTION" else ""}">
        <div class="photo">{img}</div>
        <div class="info">
          <div class="top">{badge}{new}{tags_html(it)}<span class="when">{e(it["when"])}</span></div>
          <h3>{e(it["title"])}</h3>
          <dl class="stats">
            <div><dt>{"Current bid" if it["buying"] == "AUCTION" else "Price"}</dt><dd>{money(it["price"])}</dd></div>
            <div><dt>Shipping</dt><dd>{shipping_text(it)}</dd></div>
            <div><dt>Cards</dt><dd>{info["count"] or "?"}</dd></div>
            <div><dt>Per card</dt><dd class="{"good" if (per or 99) <= 1 else ""}">{per_text}</dd></div>
          </dl>{warn}
          {players}
          <p class="names muted">Score: {e(" · ".join(it["reasons"]))}</p>
          <p class="names">Check sold prices: {links}</p>
          <details class="more"><summary>Found by</summary>
            <p class="names muted"><code>{e(it["search"])}</code> · first seen {e(ago(it["first_seen"]))}.
            {checked} Check the photos: lots often hold cheaper cards than the title suggests.</p>
          </details>
          <div class="actions">{ebay}{rate_html(it)}</div>
        </div>
      </article>
    </details>
    </div>"""


def toolbar_html(items):
    """Sort and filter controls at the top of a lot tab (the JavaScript does the work)."""
    names = sorted({p for x in items for p in x["players"]})
    options = "".join(f'<option value="{e(n)}">{e(n)}</option>' for n in names)
    return f"""
      <div class="toolbar">
        <label>Sort <select class="f-sort">
          <option value="">This tab's order</option><option value="score">Score</option>
          <option value="per">$ per card</option><option value="seen">Newest</option></select></label>
        <label>Min score <input class="f-min" type="number" min="0" max="100" step="5" value="0"></label>
        <label>Prospect <select class="f-player"><option value="">Any</option>{options}</select></label>
        <span class="f-count muted"></span>
      </div>"""


def tags_html(it):
    """Small labels: 1st, Auto, Refractor, Best Offer, Same-card bulk, ..."""
    def cls(t):
        return {"1st": " t-1st", "Auto": " t-auto", "Shiny": " t-ref"}.get(t, "")
    return "".join(f'<span class="tag{cls(t)}">{e(t)}</span>' for t in it.get("tags", []))


def rate_html(it):
    """Good / Medium / Bad buttons. Your saved rating (if any) is highlighted."""
    buttons = ""
    for label, name in (("good", "Good"), ("medium", "Medium"), ("bad", "Bad")):
        chosen = ' class="chosen"' if it.get("rating") == label else ""
        buttons += f'<button type="button" data-label="{label}"{chosen}>{name}</button>'
    return (f'<div class="rate" data-id="{e(it["item_id"])}"><span class="muted">Match for you?</span>'
            f'{buttons}<span class="rate-msg muted"></span></div>')


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
.actions { display:flex; flex-wrap:wrap; align-items:center; gap:10px 16px; }
.rate { display:flex; flex-wrap:wrap; align-items:center; gap:6px; font-size:13px; }
.rate button { font:inherit; font-size:13px; padding:6px 12px; border-radius:8px; cursor:pointer;
               background:var(--panel); color:var(--text); border:1px solid var(--line); }
.rate button:hover { background:var(--bg); }
.rate button.chosen[data-label=good] { background:var(--good-bg); color:var(--good); border-color:var(--good); }
.rate button.chosen[data-label=medium] { background:var(--warn-bg); color:var(--warn); border-color:var(--warn); }
.rate button.chosen[data-label=bad] { background:var(--bg); color:var(--muted); border-color:var(--muted); text-decoration:line-through; }
#pending-note:empty { display:none; }
td.n { text-align:right; white-space:nowrap; }
.good { color:var(--good); font-weight:600; } .bad { color:var(--warn); font-weight:600; }
/* score badges: 70+ green, 50+ blue, 30+ amber, else gray */
.badge.s-hi { background:var(--good-bg); color:var(--good); border-color:var(--good); }
.badge.s-good { color:var(--accent); border-color:var(--accent); }
.badge.s-mid { background:var(--warn-bg); color:var(--warn); border-color:transparent; }
.badge.s-low { color:var(--muted); }
.t-1st { color:var(--accent); border-color:var(--accent); }
.t-auto { color:var(--good); border-color:var(--good); }
.t-ref { color:var(--warn); border-color:var(--warn); }
.more { margin:0 0 10px; font-size:13px; }
.more > summary { cursor:pointer; color:var(--muted); }
.zoom { padding:0; border:0; background:none; cursor:zoom-in; }
#zoom-view { position:fixed; inset:0; z-index:10; background:rgba(0,0,0,.85); cursor:zoom-out;
             display:flex; flex-direction:column; align-items:center; justify-content:center; padding:16px; }
#zoom-view[hidden] { display:none; }
#zoom-view img { max-width:100%; max-height:88vh; object-fit:contain; border-radius:8px; }
#zoom-view p { color:#ccc; font-size:13px; }
.toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px; margin:0 0 12px; font-size:13px; }
.toolbar select, .toolbar input { font:inherit; padding:4px 6px; border-radius:6px;
  border:1px solid var(--line); background:var(--panel); color:var(--text); }
.toolbar input { width:64px; }
/* compact list view: one row per lot instead of the full card */
.row { display:none; align-items:center; gap:10px; padding:6px 10px; margin-bottom:6px;
       background:var(--panel); border:1px solid var(--line); border-radius:10px; font-size:14px; }
.row .thumb { width:40px; height:40px; object-fit:cover; border-radius:4px; flex:none; }
.row-per { font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; }
.row-name { font-weight:600; white-space:nowrap; }
.row-title { flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:13px; }
.btn.small { padding:4px 10px; font-size:13px; margin-left:auto; }
body.compact .row { display:flex; }
body.compact .lot > .item { display:none; }
.lot[hidden] { display:none; }
@media (max-width:520px) { .row-title { display:none; } }
.tag { font-size:11px; font-weight:600; padding:1px 7px; border-radius:6px; white-space:nowrap;
       background:var(--bg); color:var(--muted); border:1px solid var(--line); }
.news li { margin-bottom:6px; }
.like-list { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 14px; padding:0; list-style:none; }
.like-list li { background:var(--panel); border:1px solid var(--line); border-radius:999px; padding:3px 10px; font-size:13px; }
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

# Good / Medium / Bad buttons: send "good v1|123|0" to your ntfy ratings topic. The
# scanner reads it on its next run. Your choice is also remembered in this browser, so
# it stays highlighted until the next scan saves it. On the demo page nothing is sent.
RATE_JS = """
(function () {
  var topic = document.body.dataset.feedback;
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem('lot-spotter-ratings') || '{}'); } catch (e) {}
  function mark(box, label) {
    box.querySelectorAll('button').forEach(function (b) {
      b.classList.toggle('chosen', b.dataset.label === label);
    });
  }
  // the same lot can be on several tabs: update every copy; fold it away if Bad
  function markAll(id, label) {
    document.querySelectorAll('.rate').forEach(function (box) {
      if (box.dataset.id !== id) return;
      mark(box, label);
      if (label === 'bad') box.closest('details.item').open = false;
    });
  }
  // Ratings the last scan already saved come highlighted from the server. Ratings clicked
  // in this browser since then are "waiting for the next scan".
  var serverRated = {};
  document.querySelectorAll('.rate').forEach(function (box) {
    if (box.querySelector('.chosen')) serverRated[box.dataset.id] = true;
  });
  function showPending() {
    var note = document.getElementById('pending-note');
    if (!note) return;
    var onPage = {};
    document.querySelectorAll('.rate').forEach(function (b) { onPage[b.dataset.id] = true; });
    var n = Object.keys(saved).filter(function (id) { return onPage[id] && !serverRated[id]; }).length;
    note.textContent = n ? n + ' rating(s) from this browser are waiting for the next scan ' +
      '(scans run about every 10 minutes), then they count here.' : '';
  }
  showPending();
  document.querySelectorAll('.rate').forEach(function (box) {
    var id = box.dataset.id, msg = box.querySelector('.rate-msg');
    if (!topic) { box.hidden = true; return; }
    if (saved[id] && !box.querySelector('.chosen')) mark(box, saved[id]);
    box.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        var label = b.dataset.label;
        markAll(id, label);
        saved[id] = label;
        try { localStorage.setItem('lot-spotter-ratings', JSON.stringify(saved)); } catch (e) {}
        delete serverRated[id];
        showPending();
        if (topic === 'demo') { msg.textContent = 'Demo: not sent'; return; }
        msg.textContent = 'Saving...';
        fetch('https://ntfy.sh/' + encodeURIComponent(topic), { method: 'POST', body: label + ' ' + id })
          .then(function (r) {
            msg.textContent = r.ok ? 'Saved: the next scan learns from it' : 'Could not save (' + r.status + ')';
          })
          .catch(function () { msg.textContent = 'Could not save: check your connection'; });
      });
    });
  });
})();
"""


# The look: compact list toggle (remembered in this browser), sort and filter on each
# lot tab, and click a photo to see it bigger (eBay's larger version of the same photo).
LOOK_JS = """
(function () {
  var btn = document.getElementById('view-toggle');
  function setView(compact) {
    document.body.classList.toggle('compact', compact);
    btn.textContent = compact ? 'Full cards' : 'Compact list';
    try { localStorage.setItem('lot-spotter-view', compact ? 'compact' : 'cards'); } catch (e) {}
  }
  var view = null;
  try { view = localStorage.getItem('lot-spotter-view'); } catch (e) {}
  setView(view === 'compact');
  btn.addEventListener('click', function () { setView(!document.body.classList.contains('compact')); });

  // Sort and filter: re-order and hide lots in this tab only. Nothing is sent anywhere.
  document.querySelectorAll('section.tab').forEach(function (sec) {
    var bar = sec.querySelector('.toolbar'), box = sec.querySelector('.lots');
    if (!bar || !box) return;
    var sort = bar.querySelector('.f-sort'), min = bar.querySelector('.f-min'),
        who = bar.querySelector('.f-player'), count = bar.querySelector('.f-count');
    var original = Array.prototype.slice.call(box.querySelectorAll('.lot'));
    function apply() {
      var key = sort.value, lo = Number(min.value) || 0, p = who.value, shown = 0;
      var all = original.slice();
      if (key) all.sort(function (a, b) {
        if (key === 'per') return a.dataset.per - b.dataset.per;
        if (key === 'seen') return b.dataset.seen - a.dataset.seen;
        return b.dataset.score - a.dataset.score;
      });
      all.forEach(function (el) {
        var ok = Number(el.dataset.score) >= lo &&
                 (!p || el.dataset.players.split('|').indexOf(p) >= 0);
        el.hidden = !ok;
        if (ok) shown++;
        box.appendChild(el);
      });
      count.textContent = shown === all.length ? '' : 'showing ' + shown + ' of ' + all.length;
    }
    sort.addEventListener('change', apply);
    min.addEventListener('input', apply);
    who.addEventListener('change', apply);
  });

  // Click a photo: show eBay's big version (s-l1600) of it.
  var zoom = document.getElementById('zoom-view'), big = zoom.querySelector('img');
  document.querySelectorAll('button.zoom').forEach(function (b) {
    b.addEventListener('click', function () {
      big.src = b.querySelector('img').src.replace(/s-l\\d+\\./, 's-l1600.');
      zoom.hidden = false;
    });
  });
  zoom.addEventListener('click', function () { zoom.hidden = true; big.removeAttribute('src'); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && !zoom.hidden) zoom.click();
  });
})();
"""


def ratings_text(c):
    """'2 good · 1 medium · 3 bad', plus a hint when a search's lots are mostly bad."""
    if not c:
        return "-"
    text = " · ".join(f"{c[k]} {k}" for k in ("good", "medium", "bad") if c.get(k))
    total = sum(c.values())
    if total >= 5 and c.get("bad", 0) / total >= 0.7:
        text += " (mostly bad: consider removing)"
    return text


def learned_html(learned):
    """The 'What you like' tab: what your ratings taught the spotter."""
    pending = '<p class="warn" id="pending-note"></p>'
    if not learned or not learned["rated"]:
        return (pending + '<p class="empty">No ratings yet. Tap Good, Medium or Bad on any lot (or on a '
                'phone alert). After a few ratings, this shows what you like, and the spotter '
                'starts its own searches for it.</p>')
    c = learned["counts"]

    def chips(items):
        return ('<ul class="like-list">' + "".join(f"<li>{e(t)} ({v:+d})</li>" for t, v in items)
                + "</ul>") if items else '<p class="muted">Nothing clear yet.</p>'
    queries = "".join(f"<li><code>{e(q)}</code></li>" for q in learned["queries"])
    return pending + f"""
      <p class="intro">You've rated <b>{learned["rated"]}</b> lots: {c.get("good", 0)} good,
      {c.get("medium", 0)} medium, {c.get("bad", 0)} bad. Good = +2, Medium = +1, Bad = -2 for
      everything a lot names (prospects, year, product, features). Lots you rate Bad are hidden.</p>
      <h3>You like</h3>{chips(learned["liked"])}
      <h3>You pass on</h3>{chips(learned["disliked"])}
      <h3>New searches from your ratings</h3>
      {f'<ul>{queries}</ul><p class="muted">These run every 30 minutes and change as you rate more.</p>'
       if queries else '<p class="muted">None yet: something needs good ratings on at least 2 lots first.</p>'}"""


GROUP_NAMES = {"every_scan": "every scan", "my_searches": "my searches",
               "every_30_min": "every 30 min", "every_2_hours": "every 2 hours",
               "teams": "team (auto)", "players": "players (auto)", "typos": "name typos (auto)",
               "learned": "learned from your ratings"}


def searches_html(rows, cfg):
    """The Searches tab: what each search found last time, and how to change them."""
    body = "".join(
        f'<tr><td><code>{e(r["q"])}</code></td><td>{e(GROUP_NAMES.get(r["group"], r["group"]))}</td>'
        f'<td class="n">{e(ago(r["last"]) or "not yet")}</td>'
        f'<td class="n">{e(r["found"] or "-")}</td><td class="n">{e(r["kept"] or "-")}</td>'
        f'<td>{e(ratings_text(r.get("ratings")))}</td></tr>'
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
        <tr><th>Search</th><th>How often</th><th>Last run</th><th>eBay results</th><th>Lots kept</th>
            <th>Your ratings</th></tr>
        {body}
      </table></div>"""


def bids_text(r):
    return "-" if r["avg_bids"] is None else f'{r["avg_bids"]:.1f}'


def trending_html(trending):
    """The Trending tab: per prospect, lots and median asking price this week vs last
    week, and average bids on auctions that ended in the last 7 days."""
    rows, days = trending or ([], 0)
    if not rows:
        return '<p class="empty">Not enough data yet.</p>'

    def change(r):
        if r["change"] is None:
            return '<span class="muted">-</span>'
        cls = "good" if r["change"] > 0.05 else "bad" if r["change"] < -0.05 else ""
        return f'<span class="{cls}">{r["change"]:+.0%}</span>'
    body = "".join(
        f'<tr><td>{"#" + str(r["rank"]) if r["rank"] else ""} {e(r["player"])}</td>'
        f'<td class="n">{r["lots"]}</td><td class="n">{money(r["median"])}</td>'
        f'<td class="n">{money(r["last_median"])}</td><td class="n">{change(r)}</td>'
        f'<td class="n">{r["auctions"]}</td>'
        f'<td class="n">{bids_text(r)}</td></tr>'
        for r in rows)
    note = ("" if days >= 14 else
            f'<p class="warn">Only {days:.0f} day(s) of data so far: the week-over-week change '
            f'appears after 2 weeks of scanning.</p>')
    return f"""
      <p class="intro">From the spotter's own scans only. <b>Median ask</b> = the middle asking
      price of the prospect's Buy It Now lots first seen that week (lot sizes vary, so it's a rough
      signal). <b>Avg bids</b> = auctions that ended in the last 7 days (the last count we saw, so
      a little low). Rising asks and more bids mean more interest.</p>{note}
      <div class="table-wrap"><table class="searches">
        <tr><th>Prospect</th><th>Lots this week</th><th>Median ask</th><th>Last week</th>
            <th>Change</th><th>Auctions</th><th>Avg bids</th></tr>
        {body}
      </table></div>"""


# Prospect news: sites to check BY HAND (plain links; nothing is fetched or scraped).
NEWS_LINKS = [
    ("MLB Pipeline Top 100", "https://www.mlb.com/prospects/top100",
     "The official ranking prospects.yaml is based on (big update every January, smaller mid-season)."),
    ("FanGraphs: The Board", "https://www.fangraphs.com/prospects/the-board",
     "FanGraphs' prospect rankings with scouting grades; good for spotting risers early."),
    ("Baseball America prospect rankings", "https://www.baseballamerica.com/rankings/",
     "Top 100 and team-by-team lists; some articles need a subscription."),
    ("Prospects Live", "https://www.prospectslive.com/",
     "Rankings, draft coverage and minor-league notes."),
    ("Arizona Fall League stats", "https://www.mlb.com/milb/arizona-fall-league/stats",
     "October-November: hot Fall League hitters often get a card bump (good riser ideas)."),
]


def news_html(risers, prospects_updated, repo):
    """The Prospect news tab: links, your risers.yaml list, and when prospects.yaml was updated."""
    links = "".join(f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a>: {e(why)}</li>'
                    for n, u, why in NEWS_LINKS)
    rows = "".join(f'<tr><td>{e(r["name"])}</td><td>{e(r.get("note") or "")}</td></tr>'
                   for r in risers) or '<tr><td colspan="2" class="muted">No risers yet.</td></tr>'

    def edit(file):
        return (f'<a href="https://github.com/{e(repo)}/edit/main/{file}" target="_blank" '
                f'rel="noopener">Edit {file} on GitHub</a>' if repo else f"Edit {file}")
    return f"""
      <p class="intro">Sites to check by hand for prospect news (links only: the spotter never
      reads these sites). When someone's getting hot, add them to your risers.</p>
      <ul class="news">{links}</ul>
      <h3>Your risers</h3>
      <p class="muted">Each riser gets +8 on lots that name them, a "Riser" tag, and its own search
      every 2 hours. {edit("risers.yaml")}.</p>
      <div class="table-wrap"><table class="searches"><tr><th>Player</th><th>Your note</th></tr>
        {rows}</table></div>
      <h3>Prospect list</h3>
      <p class="muted">prospects.yaml last updated: <b>{e(prospects_updated or "unknown")}</b>.
      {edit("prospects.yaml")} (then change its <code>updated:</code> date).</p>"""


def january_banner(today=None):
    """Every January, MLB Pipeline re-ranks its prospects: remind me to update the list."""
    today = today or now().date()
    if today.month != 1:
        return ""
    return ('<p class="demo">January reminder: MLB Pipeline publishes its new '
            'Top 100 this month. Update prospects.yaml (see the Prospect news tab).</p>')


def build(path, lots, search_rows, cfg, updated, tracked, demo=False, learned=None,
          feedback_topic=None, trending=None, risers=(), prospects_updated=None):
    """lots = scored lot dicts from main.py, best score first. feedback_topic = your
    ntfy ratings topic (the rating buttons post to it; without one they're hidden)."""
    S = cfg["spotter"]
    cap = S["max_per_tab"]
    # Old Best Offer lots only go on the "Make an offer" tab
    offers = [x for x in lots if x.get("offer_only")]
    lots = [x for x in lots if not x.get("offer_only")]
    day_ago = now().timestamp() - 24 * 3600
    newest = sorted([x for x in lots if parse_time(x["first_seen"]).timestamp() >= day_ago],
                    key=lambda x: x["first_seen"], reverse=True)
    ending = sorted([x for x in lots if x["buying"] == "AUCTION"], key=lambda x: x["end_time"])
    cheap = sorted([x for x in lots if x["info"]["per_card"] is not None
                    and x["info"]["per_card"] <= 1.00],
                   key=lambda x: (-x["score"], x["info"]["per_card"]))

    # Every section: (tab id, sidebar group, title, items, message when empty, intro text)
    sections = [
        ("top", "Lots", "Top lots", lots,
         "No lots scored high enough yet.",
         f"Buy It Now lots listed in the last {S['max_age_hours']} hours and auctions ending soon, "
         f"best score first (0-100). Points come from top prospects named, "
         f"1st Bowman / auto / numbered cards, price per card, and how fresh the listing is. "
         f"New lots scoring {S['alert_min_score']}+ send a phone alert."),
        ("new", "Lots", "New (last 24 h)", newest,
         "Nothing new in the last 24 hours.",
         "Lots first seen in the last 24 hours, newest first: the ones other buyers may not have seen yet."),
        ("ending", "Lots", "Auctions ending soon", ending,
         "No auctions ending soon.",
         f"Auctions ending in the next {S['auction_hours']} hours, soonest first. "
         "The current bid will still rise."),
        ("cheap", "Lots", "$1 a card or less", cheap,
         "No lots at $1 a card or less right now.",
         "Price + shipping divided by the number of cards (when the listing says how many)."),
        ("offer", "Lots", "Make an offer", offers,
         "No Best Offer lots listed 7+ days ago right now.",
         f"Buy It Now lots that accept Best Offer and were listed {S['offer_after_days']}+ days ago. "
         "Still unsold after a week usually means the price is too high, so the seller may take "
         "less: try an offer around what the lot is worth to you. (Scores include the -10 for "
         "being old.)"),
    ]

    def shown_of(items):
        """'60 of 412' when the tab holds more lots than it shows, else just '12'."""
        return f"{min(len(items), cap)} of {len(items)}" if len(items) > cap else str(len(items))

    def section_html(sid, group, title, items, empty_msg, intro):
        body = "".join(lot_html(x) for x in items[:cap]) or f'<p class="empty">{empty_msg}</p>'
        return f"""
  <section class="tab" id="tab-{sid}" data-tab-id="{sid}" data-count="{len(items)}">
    <details class="sec" open>
      <summary><h2>{title} ({shown_of(items)})</h2></summary>
      <p class="muted intro">{intro}</p>
      {toolbar_html(items[:cap]) if items else ""}
      <div class="lots">{body}</div>
    </details>
  </section>"""

    links = "".join(f'<a href="#{sid}" data-tab="{sid}">{title}<span class="count">{shown_of(items)}</span></a>'
                    for sid, _, title, items, _, _ in sections)
    rated = learned["rated"] if learned else 0
    links_settings = (f'<a href="#searches" data-tab="searches">Searches'
                      f'<span class="count">{len(search_rows)}</span></a>'
                      f'<a href="#likes" data-tab="likes">What you like'
                      f'<span class="count">{rated}</span></a>')
    # Research tabs: (tab id, title, count shown in the sidebar, html)
    trend_rows = (trending or ([], 0))[0]
    research = [("trending", "Trending", len(trend_rows), trending_html(trending)),
                ("news", "Prospect news", len(risers),
                 news_html(risers, prospects_updated, S.get("repo")))]
    links_research = "".join(f'<a href="#{sid}" data-tab="{sid}">{title}<span class="count">{n}</span></a>'
                             for sid, title, n, _ in research)
    research_html = "".join(f'''
    <section class="tab" id="tab-{sid}" data-tab-id="{sid}" data-count="{n}">
      <details class="sec" open>
        <summary><h2>{title}</h2></summary>
        {body}
      </details>
    </section>''' for sid, title, n, body in research)
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
<body data-feedback="{e(feedback_topic or "")}">
<div class="layout">
  <nav class="side" aria-label="Sections">
    <p class="title">Lot Spotter</p>
    <details class="group" open><summary>Lots</summary>{links}</details>
    <details class="group" open><summary>Research</summary>{links_research}</details>
    <details class="group" open><summary>Settings</summary>{links_settings}</details>
    <div class="tools">
      <button type="button" id="expand-all">Expand all</button>
      <button type="button" id="collapse-all">Collapse all</button>
    </div>
    <div class="tools">
      <button type="button" id="view-toggle">Compact list</button>
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
    {demo_note}{january_banner()}
    {"".join(section_html(*s) for s in sections)}
    {research_html}
    <section class="tab" id="tab-searches" data-tab-id="searches" data-count="{len(search_rows)}">
      <details class="sec" open>
        <summary><h2>Searches ({len(search_rows)})</h2></summary>
        {searches_html(search_rows, cfg)}
      </details>
    </section>
    <section class="tab" id="tab-likes" data-tab-id="likes" data-count="{rated}">
      <details class="sec" open>
        <summary><h2>What you like ({rated} rated)</h2></summary>
        {learned_html(learned)}
      </details>
    </section>
    <footer>
      Scores are a quick guide, not a price check: eBay doesn't share sold prices through its
      free API. Before buying, look at the photos (which cards are really in the lot, condition,
      fakes), the seller's feedback, and recent sold prices yourself.
    </footer>
  </main>
</div>
<div id="zoom-view" hidden><img alt=""><p>Click anywhere to close</p></div>
<script>{TABS_JS}{RATE_JS}{LOOK_JS}</script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
