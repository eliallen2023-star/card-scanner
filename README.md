# Lot Spotter

Watches eBay for **baseball card lots**, scores each one from 0 to 100, and pushes a
phone alert (with the eBay link) when a **new** high-scoring lot shows up, so you can see
it before other buyers do. Lots naming top prospects (`prospects.yaml`) rank highest.
Everything is also on a web page (GitHub Pages), ranked by score.

It uses only eBay's official Browse API (no scraping) and plain code for scoring (no AI).

## How it works
1. **Searches** (`searches.yaml`, edit it any time): broad lot searches like `1st bowman lot`,
   your own terms, misspellings (`bowmen`, `refracter`) that fewer buyers find, team lots and
   player-name lots built from `prospects.yaml`. Each search looks at newly listed Buy It Now
   lots and auctions ending in the next 3 hours.
2. **Details**: for the most promising new lots, one extra call reads the item specifics and
   description: real shipping, number of cards, players named, and Sport (non-baseball lots
   are dropped).
3. **Score** (`score.py`): prospects named (up to 45, the #1 prospect counts most), card types
   (1st Bowman, auto, numbered, graded, refractor... up to 30), price per card (up to 20),
   freshness (5). The page shows why each lot got its score.
4. **Alerts**: new lots scoring `alert_min_score` (60) or more, first seen in the last 12 hours,
   outside quiet hours (11pm-8am). The very first scan sends none.
5. **Web page** tabs: Top lots, New (last 24 h), Auctions ending soon, $1 a card or less, Searches.

## Run it on your computer (Windows PowerShell, Python 3.13)
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --demo      # fake lots, no keys: writes docs\demo.html
.venv\Scripts\python.exe main.py --budget    # API calls per day your searches use (limit 5,000)
.venv\Scripts\python.exe main.py --dry-run   # real eBay search, alerts printed: docs\preview.html
```
Tests: `test_score.py`, `test_parse.py`, `test_lots.py`, `test_paste.py`.

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
