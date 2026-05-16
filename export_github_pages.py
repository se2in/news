from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "finance_radar.sqlite3"
WORKFLOW_PAYLOAD_PATH = BASE_DIR / "workflow_payload.json"
DOCS_DIR = BASE_DIR / "docs"


def fetch_earnings_rows() -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT event_date, ticker, company, event_name, earnings_call_time,
                   eps_estimate, eps_actual, eps_surprise_pct, result_status,
                   market_cap, url, collected_at
            FROM earnings_results
            ORDER BY event_date DESC,
                     CASE result_status
                       WHEN 'Beat' THEN 1
                       WHEN 'Miss' THEN 2
                       WHEN 'Meet' THEN 3
                       WHEN '실제치 발표' THEN 4
                       WHEN '예정' THEN 5
                       ELSE 6
                     END,
                     ticker ASC
            LIMIT 3000
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def build_earnings_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_result: dict[str, int] = {}
    dates: list[str] = []
    for row in rows:
        status = row.get("result_status") or "미확인"
        by_result[status] = by_result.get(status, 0) + 1
        event_date = row.get("event_date")
        if event_date and event_date not in dates:
            dates.append(event_date)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total": len(rows),
            "by_result": by_result,
            "dates": dates[:60],
        },
        "rows": rows,
    }


def load_workflow_payload() -> dict[str, Any]:
    if not WORKFLOW_PAYLOAD_PATH.exists():
        return {}
    return json.loads(WORKFLOW_PAYLOAD_PATH.read_text(encoding="utf-8"))


def normalize_news_groups(groups: dict[str, Any], wanted_categories: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for category, items in groups.items():
        if wanted_categories and category not in wanted_categories:
            continue
        output[category] = [
            {
                "headline": item.get("headline", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "score": item.get("score", ""),
                "comments": item.get("comments", ""),
            }
            for item in (items or [])[:10]
        ]
    return output


def build_news_payload(workflow_payload: dict[str, Any]) -> dict[str, Any]:
    briefing = workflow_payload.get("briefing", {}) if isinstance(workflow_payload, dict) else {}
    return {
        "generated_at": workflow_payload.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_trends": briefing.get("market_trends", []),
        "featured_stocks": briefing.get("featured_stocks", {}),
        "news": {
            "naver": normalize_news_groups(briefing.get("naver_news", {})),
            "reddit": normalize_news_groups(briefing.get("reddit_news", {}), ["경제", "IT"]),
            "yahoo": normalize_news_groups(briefing.get("yahoo_news", {}), ["경제", "IT"]),
        },
    }


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"DB file not found: {DB_PATH}")

    DOCS_DIR.mkdir(exist_ok=True)
    earnings_payload = build_earnings_payload(fetch_earnings_rows())
    news_payload = build_news_payload(load_workflow_payload())

    (DOCS_DIR / "earnings.json").write_text(
        json.dumps(earnings_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS_DIR / "news.json").write_text(
        json.dumps(news_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"GitHub Pages earnings exported: {DOCS_DIR / 'earnings.json'}")
    print(f"GitHub Pages news exported: {DOCS_DIR / 'news.json'}")


if __name__ == "__main__":
    main()
