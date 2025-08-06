import os
from datetime import datetime
from typing import List

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote

# ========= Config via env =========
REALM = os.getenv("REALM", "poe2")  # poe1|poe2
LEAGUE = os.getenv("LEAGUE", "Dawn of the Hunt")
QUERY_ID = os.getenv("QUERY_ID", "")  # the saved search id from /trade2/search/.../<id>
USER_AGENT = os.getenv("USER_AGENT", "poe2-flips/0.13 (contact: you@example.com)")
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "30"))
DIVINE_TO_CHAOS = float(os.getenv("DIVINE_TO_CHAOS", "180"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

# ========= FastAPI app + CORS =========
app = FastAPI()

if CORS_ORIGINS == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= Helpers =========
def api_search(realm: str, league: str, query_id: str):
    """
    For saved searches, PoE2 supports:
    GET /api/trade2/search/{realm}/{league}/{id}
    Response includes "result": [<listing ids>]
    """
    if not query_id:
        return {"result": []}

    league_enc = quote(league, safe="")
    url = f"https://www.pathofexile.com/api/trade2/search/{realm}/{league_enc}/{query_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def api_fetch(ids: List[str], query_id: str):
    """
    Fetch listing details. Must pass the listing IDs AND ?query=<id>
    GET /api/trade2/fetch/{id1,id2,...}?query=<search id>
    """
    if not ids:
        return {"result": []}
    url = f"https://www.pathofexile.com/api/trade2/fetch/{','.join(ids)}?query={query_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def map_result_to_deal(res_item: dict):
    listing = res_item.get("listing", {})
    item = res_item.get("item", {}) or {}
    price = listing.get("price", {}) or {}

    amount = price.get("amount")
    currency = price.get("currency")
    price_str = f"{amount}{currency}" if amount is not None and currency else ""

    return {
        "id": res_item.get("id"),
        "name": item.get("name") or "",
        "baseType": item.get("typeLine") or "",
        "price": amount,
        "currency": currency,
        "priceStr": price_str,
        "estimate": None,      # left blank for now (no filtering)
        "marginPct": None,     # left blank for now (no filtering)
        "score": None,         # left blank for now (no filtering)
        "seller": (listing.get("account") or {}).get("name", ""),
        "listedAt": listing.get("indexed"),
        "seenAt": listing.get("indexed"),
        "tradeUrl": f"https://www.pathofexile.com/trade2/search/{REALM}/{quote(LEAGUE, safe='')}/{QUERY_ID}",
    }

# ========= Routes =========
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "realm": REALM,
        "league": LEAGUE,
        "query_id": QUERY_ID,
    }

@app.get("/deals")
def deals(limit: int = Query(FETCH_LIMIT, ge=1, le=100)):
    """
    Returns raw listings from PoE2 for the saved search identified by QUERY_ID.
    No server-side filtering; just maps to a simple shape for the frontend.
    """
    try:
        search_data = api_search(REALM, LEAGUE, QUERY_ID)
        ids = (search_data.get("result") or [])[:limit]
        if not ids:
            return {"items": []}

        fetch_data = api_fetch(ids, QUERY_ID)
        results = fetch_data.get("result") or []
        mapped = [map_result_to_deal(r) for r in results]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        return {"items": [], "error": f"http_error:{e.response.status_code}"}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/history")
def history(id: str):
    # Placeholder history endpoint
    return {"id": id, "history": []}
