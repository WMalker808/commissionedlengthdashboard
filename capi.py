import re
import requests
from typing import Optional

CAPI_BASE_URL = "https://content.guardianapis.com/search"
STANDARD_LENGTHS = {400, 650, 900, 1200}
MAX_PAGES = 50  # hard cap at ~10,000 articles per query


def _parse_article(raw: dict) -> dict:
    fields = raw.get("fields", {})
    tags = raw.get("tags", [])

    commissioning_desk = next(
        (t["webTitle"] for t in tags if t.get("type") == "tracking"),
        ""
    )

    wordcount_str = fields.get("wordcount")
    commissioned_str = fields.get("internalCommissionedWordcount")

    wordcount = int(wordcount_str) if wordcount_str else None
    commissioned_length = int(commissioned_str) if commissioned_str else None

    deviation = None
    if wordcount is not None and commissioned_length is not None and commissioned_length > 0:
        deviation = round(abs(wordcount - commissioned_length) / commissioned_length * 100, 1)

    return {
        "headline": fields.get("headline", ""),
        "creationDate": (fields.get("creationDate") or "")[:10],
        "publicationDate": (raw.get("webPublicationDate") or "")[:10],
        "webUrl": raw.get("webUrl", ""),
        "wordcount": wordcount,
        "commissionedLength": commissioned_length,
        "commissioningDesk": commissioning_desk,
        "deviation": deviation,
        "usesStandardLength": commissioned_length in STANDARD_LENGTHS if commissioned_length else False,
    }


def fetch_articles(
    api_key: str,
    from_date: str,
    to_date: str,
    desk_filter: Optional[str] = None,
    commissioned_length_filter: Optional[int] = None,
) -> dict:
    articles = []
    current_page = 1
    capped = False

    while True:
        params = {
            "api-key": api_key,
            "type": "article",
            "show-fields": "creationDate,wordcount,internalCommissionedWordcount,headline",
            "show-tags": "tracking",
            "page-size": "200",
            "from-date": from_date,
            "to-date": to_date,
            "page": str(current_page),
        }

        resp = requests.get(CAPI_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        response = data.get("response", {})
        results = response.get("results", [])
        total_pages = response.get("pages", 1)

        for raw in results:
            articles.append(_parse_article(raw))

        if current_page >= total_pages:
            break
        if current_page >= MAX_PAGES:
            capped = True
            break
        current_page += 1

    # Apply filters in Python
    if desk_filter:
        pattern = re.compile(r'\b' + re.escape(desk_filter) + r'\b', re.IGNORECASE)
        articles = [a for a in articles if pattern.search(a["commissioningDesk"])]

    if commissioned_length_filter is not None:
        articles = [a for a in articles if a["commissionedLength"] == commissioned_length_filter]

    return {"articles": articles, "capped": capped}


def build_summary(articles: list[dict]) -> dict:
    total = len(articles)
    if total == 0:
        return {
            "total": 0,
            "has_commissioned_length": 0,
            "pct_with_commissioned_length": 0,
            "pct_uses_standard_length": 0,
            "avg_wordcount": 0,
            "length_distribution": {},
            "by_date": [],
        }

    has_cl = sum(1 for a in articles if a["commissionedLength"] is not None)
    uses_standard = sum(1 for a in articles if a["usesStandardLength"])
    wordcounts = [a["wordcount"] for a in articles if a["wordcount"] is not None]
    avg_wc = round(sum(wordcounts) / len(wordcounts)) if wordcounts else 0

    # Length distribution
    length_dist: dict[str, int] = {}
    for a in articles:
        if a["commissionedLength"] is not None:
            key = str(a["commissionedLength"])
            length_dist[key] = length_dist.get(key, 0) + 1

    # Sort by count descending, take top 30
    length_dist = dict(
        sorted(length_dist.items(), key=lambda x: x[1], reverse=True)[:30]
    )

    # By creation date
    by_date_map: dict[str, dict] = {}
    for a in articles:
        d = a["creationDate"]
        if not d:
            continue
        if d not in by_date_map:
            by_date_map[d] = {"total": 0, "has_cl": 0, "wordcount_sum": 0, "wc_count": 0}
        by_date_map[d]["total"] += 1
        if a["commissionedLength"] is not None:
            by_date_map[d]["has_cl"] += 1
        if a["wordcount"] is not None:
            by_date_map[d]["wordcount_sum"] += a["wordcount"]
            by_date_map[d]["wc_count"] += 1

    by_date = [
        {
            "date": d,
            "total": v["total"],
            "has_cl": v["has_cl"],
            "pct": round(v["has_cl"] / v["total"], 4) if v["total"] else 0,
            "avg_wordcount": round(v["wordcount_sum"] / v["wc_count"]) if v["wc_count"] else 0,
        }
        for d, v in sorted(by_date_map.items())
    ]

    return {
        "total": total,
        "has_commissioned_length": has_cl,
        "pct_with_commissioned_length": round(has_cl / total, 4) if total else 0,
        "pct_uses_standard_length": round(uses_standard / total, 4) if total else 0,
        "avg_wordcount": avg_wc,
        "length_distribution": length_dist,
        "by_date": by_date,
    }
