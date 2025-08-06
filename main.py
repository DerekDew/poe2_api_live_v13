import os
import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# ===== Env config =====
REALM = os.getenv("REALM", "poe2")
LEAGUE_RAW = os.getenv("LEAGUE", "Dawn of the Hunt")            # plain text
LEAGUE_ENC = quote(LEAGUE_RAW, safe="")                         # encoded
DEFAULT_ITEM = os.getenv("DEFAULT_ITEM", "Scroll of Wisdom")
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "30"))
USER_AGENT = os.getenv("USER_AGENT", "poe2-flips/0.13 (contact: you@example.com)")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
QUERY_ID_ENV = (os.getenv("QUERY_ID", "") or "").strip()        # may be ID or full URL

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ===== App + CORS =====
app = FastAPI(title="PoE2 Flips API v13")

allow_origins = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Helpers =====
TRADE_URL_RE = re.compile(r"/trade2/search/(?P<realm>[^/]+)/(?P<league>[^/]+)/(?P<qid>[^/?#]+)")

def parse_trade_url(url_or_id: str) -> Optional[Tuple[str, str, str]]:
    """
    Accepts either a full PoE trade URL or a bare query id.
    Returns (realm, league_encoded, query_id) or None.
    """
    if not url_or_id:
        return None
    m = TRADE_URL_RE.search(url_or_id)
    if m:
        return m.group("realm"), m.group("league"), m.group("qid")
    # Treat as bare ID from env; use our REALM/LEAGUE
    if "/" not in url_or_id and len(url_or_id) >= 6:
        return REALM, LEAGUE_ENC, url_or_id
    return None

def poe_search_by_name(item_name: str) -> dict:
    url = f"https://www.pathofexile.com/api/trade2/search/{REALM}/{LEAGUE_ENC}"
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

def poe_search_by_id(realm: str, league_enc: str, qid: str) -> dict:
    url = f"https://www.pathofexile.com/api/trade2/search/{realm}/{league_enc}/{qid}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def poe_fetch(ids: List[str], qid: str) -> dict:
    if not ids:
        return {"result": []}
    url = f"https://www.pathofexile.com/api/trade2/fetch/{','.join(ids)}?query={qid}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def map_listing(res_item: dict) -> dict:
    listing = res_item.get("listing", {}) or {}
    item = res_item.get("item", {}) or {}
    price = listing.get("price", {}) or {}
    amount = price.get("amount")
    currency = price.get("currency")
    return {
        "id": res_item.get("id"),
        "name": item.get("name") or "",
        "baseType": item.get("typeLine") or "",
        "price": amount,
        "currency": currency,
        "priceStr": f"{amount}{currency}" if amount is not None and currency else "",
        "estimate": None,
        "marginPct": None,
        "score": None,
        "seller": (listing.get("account") or {}).get("name", ""),
        "listedAt": listing.get("indexed"),
        "tradeUrl": f"https://www.pathofexile.com/trade2/search/{REALM}/{LEAGUE_ENC}/{res_item.get('id','')}",
    }

# ===== Routes =====
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "realm": REALM,
        "league": LEAGUE_RAW,
        "league_enc": LEAGUE_ENC,
        "default_item": DEFAULT_ITEM,
        "has_query_id_env": bool(QUERY_ID_ENV),
        "fetch_limit": FETCH_LIMIT,
    }

@app.get("/deals")
def deals(item: Optional[str] = Query(None, description="Item name to search"),
          limit: int = Query(FETCH_LIMIT, ge=1, le=60)):
    """
    Dynamic search by item name (listed items, not bulk exchange).
    """
    target = (item or DEFAULT_ITEM).strip()
    if not target:
        return {"items": [], "error": "missing_item"}
    try:
        search = poe_search_by_name(target)
        qid = search.get("id")
        ids = (search.get("result") or [])[:limit]
        if not qid or not ids:
            return {"items": []}
        fetched = poe_fetch(ids, qid)
        mapped = [map_listing(r) for r in (fetched.get("result") or [])]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        details = ""
        try:
            details = (e.response.text or "")[:200]
        except Exception:
            pass
        return {"items": [], "error": f"http_error:{code}", "details": details}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/deals_from_env")
def deals_from_env(limit: int = Query(FETCH_LIMIT, ge=1, le=60)):
    """
    Uses QUERY_ID env, which may be a bare id (e.g. 'AbCd123')
    OR a full PoE trade URL. Automatically parses both.
    """
    parts = parse_trade_url(QUERY_ID_ENV)
    if not parts:
        return {"items": [], "error": "no_query_id_env"}
    realm, league_enc, qid = parts
    try:
        search = poe_search_by_id(realm, league_enc, qid)
        ids = (search.get("result") or [])[:limit]
        if not ids:
            return {"items": []}
        fetched = poe_fetch(ids, qid)
        mapped = [map_listing(r) for r in (fetched.get("result") or [])]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        details = ""
        try:
            details = (e.response.text or "")[:200]
        except Exception:
            pass
        return {"items": [], "error": f"http_error:{code}", "details": details}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/deals_by_url")
def deals_by_url(url: str, limit: int = Query(FETCH_LIMIT, ge=1, le=60)):
    """
    Pass a full trade URL exactly as seen in your browser.
    Example:
      /deals_by_url?url=https://www.pathofexile.com/trade2/search/poe2/Dawn%20of%20the%20Hunt/AbCd123&limit=10
    """
    parts = parse_trade_url(url)
    if not parts:
        return {"items": [], "error": "bad_url"}
    realm, league_enc, qid = parts
    try:
        search = poe_search_by_id(realm, league_enc, qid)
        ids = (search.get("result") or [])[:limit]
        if not ids:
            return {"items": []}
        fetched = poe_fetch(ids, qid)
        mapped = [map_listing(r) for r in (fetched.get("result") or [])]
        return {"items": mapped[:limit]}
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        details = ""
        try:
            details = (e.response.text or "")[:200]
        except Exception:
            pass
        return {"items": [], "error": f"http_error:{code}", "details": details}
    except Exception as e:
        return {"items": [], "error": f"exception:{type(e).__name__}"}

@app.get("/history")
def history(id: str):
    return {"id": id, "history": []}
