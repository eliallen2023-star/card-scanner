# Card Scanner

Scans eBay every hour for cards of MLB's top 50 prospects. It records what auctions
actually sell for, and pushes a notification to your phone when a listing is priced
well below recent sales, or when a cheap lot includes several of your prospects.

## Software you need (all free)

| What | Why |
|---|---|
| **Python 3.12+** (python.org) | The language the app is written in |
| **VS Code** (code.visualstudio.com) + the Python extension | Editing and running the code |
| **Git** + a **GitHub** account | Stores the code and runs it on a schedule for free (GitHub Actions) |
| **eBay Developer account** (developer.ebay.com) | Official API keys for searching listings |
| **ntfy app** (App Store / Google Play) | Receives the push notifications on your phone |

## Setup, step by step

### 1. Run the demo on your computer
Windows PowerShell (use Python 3.13):
```powershell
cd card-scanner
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe test_parse.py     # title-parser tests
.venv\Scripts\python.exe main.py --demo    # fake data: prints sample alerts, writes docs\demo.html
start docs\demo.html                       # open the demo web page
```

### Check a card's price yourself (no keys needed)
```powershell
.venv\Scripts\python.exe check.py "2025 Bowman Chrome Jesus Made 1st Auto Refractor /499" 80 --ship 4.99
```
Shows the sales the scanner has recorded for that exact card, your estimated profit, and
links to eBay sold listings, 130point and PSA prices so you can look up comps by hand.

Both `check.py` and `paste.py` first download the scanner's latest prices from the
`scanner-data` branch on GitHub (add `--offline` to skip that).

### Judge a whole Facebook sale post (paste mode)
Copy a post from a Facebook group (or anywhere) and paste it in:
```powershell
.venv\Scripts\python.exe paste.py --year 2025      # paste, then type  done  on its own line
.venv\Scripts\python.exe paste.py --file post.txt  # or save the post in a text file
```
Each line with a prospect's full name and a price (`$80`, `80 shipped`, `25 + ship`, `35 obo`)
is one card; the price can also be on the next line. Shorthand like `BDC` is understood.
Prices not marked "shipped" get `--ship` added (default $5). Every card gets a verdict and
lookup links, best first. Nothing touches Facebook: it doesn't allow automated access, so
you copy the post yourself. Pay with PayPal Goods & Services, never Friends & Family.

### 2. Get eBay API keys
1. Sign up at developer.ebay.com and create an app ("Application Keys").
2. eBay asks you to set up **Marketplace Account Deletion** notifications before it
   turns on production keys. This app doesn't store any eBay user data, so choose the
   option to apply for an **exemption**.
3. Copy the **Production** App ID (Client ID) and Cert ID (Client Secret).
4. Test it (PowerShell; these only last until you close the window, nothing is saved to a file):
   ```powershell
   $env:EBAY_CLIENT_ID = "..."; $env:EBAY_CLIENT_SECRET = "..."
   .venv\Scripts\python.exe main.py --dry-run   # real search, alerts printed, writes docs\preview.html
   ```

### 3. Set up phone alerts
1. Install **ntfy** and tap **+ Subscribe to topic**.
2. Pick a long, hard-to-guess topic name, e.g. `eli-cards-8f3k29x` (anyone who knows it can read your alerts).
3. `export NTFY_TOPIC=eli-cards-8f3k29x` and run `python main.py`.

### 4. Make it run automatically
1. Create a **public** GitHub repo and push this folder to it. (Public repos get free
   Actions minutes and free GitHub Pages. Keys are never in the code, only in secrets.
   Note: anyone who finds your Pages site can see your deals.)
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**, and add
   `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` and (optional) `NTFY_TOPIC`.
3. **Actions** tab → enable workflows → **card-scan → Run workflow** to test it.
4. After the first run succeeds, a branch called `scanner-data` appears. Go to
   **Settings → Pages** → Source: *Deploy from a branch*, branch `scanner-data`, folder `/docs`.
   Each run updates that page with every current deal and a **View on eBay** link.

After that it runs every 15 minutes. Auctions are checked every run; Buy It Now listings
about once an hour. The database and page live on the `scanner-data` branch, which each
run replaces with one fresh commit, so the repo stays small and the bot never touches your code.

## How it decides something is a deal

1. **Card key.** `parse.py` reads each title and turns it into player | year | product | auto/base |
   1st | parallel | serial number | grade. A "1st Gold Refractor /50 PSA 10" is only compared with
   the same card (same year too, because 1st Bowman cards sell for much more than later ones).
2. **Comps.** Every 15 minutes the scanner records auctions ending in the next 3 hours. Once
   one ends with bids, and it was seen within 30 minutes of the end, its last price becomes a
   sale record. It's a bit low (it misses last-minute bids), which keeps estimates on the safe side.
3. **Alert rule** (all in `config.yaml`):
   - the price plus shipping is **at least 30% below** the median of recent sales,
   - estimated profit after the 13.25% eBay fee and outgoing shipping is **at least $10**,
   - there are at least 3 recent sales to compare against,
   - auctions only alert in their last 3 hours, and the alert says the price will still rise.
4. **Lots (lots.py).** Each lot is valued card by card. The cards come from the description if it
   lists them, otherwise from the title and eBay's Player/Athlete item specific ("Lot of (18)" of one
   card = 18 copies). Each card gets a single's value: 3+ sold comps, else the low end of 5+ asking
   prices for that exact card, else the player's base cards. Only 3 copies of a card count. A lot
   30%+ under its singles shows on the page; it alerts only if reselling the singles nets $10+
   (cards under $6 count $0 there). Check the photos: a lot may hold cheaper versions than described.
   **Cheap 1st & RC lots (page only):** lots of 5+ cards at about $1 or less per card (price +
   shipping), naming at least one of your prospects (the other cards can be anyone) and mentioning
   1st or RC cards. Ranked 1sts first, then RCs, then by the prospects named. Settings: `lots.bulk`.
5. **Recommended (web page only).** Before sold comps build up, the page also lists Buy It Now
   cards priced 25%+ under what other sellers ask for the exact same card (needs 3+ other
   listings), ranked by a desirability score: prospect rank, 1st, auto, numbered, color, grade 10.
   Asking prices run higher than sales, so these never send phone alerts. Settings: `recommend:`
   in `config.yaml`; scoring: `desirability()` in `main.py`.

**Expect a quiet first 2–3 weeks.** Until enough sales are recorded, only lot alerts can
fire. To speed this up, look up a few sales by hand (for example on 130point) and add them
to `manual_comps.csv`:
```
title,total_price,sold_date
2025 Bowman Chrome Jesus Made 1st Auto Refractor /499,128.00,2026-11-02
```

## Customizing
- `prospects.yaml`: your player list. A few ranks are missing (see the note in the file).
  Pipeline updates the list again in January.
- `config.yaml`: discount, profit, quiet hours (11pm–8am by default) and the maximum price.
- `search.extra_keywords: "bowman"` limits searches to Bowman products.

## Limits worth knowing
- The free Browse API allows about 5,000 calls a day. Up to 4 players share one search,
  so 37 players is about 10 searches per run: ~1,300 calls a day. With 50 players, ~1,700.
- Buy It Now sales can't be seen through the free API, so the comps come from auctions only.
- About half of search results don't show shipping. For listings that would be deals with free
  shipping, the scanner looks up the real cost (up to 10 per run, each listing only once). Any
  left unknown are marked "Shipping not listed" on the page.
- Check every alert before you buy: look at the photos for condition, centering and fakes,
  and check the seller's feedback.
