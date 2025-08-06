from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

POE2_API_BASE = "https://www.pathofexile.com/api/trade2"
DEFAULT_LEAGUE = "Dawn of the Hunt"

def fetch_trade_data(url):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch data from PoE2 API: {str(e)}"}

@app.route("/deals", methods=["GET"])
def get_deals():
    item_name = request.args.get("item")
    if not item_name:
        return jsonify({"error": "Missing 'item' parameter"}), 400

    try:
        # Example search: You may need to adapt to your PoE2 API endpoint
        search_url = f"{POE2_API_BASE}/search/{DEFAULT_LEAGUE}?q={item_name}"
        data = fetch_trade_data(search_url)

        if "error" in data:
            return jsonify(data), 500

        if not data.get("result"):
            return jsonify({
                "error": f"Unknown item name: '{item_name}' or no results found."
            }), 404

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/deals_by_url", methods=["GET"])
def get_deals_by_url():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        data = fetch_trade_data(url)
        if "error" in data:
            return jsonify(data), 500
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/deals_from_env", methods=["GET"])
def get_deals_from_env():
    query_id = os.getenv("QUERY_ID")
    if not query_id:
        return jsonify({"error": "QUERY_ID not set in environment"}), 500

    try:
        url = f"{POE2_API_BASE}/fetch/{query_id}?league={DEFAULT_LEAGUE}"
        data = fetch_trade_data(url)
        if "error" in data:
            return jsonify(data), 500
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
