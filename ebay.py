"""Minimal eBay Browse API client (official, free with a developer account)."""
import base64
import html
import re
import time
from datetime import timedelta
from urllib.parse import quote

import requests

from store import iso, now

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/"


class Ebay:
    def __init__(self, client_id, client_secret, ship_to_zip="10001"):
        self.client_id, self.client_secret = client_id, client_secret
        self.zip = ship_to_zip
        self._token, self._expires = None, 0
        self.calls = 0

    def token(self):
        """An 'application token' (lasts 2 hours). Fetched once and reused."""
        if self._token and time.time() < self._expires - 300:
            return self._token
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        r = requests.post(TOKEN_URL, timeout=30, headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                  "scope": "https://api.ebay.com/oauth/api_scope"})
        r.raise_for_status()
        j = r.json()
        self._token, self._expires = j["access_token"], time.time() + j["expires_in"]
        return self._token

    def _get(self, url, params=None):
        """GET from the Browse API, retrying if eBay is busy. Returns the JSON, or None."""
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            # "I'm a buyer in the US at this ZIP" - lets eBay work out calculated shipping
            "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3DUS%2Czip%3D{self.zip}",
        }
        for attempt in range(3):
            r = requests.get(url, params=params, timeout=30, headers=headers)
            self.calls += 1
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 * (attempt + 1))   # eBay busy: wait a moment and retry
                continue
            r.raise_for_status()
            return r.json()
        return None

    def search(self, q, category_id, buying, sort, limit, max_price, ends_within_hours=None):
        """One search. buying is "AUCTION" or "FIXED_PRICE" (Buy It Now).
        ends_within_hours: only auctions ending before now + that many hours."""
        filters = [f"buyingOptions:{{{buying}}}", f"price:[1..{max_price}]",
                   "priceCurrency:USD", "deliveryCountry:US"]
        if ends_within_hours:
            filters.append(f"itemEndDate:[..{iso(now() + timedelta(hours=ends_within_hours))}]")
        j = self._get(SEARCH_URL, {
            "q": q,
            "category_ids": category_id,
            "filter": ",".join(filters),
            "sort": sort,
            "limit": str(min(limit, 200)),   # eBay's maximum per call is 200
        })
        return [simplify(i) for i in (j or {}).get("itemSummaries", [])]

    def get_shipping(self, item_id):
        """Look up ONE listing's full details and return its cheapest shipping
        cost to our ZIP, or None if eBay still doesn't give one. Costs 1 call."""
        j = self._get(ITEM_URL + quote(item_id, safe=""))   # item ids contain "|"
        return cheapest_shipping(j or {})

    def item_details(self, item_id):
        """Full details of one LOT listing (1 call): shipping, the description as
        text lines, players and card count from the item specifics."""
        j = self._get(ITEM_URL + quote(item_id, safe="")) or {}
        aspects = {a.get("name"): a.get("value") for a in j.get("localizedAspects", []) or []}
        players = [p.strip() for p in (aspects.get("Player/Athlete") or "").split(",") if p.strip()]
        try:
            count = int(aspects.get("Number of Cards"))
        except (TypeError, ValueError):
            count = None
        return {"shipping": cheapest_shipping(j),
                "lines": description_lines(j.get("description") or ""),
                "players": players, "count": count}


def description_lines(desc_html):
    """Seller descriptions are HTML. Turn them into plain text lines."""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</tr>|</h\d>", "\n", desc_html)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))   # drop the remaining tags
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line][:300]          # cap very long descriptions


def _money(d):
    try:
        return float(d["value"])
    except (TypeError, KeyError, ValueError):
        return None


def cheapest_shipping(i):
    ship = None
    for opt in i.get("shippingOptions", []) or []:
        c = _money(opt.get("shippingCost"))
        if c is not None:
            ship = c if ship is None else min(ship, c)
    return ship


def simplify(i):
    """Keep just the fields we use from eBay's (large) listing record."""
    ship = cheapest_shipping(i)
    is_auction = "AUCTION" in (i.get("buyingOptions") or [])
    price = _money(i.get("currentBidPrice")) if is_auction else None
    if price is None:
        price = _money(i.get("price")) or 0.0
    return {
        "item_id": i["itemId"],
        "title": i.get("title", ""),
        "buying": "AUCTION" if is_auction else "BIN",
        "price": price,
        # About half of search results leave shipping out (calculated shipping).
        # We use 0 for now but remember it's unknown; main.py looks up the real
        # cost for the promising ones, and the page warns about the rest.
        "shipping": ship if ship is not None else 0.0,
        "shipping_known": ship is not None,
        "bid_count": i.get("bidCount", 0) or 0,
        "end_time": i.get("itemEndDate"),
        "url": i.get("itemWebUrl", ""),
        "image": (i.get("image") or {}).get("imageUrl", ""),
    }
