import os
import re
from datetime import date, timedelta
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests
from capi import fetch_articles, build_summary

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

load_dotenv()

app = Flask(__name__)


@app.route("/")
def index():
    today = date.today()
    default_from = (today - timedelta(days=30)).isoformat()
    default_to = today.isoformat()
    return render_template("index.html", default_from=default_from, default_to=default_to)


@app.route("/api/search")
def search():
    api_key = os.environ.get("GUARDIAN_API_KEY")
    if not api_key:
        return jsonify({"error": "GUARDIAN_API_KEY environment variable is not set"}), 500

    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    desk = request.args.get("desk", "").strip() or None
    cl_str = request.args.get("commissioned_length", "").strip()

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    if not DATE_RE.match(from_date) or not DATE_RE.match(to_date):
        return jsonify({"error": "Dates must be in YYYY-MM-DD format"}), 400

    if from_date > to_date:
        return jsonify({"error": "from_date must be on or before to_date"}), 400

    commissioned_length_filter = None
    if cl_str:
        try:
            commissioned_length_filter = int(cl_str)
        except ValueError:
            return jsonify({"error": "commissioned_length must be an integer"}), 400

    try:
        result = fetch_articles(
            api_key=api_key,
            from_date=from_date,
            to_date=to_date,
            desk_filter=desk,
            commissioned_length_filter=commissioned_length_filter,
        )
    except requests.HTTPError as e:
        return jsonify({"error": f"CAPI request failed: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    articles = result["articles"]
    capped = result["capped"]
    summary = build_summary(articles)

    # Table rows has been raised to 2000 to check if this reduces performance
    return jsonify({
        "articles": articles[:2000],
        "total_fetched": len(articles),
        "capped": capped,
        "summary": summary,
    })


if __name__ == "__main__":
    app.run(debug=True)
