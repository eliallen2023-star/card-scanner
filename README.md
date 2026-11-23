# Lot Spotter

Watches eBay for **baseball card lots**, scores each one from 0 to 100, and pushes a
phone alert (with the eBay link) when a **new** high-scoring lot shows up, so you can see
it before other buyers do. Lots naming top prospects (`prospects.yaml`) rank highest.
Everything is also on a web page (GitHub Pages), ranked by score.

It uses only eBay's official Browse API (no scraping) and plain code for scoring (no AI).

## How it works
1. **Searches** (`searches.yaml`, edit it any time): broad lot searches like `1st bowman lot`,
   your own terms, misspellings (`bowmen`, `refracter`) that fewer buyers find, team lots and
   player-name lots built from `prospects.yaml`, common name typos (`typos:` in
   `prospects.yaml`, e.g. "Eli Willets"), and your risers (`risers.yaml`). Each search looks at
   newly listed Buy It Now lots and auctions ending in the next 3 hours (8 hours from 8-11 PM, to
   catch auctions ending 1-6 AM when few people bid).
2. **Details**: for the most promising new lots, one extra call reads the item specifics and
   description: real shipping, number of cards, players named, and Sport (non-baseball lots
   are dropped).
3. **Score** (`score.py`): prospects named (up to 30; top 100 in `prospects.yaml`, #1 = 30,
   #50 = 15, #100 = 0.3), card types (1st Bowman 20, or 8 if only the description says it;
   auto, numbered, graded, color... up to 35),
   shiny cards (refractor, mojo, x-fractor, shimmer, sparkle, wave, sapphire... from the title,
   item specifics or description: 1 kind +8, 2 kinds +12, 3+ kinds +15), +10 when a ranked prospect AND a 1st Bowman
   are in the title, title says Bowman Chrome +10 / doesn't say Bowman -10, team lot (one MLB
   team, 10+ cards) -15, other sets in the title (Pro Debut, Heritage, Mosaic...) -10, price
   per card (up to 12; $1-4 a card scores best, very cheap bulk only 3), freshness (5).
   Football / basketball / other-sport lots (title words like "football", "Bowman U", "NFL",
   team names) are skipped, or -15 if they also name one of your prospects. Also: listed over
   7 days ago -10, same-card bulk ("x50 one card") -20 with stricter price points, seller
   feedback under 50 +5, auction ending 1-6 AM Eastern with 0-2 bids +5, risers +8, and your
   own sold prices / sell-through (below). The page shows why each lot got its score.
4. **Alerts**: new lots scoring `alert_min_score` (65) or more, first seen in the last 12 hours,
   outside quiet hours (11pm-8am). The very first scan sends none.
5. **Web page** tabs: Top lots, New (last 24 h), Auctions ending soon, $1 a card or less,
   Make an offer (Best Offer lots listed 7+ days ago), Trending (from our own scans: lots and
   median asking price this week vs last, average bids), Prospect news, Searches, What you like.
   Tab counts read "60 of 412" (shown of total). Each lot tab has sort / min score / prospect
   filters, and a **Compact list** button (remembered in your browser). Click a photo to enlarge.

## Your own research (by hand: nothing here is scraped or automated)
- **Sold-price links** on every lot: eBay sold, 130point, and eBay **Product Research**
  (`ebay.com/sh/research`, in Seller Hub). Note: Seller Hub only opens for accounts with at
  least one completed sale.
- **`manual_comps.csv`**: `title,total_price,sold_date,sell_through`. Type in sales you look up.
  Each row should name one prospect. A lot whose named prospects' sold prices (one card each)
  cover its price gets +5 (1.5x: +10). `sell_through` is optional (65 = 65%, e.g. from
  Product Research); above 50% adds +1 per 10 points, up to +3.
- **`risers.yaml`**: players you think are getting hot, with a note. +8 on their lots, a
  "Riser" tag, their own search every 2 hours; listed on the Prospect news tab (edit link there).
- **`prospects.yaml`**: change its `updated:` date when you refresh it. Every January the page
  shows a reminder (MLB Pipeline's new Top 100 comes out then).

## Rate lots: Good / Medium / Bad (it learns from you)
Every lot on the page, and every phone alert, has **Good / Medium / Bad** buttons. A rating is
sent to a second ntfy topic (`NTFY_FEEDBACK_TOPIC`), and the next scan saves it (`feedback.py`):
- It counts what the lots you rate have in common (prospects, year, product, features such as
  Mojo, auto, PSA 10). Good = +2, Medium = +1, Bad = -2; something needs 2+ liked lots to count.
- From that it builds up to `learned_searches` (4) **new searches**, run every 30 minutes.
- The **What you like** tab shows what it learned; the **Searches** tab shows how you rated each
  search's lots (and suggests removing searches whose lots you mostly rate Bad).
- Lots you rate Bad are hidden. Only ratings for lots the spotter found are accepted.
Note: the ratings topic name is in the public page's code, so someone who finds your site could
send fake ratings. ntfy.sh keeps messages about 12 hours, so ratings are read well before then.

## Run it on your computer (Windows PowerShell, Python 3.13)
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --demo      # fake lots, no keys: writes docs\demo.html
.venv\Scripts\python.exe main.py --budget    # API calls per day your searches use (limit 5,000)
.venv\Scripts\python.exe main.py --dry-run   # real eBay search, alerts printed: docs\preview.html
```
Tests: `test_score.py`, `test_feedback.py`, `test_parse.py`, `test_lots.py`, `test_paste.py`.

The dry run needs eBay API keys in the environment variables `EBAY_CLIENT_ID` and
`EBAY_CLIENT_SECRET` (developer.ebay.com, Production keyset). Never put keys in a file.

## Change your searches
Open `searches.yaml` on GitHub, click the pencil, edit, and **Commit changes** (or use the
"Edit your searches" link on the Searches tab). The next scan uses the new list.
Spaces mean AND, `(a, b)` means either one, 100 characters at most. Searches in `every_scan`
cost the most API calls; run `main.py --budget` after adding several.

## Settings (`config.yaml` → `spotter:`)
`alert_min_score`, `page_min_score`, `max_price`, `max_price_per_card` (lots with none of your
prospects that cost more per card are skipped), `detail_lookups_per_run`, quiet hours under `alerts:`.

## Running automatically (GitHub)
- Public repo, so Actions and Pages are free. Secrets: `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`,
  `NTFY_TOPIC` (Settings → Secrets and variables → Actions).
- `.github/workflows/scan.yml` runs a scan, then saves the database and page to the
  `scanner-data` branch (one fresh commit each time). GitHub Pages publishes its `/docs` folder.
- GitHub's own schedule is best-effort (runs can be hours apart), so an outside timer starts
  the workflow every 10 minutes.

## Phone alerts (ntfy)
Install the free **ntfy** app, subscribe to your topic name, and store the same name as the
`NTFY_TOPIC` secret. Anyone who knows the topic can read your alerts, so make it hard to guess.

## Judging cards you find elsewhere (paste mode)
Copy a Facebook group page or post (Ctrl+A, Ctrl+C) and run `.venv\Scripts\python.exe paste.py
--year 2025`. It finds each card and lot with its price and judges it against the scanner's
data (`check.py` does the same for one card). Nothing touches Facebook. Note: these use the
singles prices the old card scanner collected, which will thin out now that it only scans lots.

## Limits worth knowing
- eBay's free API has **no sold prices**, so scores rank lots; they don't price them. Check
  sold prices (eBay sold filter, 130point) and the photos before you buy.
- About half of search results don't show shipping until the detail lookup.
- Card counts come from the title or the "Number of Cards" item specific; some lots don't say.
