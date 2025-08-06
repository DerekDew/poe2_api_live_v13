import time, random, statistics
from typing import List, Optional, Dict, Any
import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REALM: str = "poe2"
    LEAGUE: str = "Dawn of the Hunt"
    QUERY_ID: str = "lWPMj4jcV"
    USER_AGENT: str = "poe2-flips/0.13 (contact: you@example.com)"
    FETCH_LIMIT: int = 30
    DIVINE_TO_CHAOS: float = 180.0
    CORS_ORIGINS: str = "*"
    class Config: env_file = ".env"

S = Settings()

app = FastAPI(title="PoE2 Flips API (live)", version="0.13.0")
origins = [o.strip() for o in S.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

class Listing(BaseModel):
    id: str
    name: str
    slot: str
    price_chaos: float
    market_chaos: float
    seller: str
    listed_ago_min: int
    ilvl: Optional[int] = None
    url: Optional[str] = None

class ScoredItem(BaseModel):
    listing: Listing
    score: float

class DealsResponse(BaseModel):
    items: List[ScoredItem]

class Health(BaseModel):
    status: str
    time: float

class HistoryResponse(BaseModel):
    id: str
    points: list[float]

BASE = "https://www.pathofexile.com"
TRADE_PREFIX = "trade2" if S.REALM.lower().startswith("poe2") else "trade"
HEADERS = {"User-Agent": S.USER_AGENT, "Accept": "application/json"}

def price_to_chaos(price: Dict[str, Any]) -> Optional[float]:
    if not price: return None
    try:
        amt = float(price.get("amount", 0))
        cur = (price.get("currency") or "").lower()
        if cur in ("c","chaos"): return amt
        if cur in ("d","divine","div"): return amt * float(S.DIVINE_TO_CHAOS)
    except Exception: return None
    return None

def margin_pct(market: float, price: float)->float:
    if not market or market <= 0: return 0.0
    return max(0.0, (market - price) / market * 100.0)

def compute_score(l: Listing, w_margin=100.0, w_spread=0.5, w_vel=20.0)->float:
    m = margin_pct(l.market_chaos, l.price_chaos)
    spread = max(0.0, l.market_chaos - l.price_chaos)
    vel = w_vel if l.listed_ago_min <= 5 else (w_vel-10 if l.listed_ago_min <= 15 else (w_vel-15 if l.listed_ago_min<=60 else 0))
    return m*w_margin + spread*w_spread + max(0.0, vel)

async def get_result_ids(client: httpx.AsyncClient, page:int=1):
    path = f"/api/{TRADE_PREFIX}/search/"
    if S.REALM.lower().startswith("poe2"): path += "poe2/"
    path += f"{S.LEAGUE}"
    url = f"{BASE}{path}"
    r = await client.get(url, params={"id": S.QUERY_ID, "page": page}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return (r.json() or {}).get("result", [])

async def fetch_items(client: httpx.AsyncClient, ids):
    if not ids: return []
    id_str = ",".join(ids)
    path = f"/api/{TRADE_PREFIX}/fetch/"
    if S.REALM.lower().startswith("poe2"): path += "poe2/"
    path += id_str
    url = f"{BASE}{path}"
    r = await client.get(url, params={"query": S.QUERY_ID}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return (r.json() or {}).get("result", [])

def map_listing(node: Dict[str, Any]) -> Optional[Listing]:
    try:
        item = node.get("item", {}); listing = node.get("listing", {})
        name = item.get("name") or item.get("typeLine") or "Unknown"
        cat = item.get("category") or {}; slot = next(iter(cat.keys()), "item")
        chaos = price_to_chaos(listing.get("price") or {}) or 0.0
        account = (listing.get("account") or {}).get("lastCharacterName") or (listing.get("account") or {}).get("name") or "Seller"
        mins = random.randint(1, 180)
        ilvl = item.get("ilvl")
        url = f"https://www.pathofexile.com/trade2/search/{S.REALM}/{S.LEAGUE}/{S.QUERY_ID}?redirect&exact&offer={node.get('id')}"
        return Listing(id=node.get("id"), name=name, slot=slot, price_chaos=float(chaos),
                       market_chaos=0.0, seller=account, listed_ago_min=int(mins),
                       ilvl=ilvl, url=url)
    except Exception:
        return None

async def load_live_deals(limit:int):
    async with httpx.AsyncClient() as client:
        ids = await get_result_ids(client, page=1)
        ids = ids[:max(1, min(limit, len(ids)))]
        nodes = await fetch_items(client, ids)
        listings = [l for l in (map_listing(n) for n in nodes) if l and l.price_chaos>0]
        if not listings: return []
        prices = [l.price_chaos for l in listings]
        median_price = float(statistics.median(prices))
        for l in listings: l.market_chaos = median_price
        rows = [ScoredItem(listing=l, score=compute_score(l)) for l in listings]
        rows.sort(key=lambda s: s.score, reverse=True)
        return rows

@app.get("/health", response_model=Health)
def health(): return Health(status="ok", time=time.time())

@app.get("/deals", response_model=DealsResponse)
async def deals(limit: int = Query(S.FETCH_LIMIT, ge=1, le=60)):
    try:
        rows = await load_live_deals(limit)
        return DealsResponse(items=rows)
    except Exception:
        return DealsResponse(items=[])

@app.get("/history", response_model=HistoryResponse)
def history(id: str):
    base = 100.0
    pts = [round(max(1.0, base + (random.random()-0.5)*10),2) for _ in range(60)]
    return HistoryResponse(id=id, points=pts)
