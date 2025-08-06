import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

# ===== Env Vars =====
REALM = os.getenv("REALM", "poe2")
LEAGUE = os.getenv("LEAGUE", "Dawn of the Hunt")
QUERY_ID = os.getenv("QUERY_ID", "")
USER_AGENT = os.getenv("USER_AGENT", "poe2-flips/0.13 (contact: you@example.com)")
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "30"))
DIVINE_TO_CHAOS = float(os.getenv("DIVINE_TO_CHAOS", "180"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

# ===== API Setup =====
app = FastAPI()

# CORS
if CORS_ORIGINS == "*":
    origins = ["*"]
else:
    origins = [o.strip() for o in CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Helper Functions =====
def fetch_trade_data():
    """Fetch raw trade data from PoE trade API."""
    if not QUERY_ID:
        return []

    url = f"https://www.pathofexile.com/api/trade2/fetch/{QUERY_ID}"
    search_url = f"https://www.pathofexile.com/api/trade2/search/{REALM}/{LEAGUE}/{QUERY_ID}"
    try:
        # Get search results
        search_resp = requests.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        search_resp.raise_for_status()
        data = search_resp.json()

        if "result" not in data or not data["result"]:
            return []

        # Limit results
        result_ids = data["result"][:FETCH_LIMIT]

        # Fetch details for the results
        fetch_url = f"https://www.pathofexile.com/api/trade2/fetch/{','.join(result_ids)}"
        fetch_resp = requests.get(fetch_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        fetch_resp.raise_for_status()
        fetched_data = fetch_resp.json()

        return fetched_data.get("result", [])

    except Exception as e:
        print("Error fetching trade data:", e)
        return []

def parse_deals(raw_items):
    """Parse trade API items into a simple list — no filtering."""
    deals = []
    for it in raw_items:
        listing = it.get("listing", {})
        price = listing.get("price", {})
        amount = price.get("amount")
        currency = price.get("currency")

        deals.append({
            "id": it.get("id"),
            "name": it.get("item", {}).get("name") or "",
            "baseType": it.get("item", {}).get("typeLine") or "",
            "price": amount,
            "currency": currency,
            "priceStr": f"{amount}{currency}" if amount and currency else "",
            "estimate": None,  # Placeholder — logic removed for simplicity
            "marginPct": None, # No margin filtering
            "score": None,     # No score filtering
            "seller": listing.get("account", {}).get("name", ""),
            "listedAt": listing.get("indexed"),
            "tradeUrl": f"https://www.pathofexile.com/trade2/search/{REALM}/{LEAGUE}/{QUERY_ID}"
        })
    return deals

# ===== Routes =====
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat(),
        "realm": REALM,
        "league": LEAGUE,
        "query_id": QUERY_ID
    }

@app.get("/deals")
def get_deals(limit: int = FETCH_LIMIT):
    raw_items = fetch_trade_data()
    deals = parse_deals(raw_items)
    # Just slice for requested limit
    return {"items": deals[:limit]}

@app.get("/history")
def history(id: str):
    # This is just a placeholder — history logic would be added here if needed
    return {"id": id, "history": []}
