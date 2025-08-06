import os
import re
from datetime import datetime
from typing import List
from urllib.parse import quote

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# ========= Env config =========
REALM = os.getenv("REALM", "poe2")
LEAGUE_RAW = os.getenv("LEAGUE", "Dawn of the Hunt")
LEAGUE = quote(LEAGUE_RAW, safe="")
DEFAULT_ITEM = os.getenv("DEFAULT_ITEM", "Scroll of Wisdom")
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "30"))
USER_AGENT = os.getenv("USER_AGENT", "poe2-flips/0.13 (contact: you@example.com)")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ========= FastAPI + CORS =========
app = FastAPI(title="PoE2 Flips API v13 (dynamic search + URL search)")

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

# ========= Helper: mapping result items =========
def map_listing(res_item: dict) -> dict:
    listing = res_item.get("listing", {}) or {}
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
        "estimate": None,
        "marginPct": None,
        "score": None,
        "seller": (listing.get("account") or {}).get("name", ""),
        "listedAt": listing.get("indexed"),
        "seenAt": listing.get("indexed"),
        "tradeUrl": f"https://www.pathofexile.com/trade2/search/{REALM}/{LEAGUE}/{res_item.get('id','')}",
    }

# ========= PoE API helpers =========
def post_search(item_name: str) -> dict:
    url = f"https://www.pathofexile.com/api/trade2/search/{REALM}/{LEAGUE}"
    body = {
        "query": {
            "status": {"option": "online"},
            "name": item_name,
        },
        "sort": {"price": "asc"},
    }
    r = requests.post(url, headers=HEADERS, json=body, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_results(ids: List[str], search_id: str) -> dict:
    if not ids:
        return {"result": []}
    url = f"https://www.pathofexile.com/api/trade2/fetch/{','.join(ids)}?query={search_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

# ========= New: deals_by_url helpers =========
TRADE_URL_RE = re.compile(
    r"/trade2/search/(?P<realm>[^/]+)/(?P<league>[^/]+)/(?P<qid>[^/?#]+)"
)

def parse_trade_url(url: str):
    m = TRADE_URL_RE.search(url)
    if not m:
        return None
    return m.group("realm"), m.group("league"), m.group("qid")

def api_search_by_id(realm: str, league_enc: str, qid: str) -> dict:
    url = f"https://www.pathofexile.com/api/trade2/search/{realm}/{league_enc}/{qid}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

# ========= Routes =========
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "realm": REALM,
        "league": LEAGUE_RAW,
        "default_item": DEFAULT_ITEM,
        "fetch_limit": FETCH_LIMIT,
    }

@app.get("/deals")
def deals(
    item: str = Query(None, description="Item name to search"),
    limit: int = Query(FETCH_LIMIT, ge=1, le=60),
):
    target_item = (item or DEFAULT_ITEM).strip()
    if not target_item:
        return {"items": [], "error": "missing_item"}
    try:
        search = post_search(target_item)
        search_id = search.get("id")
        result_ids = (search.get("result") or [])[:limit]
        if not search_id or not result_ids:
            return {"items": []}

        fetched = fetch_results(result_ids, search_id)
        results = fetched.get("result") or []
        mapped = [map_listing(r) for r in results]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        return {"items": [], "error": f"http_error:{code}"}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/deals_by_url")
def deals_by_url(url: str, limit: int = Query(FETCH_LIMIT, ge=1, le=60)):
    parts = parse_trade_url(url)
    if not parts:
        return {"items": [], "error": "bad_url"}

    realm, league_enc, qid = parts
    try:
        search = api_search_by_id(realm, league_enc, qid)
        ids = (search.get("result") or [])[:limit]
        if not ids:
            return {"items": []}

        fetched = fetch_results(ids, qid)
        results = fetched.get("result") or []
        mapped = [map_listing(r) for r in results]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        try:
            snippet = e.response.text[:160]
        except Exception:
            snippet = ""
        return {"items": [], "error": f"http_error:{code}", "details": snippet}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/history")
def history(id: str):
    return {"id": id, "history": []}
