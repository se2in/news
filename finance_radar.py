from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from bs4 import MarkupResemblesLocatorWarning


KST = timezone(timedelta(hours=9))
NY_TZ = ZoneInfo("America/New_York")
DEFAULT_USER_AGENT = "DifyFinanceRadar/1.0 (+https://cloud.dify.ai)"
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

EARNINGS_DASHBOARD_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>유진증권 안상현 센터장의 기업실적 dash board</title>
  <style>
    :root { color-scheme: dark; font-family: Arial, "Malgun Gothic", sans-serif; --orange:#f59e0b; --bg:#050505; --panel:#101010; --grid:#2f2f2f; --text:#f3f4f6; --muted:#9ca3af; }
    body { margin: 0; background: var(--bg); color: var(--text); }
    header { padding: 18px 24px; border-bottom: 2px solid var(--orange); background: #000; display:flex; justify-content:space-between; align-items:flex-end; gap:16px; }
    h1 { margin: 0; font-size: 24px; color: var(--orange); letter-spacing: .2px; }
    .meta { color: var(--muted); font-size: 13px; }
    main { padding: 18px 24px; }
    .controls { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
    input, select { background: var(--panel); color: var(--text); border: 1px solid var(--grid); border-radius: 2px; padding: 9px 10px; }
    table { width: 100%; border-collapse: collapse; background: #070707; box-shadow: 0 0 0 1px var(--grid); }
    th, td { border-bottom: 1px solid #222; border-right: 1px solid #181818; padding: 9px 8px; text-align: left; font-size: 13px; vertical-align: top; }
    th { position: sticky; top: 0; background: #171717; color: var(--orange); z-index: 1; text-transform: uppercase; font-size: 12px; }
    tr:hover td { background:#111; }
    a { color: #60a5fa; text-decoration: none; }
    .badge { display: inline-block; min-width: 44px; text-align: center; border-radius: 999px; padding: 3px 8px; font-weight: 700; font-size: 12px; }
    .Beat { background: #064e3b; color: #a7f3d0; }
    .Miss { background: #7f1d1d; color: #fecaca; }
    .Meet { background: #374151; color: #e5e7eb; }
    .예정, .실제치발표 { background: #3b2f0b; color: #fde68a; }
    .num { white-space: nowrap; }
  </style>
</head>
<body>
  <header>
    <h1>유진증권 안상현 센터장의 기업실적 dash board</h1>
    <div class="meta" id="meta">loading...</div>
  </header>
  <main>
    <div class="controls">
      <input id="q" placeholder="티커/회사 검색">
      <select id="result">
        <option value="">전체 결과</option>
        <option value="Beat">Beat</option>
        <option value="Miss">Miss</option>
        <option value="Meet">Meet</option>
        <option value="예정">예정</option>
        <option value="실제치 발표">실제치 발표</option>
      </select>
      <select id="callTime">
        <option value="">전체 발표시간</option>
        <option value="AMC">AMC 장마감 후</option>
        <option value="BMO">BMO 장전</option>
        <option value="TNS">TNS 시간 미정</option>
      </select>
    </div>
    <table>
      <thead>
        <tr>
          <th>날짜</th>
          <th>티커/회사</th>
          <th>발표시간</th>
          <th>EPS 예상</th>
          <th>EPS 실제</th>
          <th>서프라이즈</th>
          <th>결과</th>
          <th>시총</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </main>
  <script>
    let allRows = [];
    const $ = id => document.getElementById(id);
    function cls(value) { return String(value || '').replaceAll(' ', ''); }
    function render() {
      const q = $('q').value.trim().toLowerCase();
      const result = $('result').value;
      const callTime = $('callTime').value;
      const rows = allRows.filter(r => {
        const hay = `${r.ticker} ${r.company}`.toLowerCase();
        return (!q || hay.includes(q)) && (!result || r.result_status === result) && (!callTime || r.earnings_call_time === callTime);
      });
      $('rows').innerHTML = rows.map(r => `
        <tr>
          <td class="num">${r.event_date || ''}</td>
          <td><a href="${r.url || '#'}" target="_blank" rel="noreferrer">${r.ticker || ''}</a><br>${r.company || ''}<br><span class="meta">${r.event_name || ''}</span></td>
          <td class="num">${r.earnings_call_time || ''}</td>
          <td class="num">${r.eps_estimate || '-'}</td>
          <td class="num">${r.eps_actual || '-'}</td>
          <td class="num">${r.eps_surprise_pct || '-'}</td>
          <td><span class="badge ${cls(r.result_status)}">${r.result_status || '-'}</span></td>
          <td class="num">${r.market_cap || '-'}</td>
        </tr>
      `).join('');
    }
    const embeddedData = __EARNINGS_DATA__;
    allRows = embeddedData.rows || [];
    $('meta').textContent = `생성시각: ${embeddedData.generated_at || '-'} / ${allRows.length}개`;
    render();
    ['q', 'result', 'callTime'].forEach(id => $(id).addEventListener('input', render));
  </script>
</body>
</html>
"""

KOREAN_STOPWORDS = {
    "관련",
    "기자",
    "뉴스",
    "분기",
    "오늘",
    "이번",
    "지난",
    "최근",
    "시장",
    "전망",
    "분석",
    "투자",
    "종목",
    "증시",
    "주식",
    "경제",
    "금융",
    "상승",
    "하락",
    "급등",
    "급락",
    "마감",
    "오전",
    "오후",
    "국내",
    "해외",
}

ENGLISH_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "ahead",
    "all",
    "already",
    "also",
    "although",
    "and",
    "analyst",
    "analysts",
    "annual",
    "any",
    "are",
    "around",
    "because",
    "been",
    "before",
    "best",
    "better",
    "business",
    "but",
    "buy",
    "call",
    "can",
    "conference",
    "could",
    "daily",
    "day",
    "did",
    "does",
    "down",
    "earnings",
    "for",
    "from",
    "good",
    "had",
    "has",
    "have",
    "high",
    "higher",
    "how",
    "into",
    "investing",
    "investor",
    "investors",
    "latest",
    "like",
    "just",
    "here",
    "there",
    "its",
    "it's",
    "me",
    "market",
    "markets",
    "more",
    "most",
    "my",
    "new",
    "news",
    "not",
    "now",
    "our",
    "out",
    "over",
    "portfolio",
    "price",
    "prices",
    "quarterly",
    "report",
    "reports",
    "rise",
    "rises",
    "say",
    "says",
    "share",
    "shares",
    "should",
    "stock",
    "stocks",
    "summary",
    "than",
    "that",
    "the",
    "their",
    "these",
    "they",
    "this",
    "thread",
    "today",
    "trading",
    "under",
    "was",
    "were",
    "what",
    "when",
    "why",
    "will",
    "with",
    "year",
    "years",
    "you",
    "your",
}


@dataclass(frozen=True)
class Item:
    source: str
    source_group: str
    title: str
    url: str
    summary: str = ""
    published_at: str | None = None
    author: str = ""
    score: int = 0
    comments: int = 0

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.url or self.title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def request_get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> requests.Response:
    merged = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(headers)
    response = requests.get(url, headers=merged, timeout=timeout)
    response.raise_for_status()
    return response


def parse_rss(xml_text: str, source: str, source_group: str) -> list[Item]:
    root = ElementTree.fromstring(xml_text)
    items: list[Item] = []
    for node in root.findall(".//item"):
        title = clean_text(node.findtext("title"))
        url = clean_text(node.findtext("link"))
        summary = clean_text(node.findtext("description"))
        pub_date = clean_text(node.findtext("pubDate"))
        published_at = None
        if pub_date:
            try:
                published_at = parsedate_to_datetime(pub_date).astimezone(KST).isoformat()
            except (TypeError, ValueError, IndexError):
                published_at = None
        if title and url:
            items.append(Item(source=source, source_group=source_group, title=title, url=url, summary=summary, published_at=published_at))
    return items


def collect_yahoo_finance(queries: list[str]) -> list[Item]:
    items: list[Item] = []
    for query in queries:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(query)}&region=US&lang=en-US"
        try:
            items.extend(parse_rss(request_get(url).text, "yahoo_finance", query))
        except Exception as exc:
            print(f"[warn] yahoo query failed: {query}: {exc}", file=sys.stderr)
    return items


def collect_naver_with_api(queries: list[str]) -> list[Item]:
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return []

    items: list[Item] = []
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    for query in queries:
        url = f"https://openapi.naver.com/v1/search/news.json?query={quote_plus(query)}&display=20&sort=date"
        try:
            data = request_get(url, headers=headers).json()
            for row in data.get("items", []):
                title = clean_text(row.get("title"))
                link = clean_text(row.get("originallink") or row.get("link"))
                summary = clean_text(row.get("description"))
                pub_date = clean_text(row.get("pubDate"))
                published_at = None
                if pub_date:
                    try:
                        published_at = parsedate_to_datetime(pub_date).astimezone(KST).isoformat()
                    except (TypeError, ValueError, IndexError):
                        published_at = None
                if title and link:
                    items.append(Item("naver_news", query, title, link, summary, published_at))
        except Exception as exc:
            print(f"[warn] naver api query failed: {query}: {exc}", file=sys.stderr)
    return items


def collect_naver_finance_public() -> list[Item]:
    urls = [
        ("naver_finance_main", "https://finance.naver.com/news/mainnews.naver"),
        ("naver_finance_ranking", "https://finance.naver.com/news/news_list.naver?mode=RANK"),
    ]
    items: list[Item] = []
    for group, url in urls:
        try:
            response = request_get(url, headers={"Referer": "https://finance.naver.com/"})
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("a"):
                title = clean_text(anchor.get_text(" ", strip=True))
                href = anchor.get("href", "")
                if len(title) < 8 or "news_read" not in href:
                    continue
                full_url = href if href.startswith("http") else f"https://finance.naver.com{href}"
                items.append(Item("naver_finance", group, title, full_url))
        except Exception as exc:
            print(f"[warn] naver finance page failed: {group}: {exc}", file=sys.stderr)
    return items


def collect_naver(queries: list[str]) -> list[Item]:
    api_items = collect_naver_with_api(queries)
    return api_items if api_items else collect_naver_finance_public()


def collect_reddit(subreddits: list[str], sorts: list[str], limit: int) -> list[Item]:
    items: list[Item] = []
    for subreddit in subreddits:
        for sort_name in sorts:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_name}.json?limit={int(limit)}"
            try:
                data = request_get(url, headers={"User-Agent": "DifyFinanceRadar/1.0 by local-script"}).json()
                for child in data.get("data", {}).get("children", []):
                    row = child.get("data", {})
                    title = clean_text(row.get("title"))
                    permalink = row.get("permalink", "")
                    summary = clean_text(row.get("selftext"))
                    created = row.get("created_utc")
                    published_at = datetime.fromtimestamp(created, tz=timezone.utc).astimezone(KST).isoformat() if created else None
                    if title and permalink:
                        items.append(
                            Item(
                                "reddit",
                                f"{subreddit}/{sort_name}",
                                title,
                                f"https://www.reddit.com{permalink}",
                                summary,
                                published_at,
                                author=clean_text(row.get("author")),
                                score=int(row.get("score") or 0),
                                comments=int(row.get("num_comments") or 0),
                            )
                        )
            except Exception as exc:
                print(f"[warn] reddit subreddit failed: {subreddit}/{sort_name}: {exc}", file=sys.stderr)
    return items


def news_record(title: str, url: str, source: str, category: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "source": source,
        "category": category,
        "headline": title,
        "url": url,
        "markdown": f"[{title}]({url})" if title and url else title,
    }
    if extra:
        record.update(extra)
    return record


def collect_naver_index(code: str, label: str) -> dict[str, Any]:
    url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    try:
        response = request_get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.encoding = "euc-kr"
        soup = BeautifulSoup(response.text, "html.parser")
        value = clean_text(soup.select_one("em#now_value").get_text(" ", strip=True) if soup.select_one("em#now_value") else "")
        change = clean_text(
            soup.select_one("span#change_value_and_rate").get_text(" ", strip=True)
            if soup.select_one("span#change_value_and_rate")
            else ""
        )
        if change:
            direction = "하락" if re.search(r"-\s*\d", change) else "상승" if re.search(r"\+\s*\d", change) else ""
            change = re.sub(r"\s*(상승|하락)\s*$", "", change).strip()
            change = f"{change} {direction}".strip()
        timestamp = ""
        content = soup.select_one("div#contentarea")
        if content:
            match = re.search(r"\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s+\S+", content.get_text(" ", strip=True))
            timestamp = match.group(0) if match else ""
        return {"name": label, "value": value, "change": change, "timestamp": timestamp, "url": url}
    except Exception as exc:
        print(f"[warn] naver index failed: {code}: {exc}", file=sys.stderr)
        return {"name": label, "value": "", "change": "", "timestamp": "", "url": url}


def collect_nasdaq_futures() -> dict[str, Any]:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?range=1d&interval=1m"
    try:
        data = request_get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0)
        previous = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
        change = price - previous if price and previous else 0
        change_pct = (change / previous * 100) if previous else 0
        return {
            "name": "미국 나스닥 선물 지수",
            "value": f"{price:,.2f}" if price else "",
            "change": f"{change:+,.2f} ({change_pct:+.2f}%)" if previous else "",
            "timestamp": datetime.fromtimestamp(int(meta.get("regularMarketTime") or 0), tz=timezone.utc).astimezone(KST).isoformat()
            if meta.get("regularMarketTime")
            else "",
            "url": "https://finance.yahoo.com/quote/NQ=F",
        }
    except Exception as exc:
        print(f"[warn] nasdaq futures failed: {exc}", file=sys.stderr)
        return {"name": "미국 나스닥 선물 지수", "value": "", "change": "", "timestamp": "", "url": "https://finance.yahoo.com/quote/NQ=F"}


def collect_yahoo_quote(symbol: str, label: str, url_symbol: str | None = None) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(symbol)}?range=1d&interval=1m"
    display_symbol = url_symbol or symbol
    try:
        data = request_get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0)
        previous = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
        change = price - previous if price and previous else 0
        change_pct = (change / previous * 100) if previous else 0
        return {
            "name": label,
            "value": f"{price:,.2f}" if price else "",
            "change": f"{change:+,.2f} ({change_pct:+.2f}%)" if previous else "",
            "timestamp": datetime.fromtimestamp(int(meta.get("regularMarketTime") or 0), tz=timezone.utc).astimezone(KST).isoformat()
            if meta.get("regularMarketTime")
            else "",
            "url": f"https://finance.yahoo.com/quote/{quote_plus(display_symbol)}",
        }
    except Exception as exc:
        print(f"[warn] yahoo quote failed: {symbol}: {exc}", file=sys.stderr)
        return {"name": label, "value": "", "change": "", "timestamp": "", "url": f"https://finance.yahoo.com/quote/{quote_plus(display_symbol)}"}


def collect_korea_night_futures() -> dict[str, Any]:
    url = "https://sonmul.kro.kr/"
    try:
        response = request_get(url, headers={"User-Agent": "Mozilla/5.0"})
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        match = re.search(
            r"KOSPI200_NIGHT\s+([0-9,]+(?:\.\d+)?)\s+([+-]\s*[0-9,]+(?:\.\d+)?)\s+([+-]\s*\d+(?:\.\d+)?%)",
            text,
        )
        if not match:
            match = re.search(
                r"코스피 야간선물.*?([0-9,]+(?:\.\d+)?)\s+([+-]\s*[0-9,]+(?:\.\d+)?)\s+([+-]\s*\d+(?:\.\d+)?%)",
                text,
            )
        if match:
            value = match.group(1)
            change_value = re.sub(r"\s+", "", match.group(2))
            change_pct = re.sub(r"\s+", "", match.group(3))
            return {
                "name": "한국 야간선물",
                "value": value,
                "change": f"{change_value} ({change_pct})",
                "timestamp": now_kst().isoformat(),
                "url": url,
            }
    except Exception as exc:
        print(f"[warn] korea night futures failed: {exc}", file=sys.stderr)
    return {"name": "한국 야간선물", "value": "", "change": "확인 필요", "timestamp": "", "url": url}


def collect_foreign_spot_flow() -> dict[str, Any]:
    day = now_kst().strftime("%Y%m%d")
    url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={day}&sosok=&page=1"
    try:
        response = request_get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.encoding = "euc-kr"
        soup = BeautifulSoup(response.text, "html.parser")
        for tr in soup.select("tr"):
            cols = [clean_text(td.get_text(" ", strip=True)) for td in tr.select("td")]
            if len(cols) >= 3 and re.match(r"\d{2}\.\d{2}\.\d{2}", cols[0]):
                foreign_value = cols[2]
                direction = "매도" if foreign_value.startswith("-") else "매수"
                return {
                    "name": "외국인 현물",
                    "value": foreign_value,
                    "change": f"{direction} 우위",
                    "unit": "억원",
                    "date": cols[0],
                    "url": url,
                }
    except Exception as exc:
        print(f"[warn] foreign spot flow failed: {exc}", file=sys.stderr)
    return {"name": "외국인 현물", "value": "", "change": "확인 필요", "unit": "억원", "date": "", "url": url}


def collect_market_trends() -> list[dict[str, Any]]:
    current = now_kst()
    minutes = current.hour * 60 + current.minute
    show_domestic_until = minutes <= 17 * 60
    show_global_overnight = minutes >= 17 * 60 or minutes < 7 * 60

    if show_domestic_until and not show_global_overnight:
        kospi = collect_naver_index("KOSPI", "KOSPI 지수")
        kosdaq = collect_naver_index("KOSDAQ", "KOSDAQ 지수")
        return [
            kospi,
            kosdaq,
            collect_nasdaq_futures(),
            collect_foreign_spot_flow(),
        ]

    return [
        collect_yahoo_quote("^DJI", "Dow 지수"),
        collect_yahoo_quote("^IXIC", "Nasdaq 지수"),
        collect_yahoo_quote("EWY", "EWY"),
        collect_korea_night_futures(),
    ]


def is_korea_market_open(moment: datetime | None = None) -> bool:
    current = moment or now_kst()
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    return 9 * 60 <= minutes <= 15 * 60 + 30


def is_us_market_open(moment: datetime | None = None) -> bool:
    current = (moment or now_kst()).astimezone(NY_TZ)
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def collect_korea_featured_stocks(limit: int = 10) -> dict[str, Any]:
    stocks: list[dict[str, Any]] = []
    markets = [("KOSPI", "0"), ("KOSDAQ", "1")]
    for market_name, sosok in markets:
        url = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}"
        try:
            response = request_get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.encoding = "euc-kr"
            soup = BeautifulSoup(response.text, "html.parser")
            for tr in soup.select("table.type_2 tr"):
                cols = [clean_text(td.get_text(" ", strip=True)) for td in tr.select("td")]
                link = tr.select_one("a[href*='/item/main.naver']")
                if len(cols) < 6 or not link:
                    continue
                href = link.get("href", "")
                code_match = re.search(r"code=(\d+)", href)
                code = code_match.group(1) if code_match else ""
                name = cols[1]
                if any(skip in name.upper() for skip in ("KODEX", "TIGER", "ACE", "SOL ", "KBSTAR", "HANARO", "ETF", "ETN")):
                    continue
                stocks.append(
                    {
                        "market": market_name,
                        "name": name,
                        "code": code,
                        "price": cols[2],
                        "change": cols[3],
                        "change_pct": cols[4],
                        "volume": cols[5],
                        "url": f"https://finance.naver.com/item/main.naver?code={code}" if code else url,
                        "markdown": f"[{name}]({'https://finance.naver.com/item/main.naver?code=' + code if code else url})",
                    }
                )
                if len(stocks) >= limit:
                    break
        except Exception as exc:
            print(f"[warn] korea featured stocks failed: {market_name}: {exc}", file=sys.stderr)
        if len(stocks) >= limit:
            break
    return {
        "session": "korea_regular",
        "title": "한국 장중 특징주",
        "description": "네이버금융 상승률 상위 종목 기준",
        "stocks": stocks[:limit],
    }


def collect_us_featured_stocks(limit: int = 10) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count={limit}"
    stocks: list[dict[str, Any]] = []
    try:
        data = request_get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        for quote in quotes[:limit]:
            symbol = clean_text(quote.get("symbol"))
            name = clean_text(quote.get("shortName") or quote.get("longName"))
            price = quote.get("regularMarketPrice")
            change_pct = quote.get("regularMarketChangePercent")
            volume = quote.get("regularMarketVolume")
            quote_url = f"https://finance.yahoo.com/quote/{quote_plus(symbol)}" if symbol else "https://finance.yahoo.com/screener/predefined/day_gainers"
            stocks.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
                    "volume": volume,
                    "url": quote_url,
                    "markdown": f"[{symbol} {name}]({quote_url})".strip(),
                }
            )
    except Exception as exc:
        print(f"[warn] us featured stocks failed: {exc}", file=sys.stderr)
    return {
        "session": "us_regular",
        "title": "미국 장중 특징주",
        "description": "Yahoo Finance Day Gainers 기준",
        "stocks": stocks,
    }


def collect_korea_after_close_featured_stocks(limit: int = 10) -> dict[str, Any]:
    data = collect_korea_featured_stocks(limit)
    data["session"] = "korea_after_close"
    data["title"] = "한국 마감 후 특징주"
    data["description"] = "장 마감 후에도 당일 상승률 상위 종목을 표시합니다."
    return data


def is_korea_after_close_window(moment: datetime | None = None) -> bool:
    current = moment or now_kst()
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    return 15 * 60 + 30 < minutes <= 21 * 60


def collect_featured_stocks(limit: int = 10) -> dict[str, Any]:
    current = now_kst()
    if is_korea_market_open(current):
        return collect_korea_featured_stocks(limit)
    if is_korea_after_close_window(current):
        return collect_korea_after_close_featured_stocks(limit)
    if is_us_market_open(current):
        return collect_us_featured_stocks(limit)
    return {
        "session": "closed",
        "title": "장중 특징주",
        "description": "현재 한국/미국 정규장 또는 한국 마감 후 특징주 표시 시간이 아닙니다.",
        "stocks": [],
    }


def collect_naver_popular_news(limit: int) -> dict[str, list[dict[str, Any]]]:
    sections = {"정치": "100", "경제": "101", "사회": "102", "생활": "103", "IT": "105", "세계": "104"}
    results: dict[str, list[dict[str, Any]]] = {}
    for category, section_id in sections.items():
        url = f"https://news.naver.com/section/{section_id}"
        category_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            response = request_get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("a.sa_text_title, a[href*='/mnews/article/']"):
                title = clean_text(anchor.get_text(" ", strip=True))
                href = anchor.get("href", "")
                if not title or href in seen or "/article/comment/" in href:
                    continue
                if len(title) < 8:
                    continue
                seen.add(href)
                category_items.append(news_record(title, href, "naver", category))
                if len(category_items) >= limit:
                    break
        except Exception as exc:
            print(f"[warn] naver popular news failed: {category}: {exc}", file=sys.stderr)
        results[category] = category_items
    return results


def collect_reddit_news_by_category(category_map: dict[str, list[str]], limit: int) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    for category, subreddits in category_map.items():
        category_items: list[dict[str, Any]] = []
        for subreddit in subreddits:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
            try:
                data = request_get(url, headers={"User-Agent": "DifyFinanceRadar/1.0 by local-script"}).json()
                for child in data.get("data", {}).get("children", []):
                    row = child.get("data", {})
                    title = clean_text(row.get("title"))
                    permalink = row.get("permalink", "")
                    if title and permalink:
                        category_items.append(
                            news_record(
                                title,
                                f"https://www.reddit.com{permalink}",
                                "reddit",
                                category,
                                {
                                    "subreddit": subreddit,
                                    "score": int(row.get("score") or 0),
                                    "comments": int(row.get("num_comments") or 0),
                                },
                            )
                        )
            except Exception as exc:
                print(f"[warn] reddit category news failed: {category}/{subreddit}: {exc}", file=sys.stderr)
        category_items.sort(key=lambda item: (int(item.get("score") or 0), int(item.get("comments") or 0)), reverse=True)
        results[category] = category_items[:limit]
    return results


def collect_yahoo_news_by_category(limit: int) -> dict[str, list[dict[str, Any]]]:
    feeds = {
        "정치": "https://news.yahoo.com/rss/politics",
        "경제": "https://finance.yahoo.com/news/rssindex",
        "사회": "https://news.yahoo.com/rss/us",
        "생활": "https://news.yahoo.com/rss/health",
        "IT": "https://news.yahoo.com/rss/tech",
        "세계": "https://news.yahoo.com/rss/world",
    }
    results: dict[str, list[dict[str, Any]]] = {}
    for category, url in feeds.items():
        items: list[dict[str, Any]] = []
        try:
            for item in parse_rss(request_get(url, headers={"User-Agent": "Mozilla/5.0"}).text, "yahoo", category)[:limit]:
                items.append(news_record(item.title, item.url, "yahoo", category, {"summary": item.summary}))
        except Exception as exc:
            print(f"[warn] yahoo category news failed: {category}: {exc}", file=sys.stderr)
        results[category] = items
    return results


def collect_yahoo_earnings(limit: int) -> list[dict[str, Any]]:
    today = now_kst().date().isoformat()
    url = f"https://query1.finance.yahoo.com/v1/finance/calendar/earnings?from={today}&to={today}&size={limit}"
    try:
        data = request_get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
        rows = data.get("finance", {}).get("result", [{}])[0].get("earnings", [])
        earnings: list[dict[str, Any]] = []
        for row in rows[:limit]:
            ticker = clean_text(row.get("ticker"))
            company = clean_text(row.get("companyshortname") or row.get("companyname"))
            earnings.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "headline": f"{ticker} {company}".strip(),
                    "url": f"https://finance.yahoo.com/quote/{ticker}" if ticker else "https://finance.yahoo.com/calendar/earnings",
                    "markdown": f"[{ticker} {company}](https://finance.yahoo.com/quote/{ticker})".strip() if ticker else company,
                    "start_datetime": row.get("startdatetime"),
                    "eps_estimate": row.get("epsestimate"),
                    "eps_actual": row.get("epsactual"),
                    "eps_surprise_pct": row.get("epssurprisepct"),
                    "result_status": classify_earnings_result(row.get("epsactual"), row.get("epsestimate")),
                }
            )
        return earnings
    except Exception as exc:
        print(f"[warn] yahoo earnings failed: {exc}", file=sys.stderr)
    fallback_url = f"https://finance.yahoo.com/calendar/earnings?day={today}"
    try:
        response = request_get(fallback_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")
        earnings = []
        for tr in soup.select("table tr")[1 : limit + 1]:
            cols = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.select("td")]
            if len(cols) < 2:
                continue
            ticker, company = cols[0], cols[1]
            earnings.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "headline": f"{ticker} {company}".strip(),
                    "url": f"https://finance.yahoo.com/quote/{ticker}" if ticker else fallback_url,
                    "markdown": f"[{ticker} {company}](https://finance.yahoo.com/quote/{ticker})".strip() if ticker else company,
                    "event_name": cols[2] if len(cols) > 2 else "",
                    "earnings_call_time": cols[3] if len(cols) > 3 else "",
                    "eps_estimate": cols[4] if len(cols) > 4 else "",
                    "eps_actual": cols[5] if len(cols) > 5 else "",
                    "eps_surprise_pct": cols[6] if len(cols) > 6 else "",
                    "market_cap": cols[7] if len(cols) > 7 else "",
                    "result_status": classify_earnings_result(cols[5] if len(cols) > 5 else "", cols[4] if len(cols) > 4 else ""),
                }
            )
        return earnings[:limit]
    except Exception as fallback_exc:
        print(f"[warn] yahoo earnings fallback failed: {fallback_exc}", file=sys.stderr)
        return []


def collect_yahoo_earnings_window(limit: int, lookback_days: int) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for offset in range(max(lookback_days, 0), -1, -1):
        date = (now_kst().date() - timedelta(days=offset)).isoformat()
        for row in collect_yahoo_earnings_for_day(date, limit):
            key = (row.get("ticker", ""), row.get("event_date", date))
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(row)
    all_rows.sort(key=lambda row: (0 if row.get("result_status") in {"Beat", "Miss", "Meet"} else 1, row.get("event_date", "")))
    return all_rows[:limit]


def collect_yahoo_earnings_for_day(day: str, limit: int) -> list[dict[str, Any]]:
    fallback_url = f"https://finance.yahoo.com/calendar/earnings?day={day}"
    try:
        response = request_get(fallback_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")
        earnings = []
        for tr in soup.select("table tr")[1 : limit + 1]:
            cols = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.select("td")]
            if len(cols) < 2:
                continue
            ticker, company = cols[0], cols[1]
            estimate = cols[4] if len(cols) > 4 else ""
            actual = cols[5] if len(cols) > 5 else ""
            surprise = cols[6] if len(cols) > 6 else ""
            earnings.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "headline": f"{ticker} {company}".strip(),
                    "url": f"https://finance.yahoo.com/quote/{ticker}" if ticker else fallback_url,
                    "markdown": f"[{ticker} {company}](https://finance.yahoo.com/quote/{ticker})".strip() if ticker else company,
                    "event_date": day,
                    "event_name": cols[2] if len(cols) > 2 else "",
                    "earnings_call_time": cols[3] if len(cols) > 3 else "",
                    "eps_estimate": estimate,
                    "eps_actual": actual,
                    "eps_surprise_pct": surprise,
                    "market_cap": cols[7] if len(cols) > 7 else "",
                    "result_status": classify_earnings_result(actual, estimate),
                }
            )
        return earnings[:limit]
    except Exception as exc:
        print(f"[warn] yahoo earnings day failed: {day}: {exc}", file=sys.stderr)
        return []


def clean_eps_value(value: Any) -> str:
    text = clean_text(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"-", "N/A", "na"}:
        return "-"
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    return text


def normalize_nasdaq_time(value: str) -> str:
    text = (value or "").lower()
    if "pre" in text or "before" in text:
        return "BMO"
    if "after" in text or "post" in text:
        return "AMC"
    if "not" in text or "unsupplied" in text:
        return "TAS"
    return clean_text(value).upper() or "TAS"


def collect_nasdaq_earnings_for_day(day: str, limit: int = 1000) -> list[dict[str, Any]]:
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={day}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/market-activity/earnings",
    }
    try:
        data = request_get(url, headers=headers, timeout=30).json()
        rows = data.get("data", {}).get("rows", []) or []
    except Exception as exc:
        print(f"[warn] nasdaq earnings failed: {day}: {exc}", file=sys.stderr)
        return []

    earnings: list[dict[str, Any]] = []
    for row in rows[:limit]:
        ticker = clean_text(row.get("symbol"))
        if not ticker:
            continue
        actual = clean_eps_value(row.get("eps"))
        estimate = clean_eps_value(row.get("epsForecast"))
        surprise = clean_eps_value(row.get("surprise"))
        company = clean_text(row.get("name"))
        fiscal_quarter = clean_text(row.get("fiscalQuarterEnding"))
        event_name = f"Earnings {fiscal_quarter}".strip()
        earnings.append(
            {
                "ticker": ticker,
                "company": company,
                "headline": f"{ticker} {company}".strip(),
                "url": f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/earnings",
                "markdown": f"[{ticker} {company}](https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/earnings)".strip(),
                "event_date": day,
                "event_name": event_name,
                "earnings_call_time": normalize_nasdaq_time(clean_text(row.get("time"))),
                "eps_estimate": estimate,
                "eps_actual": actual,
                "eps_surprise_pct": surprise,
                "market_cap": clean_text(row.get("marketCap")),
                "result_status": classify_earnings_result(actual, estimate),
            }
        )
    return earnings


def parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def classify_earnings_result(actual: Any, estimate: Any) -> str:
    actual_value = parse_optional_float(actual)
    estimate_value = parse_optional_float(estimate)
    if actual_value is None:
        return "예정"
    if estimate_value is None:
        return "실제치 발표"
    if actual_value > estimate_value:
        return "Beat"
    if actual_value < estimate_value:
        return "Miss"
    return "Meet"


def collect_briefing_data(config: dict[str, Any]) -> dict[str, Any]:
    news_limit = int(config.get("briefing_news_limit", 10))
    return {
        "market_trends": collect_market_trends(),
        "featured_stocks": collect_featured_stocks(news_limit),
        "naver_news": collect_naver_popular_news(news_limit),
        "reddit_news": collect_reddit_news_by_category(config.get("reddit_news_subreddits", {}), news_limit),
        "yahoo_news": collect_yahoo_news_by_category(news_limit),
        "yahoo_earnings": collect_yahoo_earnings_window(
            int(config.get("earnings_limit", 20)),
            int(config.get("earnings_lookback_days", 1)),
        ),
        "earnings_report_limit": int(config.get("earnings_report_limit", 10)),
    }


def md_link(title: str, url: str) -> str:
    safe_title = (title or "").replace("[", "\\[").replace("]", "\\]")
    return f"[{safe_title}]({url})" if url else safe_title


def render_news_group(grouped_news: dict[str, list[dict[str, Any]]]) -> list[str]:
    lines: list[str] = []
    for category in ("정치", "경제", "사회", "생활", "IT", "세계"):
        lines.append(category)
        items = grouped_news.get(category, [])
        if not items:
            lines.append("- 수집된 항목 없음")
        for index, item in enumerate(items[:10], start=1):
            lines.append(f"{index}. {md_link(item.get('headline', ''), item.get('url', ''))}")
        lines.append("")
    return lines


def render_selected_news_group(grouped_news: dict[str, list[dict[str, Any]]], categories: list[str]) -> list[str]:
    lines: list[str] = []
    for category in categories:
        lines.append(category)
        items = grouped_news.get(category, [])
        if not items:
            lines.append("- 수집된 항목 없음")
        for index, item in enumerate(items[:10], start=1):
            lines.append(f"{index}. {md_link(item.get('headline', ''), item.get('url', ''))}")
        lines.append("")
    return lines


def render_briefing_markdown(briefing: dict[str, Any]) -> str:
    lines: list[str] = ["[시장동향]"]
    for item in briefing.get("market_trends", []):
        timestamp = item.get("timestamp") or item.get("date") or ""
        unit = item.get("unit", "")
        value = f"{item.get('value', '')}{unit}" if unit and item.get("value") else item.get("value", "")
        lines.append(f"- {item.get('name', '')}: {value} / {item.get('change', '')} / 기준시각 {timestamp}")

    featured = briefing.get("featured_stocks", {})
    lines.extend(["", "[장중 특징주]", f"- {featured.get('title', '장중 특징주')}"])
    stocks = featured.get("stocks", [])
    if not stocks:
        lines.append("  - 현재 장중 특징주 없음")
    for stock in stocks[:10]:
        if featured.get("session") == "us_regular":
            label = f"{stock.get('symbol', '')} {stock.get('name', '')}".strip()
            lines.append(
                f"  - {md_link(label, stock.get('url', ''))} / {stock.get('price', '')} / "
                f"{stock.get('change_pct', '')}% / {stock.get('volume', '')}"
            )
        else:
            lines.append(
                f"  - {md_link(stock.get('name', ''), stock.get('url', ''))} / {stock.get('market', '')} / "
                f"{stock.get('price', '')} / {stock.get('change_pct', '')} / {stock.get('volume', '')}"
            )

    lines.extend(["", "[네이버 뉴스]"])
    lines.extend(render_news_group(briefing.get("naver_news", {})))

    lines.append("[레딧]")
    lines.extend(render_selected_news_group(briefing.get("reddit_news", {}), ["경제", "IT"]))

    lines.append("[야후]")
    lines.extend(render_selected_news_group(briefing.get("yahoo_news", {}), ["경제", "IT"]))

    lines.append("기업 실적 발표")
    earnings = briefing.get("yahoo_earnings", [])
    earnings_report_limit = int(briefing.get("earnings_report_limit", 10))
    if not earnings:
        lines.append("- 수집된 항목 없음")
    for index, item in enumerate(earnings[:earnings_report_limit], start=1):
        estimate = item.get("eps_estimate") or "-"
        actual = item.get("eps_actual") or "-"
        surprise = item.get("eps_surprise_pct") or "-"
        result = item.get("result_status") or "확인 필요"
        lines.append(
            f"{index}. {md_link(item.get('headline', ''), item.get('url', ''))} / "
            f"예상 {estimate} / 실제 {actual} / 서프라이즈 {surprise} / 결과 {result}"
        )

    lines.extend(["", "[종합내용]"])
    lines.extend(render_investment_ideas(briefing))
    lines.extend(
        [
            "",
            "[기업실적발표 대쉬보드]",
            "- 파일: earnings_dashboard.html",
            "- 경로: C:\\Users\\se2in\\Desktop\\destiny\\dify_finance_radar\\earnings_dashboard.html",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_investment_ideas(briefing: dict[str, Any]) -> list[str]:
    market_trends = briefing.get("market_trends", [])
    featured = briefing.get("featured_stocks", {})
    stocks = featured.get("stocks", [])
    naver_econ = briefing.get("naver_news", {}).get("경제", [])
    naver_it = briefing.get("naver_news", {}).get("IT", [])
    yahoo_econ = briefing.get("yahoo_news", {}).get("경제", [])
    yahoo_it = briefing.get("yahoo_news", {}).get("IT", [])
    earnings = briefing.get("yahoo_earnings", [])

    market_summary = []
    for item in market_trends:
        name = item.get("name", "")
        value = item.get("value", "")
        change = item.get("change", "")
        if name and value:
            market_summary.append(f"{name} {value}({change})")

    stock_names = ", ".join([stock.get("name") or stock.get("symbol", "") for stock in stocks[:5] if stock.get("name") or stock.get("symbol")])
    econ_titles = [item.get("headline", "") for item in (naver_econ[:2] + yahoo_econ[:2]) if item.get("headline")]
    it_titles = [item.get("headline", "") for item in (naver_it[:2] + yahoo_it[:2]) if item.get("headline")]
    earnings_names = ", ".join([item.get("ticker", "") for item in earnings[:5] if item.get("ticker")])
    important_earnings = []
    seen_important_tickers: set[str] = set()
    for item in earnings:
        ticker = item.get("ticker", "")
        if ticker in seen_important_tickers:
            continue
        if item.get("result_status") in {"Beat", "Miss"} or ticker in {"AMAT", "NVDA", "AMD", "TSLA", "AAPL", "MSFT", "GOOGL", "META", "AMZN"}:
            important_earnings.append(item)
            seen_important_tickers.add(ticker)
        if len(important_earnings) >= 5:
            break

    market_text = " / ".join(market_summary[:4]) if market_summary else "시장지표 수집값 확인 필요"
    idea_parts = []
    if stock_names:
        idea_parts.append(f"장중 강세 종목({stock_names})의 공통 재료와 거래량 지속 여부")
    if econ_titles:
        idea_parts.append(f"경제 뉴스 흐름({'; '.join(econ_titles[:2])})")
    if it_titles:
        idea_parts.append(f"IT/기술 뉴스 흐름({'; '.join(it_titles[:2])})")
    if earnings_names:
        idea_parts.append(f"실적 발표 예정/당일 기업({earnings_names})의 가이던스와 시간외 반응")
    if important_earnings:
        comments = []
        for item in important_earnings:
            comments.append(
                f"{item.get('ticker')} {item.get('result_status')} "
                f"(예상 {item.get('eps_estimate') or '-'}, 실제 {item.get('eps_actual') or '-'})"
            )
        idea_parts.append(f"중요 실적 체크: {', '.join(comments)}")

    risk_parts = [
        "외국인 현물 수급 방향이 지수와 엇갈리는지",
        "장중 특징주의 상한가/급등이 단일 뉴스성 수급인지",
        "야후/레딧 해외 뉴스가 국내 업종에 실제 매출 또는 비용 영향으로 이어지는지",
    ]

    return [
        f"- 시장 해석: {market_text}. 수집된 시장동향과 뉴스 흐름을 함께 보면, 지수 방향과 외국인 수급, 장중 강세 종목의 재료를 분리해서 확인할 필요가 있습니다.",
        f"- 주식투자로 이어질 아이디어: {'; '.join(idea_parts) if idea_parts else '수집된 뉴스와 특징주를 기준으로 업종별 재료를 추가 확인하세요.'}",
        f"- 확인해야 할 리스크: {'; '.join(risk_parts)}",
    ]


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_group TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            score INTEGER NOT NULL DEFAULT 0,
            comments INTEGER NOT NULL DEFAULT 0,
            published_at TEXT,
            collected_at TEXT NOT NULL,
            raw_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS keyword_daily (
            day TEXT NOT NULL,
            keyword TEXT NOT NULL,
            source TEXT NOT NULL,
            mentions INTEGER NOT NULL,
            avg_score REAL NOT NULL DEFAULT 0,
            avg_comments REAL NOT NULL DEFAULT 0,
            sample_titles TEXT NOT NULL,
            PRIMARY KEY (day, keyword, source)
        );

        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            yahoo_count INTEGER NOT NULL DEFAULT 0,
            naver_count INTEGER NOT NULL DEFAULT 0,
            reddit_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS earnings_results (
            event_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            company TEXT NOT NULL DEFAULT '',
            event_name TEXT NOT NULL DEFAULT '',
            earnings_call_time TEXT NOT NULL DEFAULT '',
            eps_estimate TEXT NOT NULL DEFAULT '',
            eps_actual TEXT NOT NULL DEFAULT '',
            eps_surprise_pct TEXT NOT NULL DEFAULT '',
            result_status TEXT NOT NULL DEFAULT '',
            market_cap TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL,
            PRIMARY KEY (event_date, ticker)
        );
        """
    )
    try:
        conn.execute("ALTER TABLE keyword_daily ADD COLUMN avg_comments REAL NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def save_earnings_results(conn: sqlite3.Connection, earnings: list[dict[str, Any]]) -> int:
    collected_at = now_kst().isoformat()
    rows = [
        (
            item.get("event_date", ""),
            item.get("ticker", ""),
            item.get("company", ""),
            item.get("event_name", ""),
            item.get("earnings_call_time", ""),
            str(item.get("eps_estimate", "")),
            str(item.get("eps_actual", "")),
            str(item.get("eps_surprise_pct", "")),
            item.get("result_status", ""),
            item.get("market_cap", ""),
            item.get("url", ""),
            collected_at,
        )
        for item in earnings
        if item.get("event_date") and item.get("ticker")
    ]
    before = conn.total_changes
    conn.executemany(
        """
        INSERT INTO earnings_results
        (event_date, ticker, company, event_name, earnings_call_time, eps_estimate, eps_actual,
         eps_surprise_pct, result_status, market_cap, url, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_date, ticker) DO UPDATE SET
            company = excluded.company,
            event_name = excluded.event_name,
            earnings_call_time = excluded.earnings_call_time,
            eps_estimate = excluded.eps_estimate,
            eps_actual = CASE
                WHEN excluded.eps_actual NOT IN ('', '-') OR earnings_results.eps_actual IN ('', '-')
                THEN excluded.eps_actual
                ELSE earnings_results.eps_actual
            END,
            eps_surprise_pct = CASE
                WHEN excluded.eps_actual NOT IN ('', '-') OR earnings_results.eps_actual IN ('', '-')
                THEN excluded.eps_surprise_pct
                ELSE earnings_results.eps_surprise_pct
            END,
            result_status = CASE
                WHEN excluded.eps_actual NOT IN ('', '-') OR earnings_results.eps_actual IN ('', '-')
                THEN excluded.result_status
                ELSE earnings_results.result_status
            END,
            market_cap = excluded.market_cap,
            url = excluded.url,
            collected_at = excluded.collected_at
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def sync_recent_earnings_from_nasdaq(conn: sqlite3.Connection, days: int) -> int:
    total = 0
    today = now_kst().date()
    for offset in range(max(days, 0), -1, -1):
        event_date = (today - timedelta(days=offset)).isoformat()
        nasdaq_rows = collect_nasdaq_earnings_for_day(event_date, 1000)
        if nasdaq_rows:
            total += save_earnings_results(conn, nasdaq_rows)
    return total


def load_recent_earnings_from_db(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_date, ticker, company, event_name, earnings_call_time,
               eps_estimate, eps_actual, eps_surprise_pct, result_status,
               market_cap, url, collected_at
        FROM earnings_results
        WHERE event_date IN (
            SELECT DISTINCT event_date
            FROM earnings_results
            ORDER BY event_date DESC
            LIMIT 2
        )
        ORDER BY event_date DESC,
                 CASE result_status
                   WHEN 'Beat' THEN 1
                   WHEN 'Miss' THEN 2
                   WHEN 'Meet' THEN 3
                   WHEN '실제치 발표' THEN 4
                   WHEN '예정' THEN 5
                   ELSE 6
                 END,
                 market_cap DESC,
                 ticker ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        ticker = item.get("ticker", "")
        company = item.get("company", "")
        item["headline"] = f"{ticker} {company}".strip()
        item["markdown"] = md_link(item["headline"], item.get("url", ""))
        results.append(item)
    return results


def export_earnings_dashboard(conn: sqlite3.Connection, base_dir: Path) -> None:
    rows = conn.execute(
        """
        SELECT event_date, ticker, company, event_name, earnings_call_time, eps_estimate, eps_actual,
               eps_surprise_pct, result_status, market_cap, url, collected_at
        FROM earnings_results
        ORDER BY event_date DESC, result_status ASC, market_cap DESC, ticker ASC
        LIMIT 1000
        """
    ).fetchall()
    data = {
        "generated_at": now_kst().isoformat(),
        "rows": [dict(row) for row in rows],
    }
    (base_dir / "earnings_dashboard_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = base_dir / "earnings_dashboard.html"
    html = EARNINGS_DASHBOARD_HTML.replace("__EARNINGS_DATA__", json.dumps(data, ensure_ascii=False))
    html_path.write_text(html, encoding="utf-8")


def save_items(conn: sqlite3.Connection, items: list[Item]) -> int:
    collected_at = now_kst().isoformat()
    rows = [
        (
            item.uid,
            item.source,
            item.source_group,
            item.title,
            item.url,
            item.summary,
            item.author,
            item.score,
            item.comments,
            item.published_at,
            collected_at,
            f"{item.title} {item.summary}".strip(),
        )
        for item in items
    ]
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO items
        (id, source, source_group, title, url, summary, author, score, comments, published_at, collected_at, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def extract_tickers(text: str, tickers: list[str]) -> list[str]:
    found: list[str] = []
    for ticker in tickers:
        pattern = re.compile(rf"(?<![A-Za-z0-9])\$?{re.escape(ticker)}(?![A-Za-z0-9])", re.IGNORECASE)
        if pattern.search(text):
            found.append(ticker.upper())
    return sorted(set(found))


def normalize_english_phrase(phrase: str) -> str:
    upper = phrase.upper()
    if 2 <= len(upper) <= 6 and upper == phrase:
        return upper
    return " ".join(word.upper() if word.upper() == word and len(word) <= 6 else word.title() for word in phrase.split())


def extract_candidate_keywords(text: str, tickers: list[str]) -> set[str]:
    candidates: set[str] = set(extract_tickers(text, tickers))

    for token in re.findall(r"[가-힣]{2,12}", text):
        if token in KOREAN_STOPWORDS:
            continue
        candidates.add(token)

    english_tokens = re.findall(r"[A-Za-z][A-Za-z0-9&.-]{1,24}", text)
    cleaned: list[str] = []
    for raw_token in english_tokens:
        normalized = raw_token.strip(".-").lower()
        if len(normalized) < 3 or normalized in ENGLISH_STOPWORDS:
            continue
        if normalized.startswith(("http", "www")):
            continue
        if raw_token.strip(".-").isupper() and 2 <= len(raw_token.strip(".-")) <= 6:
            candidates.add(raw_token.strip(".-").upper())
        cleaned.append(normalized)

    for token in cleaned:
        if token.upper() in tickers:
            candidates.add(token.upper())

    for size in (2, 3):
        for index in range(0, max(len(cleaned) - size + 1, 0)):
            phrase_tokens = cleaned[index : index + size]
            if any(token in ENGLISH_STOPWORDS for token in phrase_tokens):
                continue
            phrase = " ".join(phrase_tokens)
            candidates.add(normalize_english_phrase(phrase))

    return {candidate for candidate in candidates if 2 <= len(candidate) <= 60}


def refresh_keyword_daily(conn: sqlite3.Connection, config: dict[str, Any], day: str) -> None:
    tickers = config.get("tickers", [])
    min_mentions = int(config.get("dynamic_keyword_min_mentions", 2))
    start = f"{day}T00:00:00"
    end = (datetime.fromisoformat(day).date() + timedelta(days=1)).isoformat() + "T00:00:00"
    rows = conn.execute(
        """
        SELECT source, title, raw_text, score, comments
        FROM items
        WHERE collected_at >= ? AND collected_at < ?
        """,
        (start, end),
    ).fetchall()

    stats: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        text = row["title"]
        for keyword in extract_candidate_keywords(text, tickers):
            key = (keyword, row["source"])
            bucket = stats.setdefault(key, {"mentions": 0, "score_sum": 0, "comments_sum": 0, "titles": []})
            bucket["mentions"] += 1
            bucket["score_sum"] += int(row["score"] or 0)
            bucket["comments_sum"] += int(row["comments"] or 0)
            if len(bucket["titles"]) < 5:
                bucket["titles"].append(row["title"])

    conn.execute("DELETE FROM keyword_daily WHERE day = ?", (day,))
    conn.executemany(
        """
        INSERT INTO keyword_daily (day, keyword, source, mentions, avg_score, avg_comments, sample_titles)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                day,
                keyword,
                source,
                data["mentions"],
                data["score_sum"] / max(data["mentions"], 1),
                data["comments_sum"] / max(data["mentions"], 1),
                json.dumps(data["titles"], ensure_ascii=False),
            )
            for (keyword, source), data in stats.items()
            if data["mentions"] >= min_mentions
        ],
    )
    conn.commit()


def build_payload(conn: sqlite3.Connection, config: dict[str, Any], day: str, briefing_data: dict[str, Any] | None = None) -> dict[str, Any]:
    lookback_days = int(config.get("lookback_days", 2))
    tickers = config.get("tickers", [])
    top_n = int(config.get("top_n", 5))

    today_rows = conn.execute(
        """
        SELECT keyword, source, mentions, avg_score, avg_comments, sample_titles
        FROM keyword_daily
        WHERE day = ?
        ORDER BY mentions DESC
        """,
        (day,),
    ).fetchall()
    previous_rows = conn.execute(
        """
        SELECT keyword, SUM(mentions) AS mentions
        FROM keyword_daily
        WHERE day >= ? AND day < ?
        GROUP BY keyword
        """,
        ((datetime.fromisoformat(day).date() - timedelta(days=lookback_days)).isoformat(), day),
    ).fetchall()
    previous_by_keyword = {row["keyword"]: int(row["mentions"] or 0) / max(lookback_days, 1) for row in previous_rows}
    previous_reddit_rows = conn.execute(
        """
        SELECT keyword, AVG(avg_score) AS avg_score, AVG(avg_comments) AS avg_comments
        FROM keyword_daily
        WHERE day >= ? AND day < ? AND source = 'reddit'
        GROUP BY keyword
        """,
        ((datetime.fromisoformat(day).date() - timedelta(days=lookback_days)).isoformat(), day),
    ).fetchall()
    previous_reddit_by_keyword = {
        row["keyword"]: {"avg_score": float(row["avg_score"] or 0), "avg_comments": float(row["avg_comments"] or 0)}
        for row in previous_reddit_rows
    }

    grouped: dict[str, dict[str, Any]] = {}
    for row in today_rows:
        bucket = grouped.setdefault(
            row["keyword"],
            {
                "keyword": row["keyword"],
                "mentions": 0,
                "sources": {},
                "sample_titles": [],
                "avg_reddit_score": 0.0,
                "avg_reddit_comments": 0.0,
            },
        )
        mentions = int(row["mentions"])
        bucket["mentions"] += mentions
        bucket["sources"][row["source"]] = mentions
        titles = json.loads(row["sample_titles"] or "[]")
        bucket["sample_titles"].extend(titles[:3])
        if row["source"] == "reddit":
            bucket["avg_reddit_score"] = float(row["avg_score"] or 0)
            bucket["avg_reddit_comments"] = float(row["avg_comments"] or 0)

    items = conn.execute(
        """
        SELECT source, source_group, title, url, summary, score, comments, raw_text
        FROM items
        WHERE collected_at >= ? AND collected_at < ?
        ORDER BY score DESC, collected_at DESC
        LIMIT 200
        """,
        (f"{day}T00:00:00", (datetime.fromisoformat(day).date() + timedelta(days=1)).isoformat() + "T00:00:00"),
    ).fetchall()

    top_themes: list[dict[str, Any]] = []
    for keyword, bucket in grouped.items():
        previous_avg = previous_by_keyword.get(keyword, 0)
        surge_pct = None if previous_avg <= 0 else round(((bucket["mentions"] - previous_avg) / previous_avg) * 100, 1)
        previous_reddit = previous_reddit_by_keyword.get(keyword, {"avg_score": 0.0, "avg_comments": 0.0})
        score_base = previous_reddit["avg_score"]
        comments_base = previous_reddit["avg_comments"]
        reddit_score_surge_pct = None if score_base <= 0 else round(((bucket["avg_reddit_score"] - score_base) / score_base) * 100, 1)
        reddit_comments_surge_pct = (
            None if comments_base <= 0 else round(((bucket["avg_reddit_comments"] - comments_base) / comments_base) * 100, 1)
        )
        related_text = " ".join([item["raw_text"] for item in items if keyword.lower() in item["raw_text"].lower()])
        related_tickers = extract_tickers(related_text, tickers)
        early_theme_signal = bool(
            (surge_pct is not None and surge_pct >= 100)
            or (reddit_score_surge_pct is not None and reddit_score_surge_pct >= 100)
            or (reddit_comments_surge_pct is not None and reddit_comments_surge_pct >= 100)
            or (bucket["sources"].get("reddit", 0) >= 3 and bucket["avg_reddit_comments"] >= 20)
        )
        top_themes.append(
            {
                "theme": keyword,
                "mentions": bucket["mentions"],
                "surge_pct": surge_pct,
                "sources": bucket["sources"],
                "related_tickers": related_tickers,
                "avg_reddit_score": round(bucket["avg_reddit_score"], 2),
                "avg_reddit_comments": round(bucket["avg_reddit_comments"], 2),
                "reddit_score_surge_pct": reddit_score_surge_pct,
                "reddit_comments_surge_pct": reddit_comments_surge_pct,
                "early_theme_signal": early_theme_signal,
                "sample_titles": list(dict.fromkeys(bucket["sample_titles"]))[:5],
            }
        )
    top_themes.sort(key=lambda row: (row["mentions"], row["surge_pct"] or 0), reverse=True)

    raw_by_source: dict[str, list[dict[str, Any]]] = {"reddit": [], "naver_news": [], "naver_finance": [], "yahoo_finance": []}
    for item in items:
        raw_by_source.setdefault(item["source"], []).append(
            {
                "group": item["source_group"],
                "title": item["title"],
                "url": item["url"],
                "summary": item["summary"],
                "score": item["score"],
                "comments": item["comments"],
                "engagement": int(item["score"] or 0) + int(item["comments"] or 0) * 2,
            }
        )

    briefing_markdown = render_briefing_markdown(briefing_data or {}) if briefing_data else ""

    return {
        "date": day,
        "generated_at": now_kst().isoformat(),
        "briefing": briefing_data or {},
        "briefing_markdown": briefing_markdown,
        "top_themes": top_themes[:top_n],
        "radar_payload": {
            "briefing": briefing_data or {},
            "briefing_markdown": briefing_markdown,
            "top_themes": top_themes[:top_n],
            "raw_by_source": raw_by_source,
            "instructions_for_dify": [
                "시장동향, 네이버 뉴스, 레딧, 야후 뉴스, 야후 실적 발표를 지정된 형식으로 정리하라.",
                "뉴스는 헤드라인만 Markdown 링크 형식으로 보여줘라.",
                "감성은 긍정/중립/부정과 근거를 함께 제시하라.",
                "투자 조언이 아니라 관찰된 이슈와 리스크를 분리해 작성하라.",
            ],
        },
        "reddit_data": raw_by_source.get("reddit", []),
        "naver_news_data": raw_by_source.get("naver_news", []) + raw_by_source.get("naver_finance", []),
        "yahoo_finance_data": raw_by_source.get("yahoo_finance", []),
        "telegram_data": [],
    }


def render_report(payload: dict[str, Any]) -> str:
    if payload.get("briefing_markdown"):
        return payload["briefing_markdown"]
    lines = ["[금일 AI 금융 이슈 레이더]", ""]
    themes = payload.get("top_themes", [])
    if not themes:
        lines.append("오늘 설정된 키워드에서 유의미한 언급이 아직 감지되지 않았습니다.")
    for index, theme in enumerate(themes, start=1):
        surge = "신규/기준 없음" if theme.get("surge_pct") is None else f"+{theme['surge_pct']}%"
        tickers = ", ".join(theme.get("related_tickers") or ["추출 대기"])
        sources = theme.get("sources", {})
        lines.extend(
            [
                f"{index}. {theme['theme']}",
                f"- 총 언급: {theme['mentions']}회",
                f"- 전일/최근 평균 대비: {surge}",
                f"- 소스: Reddit {sources.get('reddit', 0)} / Yahoo {sources.get('yahoo_finance', 0)} / Naver {sources.get('naver_news', 0) + sources.get('naver_finance', 0)}",
                f"- 관련 종목: {tickers}",
                f"- 레딧 평균 추천/댓글: {theme.get('avg_reddit_score', 0)} / {theme.get('avg_reddit_comments', 0)}",
                f"- 초기 테마 신호: {'있음' if theme.get('early_theme_signal') else '없음'}",
            ]
        )
        samples = theme.get("sample_titles", [])
        if samples:
            lines.append(f"- 대표 제목: {samples[0]}")
        lines.append("")
    lines.extend(
        [
            "[오늘의 결론]",
            "이 리포트는 Dify 전달 전의 1차 빈도/급증 탐지 결과입니다. 최종 감성, 요약, 투자 시사점은 Dify LLM 노드에서 생성하세요.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def call_dify(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("DIFY_API_KEY", "")
    workflow_url = os.getenv("DIFY_WORKFLOW_URL", "https://api.dify.ai/v1/workflows/run")
    user = os.getenv("DIFY_USER", "finance-radar")
    if not api_key:
        raise RuntimeError("DIFY_API_KEY is empty")
    dify_payload = {
        "briefing": payload.get("briefing", {}),
        "briefing_markdown": payload.get("briefing_markdown", ""),
    }
    response = requests.post(
        workflow_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "inputs": {
                "telegram_data": "",
                "reddit_data": "",
                "naver_news_data": "",
                "yahoo_finance_data": "",
                "radar_payload": json.dumps(dify_payload, ensure_ascii=False),
            },
            "response_mode": "blocking",
            "user": user,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def extract_dify_result(dify_response: dict[str, Any]) -> str:
    data = dify_response.get("data", {})
    outputs = data.get("outputs", {}) if isinstance(data, dict) else {}
    for key in ("result", "text", "answer"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if data.get("error"):
        return f"Dify workflow failed: {data.get('error')}"
    return json.dumps(data or dify_response, ensure_ascii=False, indent=2)


def send_telegram(message: str) -> None:
    token = os.getenv("TELE_CRAWLING_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELE_CRAWLING_ID") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("TELE_CRAWLING_TOKEN or TELE_CRAWLING_ID is empty")
    chunks = split_telegram_message(message)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"({index}/{len(chunks)})\n" if len(chunks) > 1 else ""
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": prefix + chunk, "disable_web_page_preview": True},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Telegram send failed: HTTP {response.status_code} {response.text}")


def append_dashboard_link(message: str) -> str:
    dashboard_url = os.getenv("EARNINGS_DASHBOARD_URL", "https://se2in.github.io/news/").strip()
    if not dashboard_url or dashboard_url in message:
        return message
    return f"{message.rstrip()}\n\n━━━━━━━━━━━━━━━━━━━━\n통합 대시보드\n{dashboard_url}"


def strip_local_dashboard_block(message: str) -> str:
    lines = message.splitlines()
    cleaned: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped in {"[기업실적발표 대쉬보드]", "[기업실적발표 대시보드]"}:
            skipping = True
            continue
        if skipping:
            if not stripped:
                skipping = False
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def beautify_telegram_sections(message: str) -> str:
    section_titles = {
        "[시장동향]": "시장동향",
        "[장중 특징주]": "장중 특징주",
        "[네이버 뉴스]": "네이버 뉴스",
        "[레딧]": "레딧",
        "[야후]": "야후",
        "기업 실적 발표": "기업 실적 발표",
        "[종합내용]": "종합내용",
    }
    lines: list[str] = []
    for line in message.splitlines():
        stripped = line.strip()
        if stripped in section_titles:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(section_titles[stripped])
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def format_telegram_report(message: str) -> str:
    title = "유진증권 안상현 센터장의 AI NEWS BOT BRIEF"
    generated_at = now_kst().strftime("%Y-%m-%d %H:%M")
    body = strip_local_dashboard_block(message.lstrip())
    body = beautify_telegram_sections(body)
    if body.startswith(title):
        return append_dashboard_link(body)
    header = "\n".join(
        [
            title,
            f"기준시각: {generated_at} KST",
            "시장, 뉴스, 실적을 한 번에 보는 데일리 브리핑",
        ]
    )
    return append_dashboard_link(f"{header}\n\n{body}")


def split_telegram_message(message: str, limit: int = 3500) -> list[str]:
    if len(message) <= limit:
        return [message]
    chunks: list[str] = []
    remaining = message
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


def run(config_path: Path, send_dify: bool, send_tg: bool) -> None:
    load_env(config_path.with_name(".env"))
    config = load_config(config_path)
    base_dir = config_path.parent
    db_path = base_dir / config.get("database_path", "finance_radar.sqlite3")
    day = now_kst().date().isoformat()

    conn = connect_db(db_path)
    init_db(conn)
    started_at = now_kst().isoformat()
    run_id = conn.execute("INSERT INTO runs (started_at, status) VALUES (?, ?)", (started_at, "running")).lastrowid
    conn.commit()

    try:
        yahoo_items = collect_yahoo_finance(config.get("yahoo_queries", []))
        naver_items = collect_naver(config.get("naver_queries", []))
        reddit_items = collect_reddit(
            config.get("reddit_subreddits", []),
            config.get("reddit_sorts", ["hot", "new", "rising"]),
            int(config.get("reddit_limit_per_subreddit", 25)),
        )
        all_items = yahoo_items + naver_items + reddit_items
        inserted = save_items(conn, all_items)
        refresh_keyword_daily(conn, config, day)
        briefing_data = collect_briefing_data(config)
        earnings_saved = save_earnings_results(conn, briefing_data.get("yahoo_earnings", []))
        earnings_synced = sync_recent_earnings_from_nasdaq(
            conn,
            int(config.get("earnings_sync_days", config.get("earnings_backfill_days", 14))),
        )
        if not briefing_data.get("yahoo_earnings"):
            briefing_data["yahoo_earnings"] = load_recent_earnings_from_db(
                conn,
                int(config.get("earnings_report_limit", 10)),
            )
        export_earnings_dashboard(conn, base_dir)
        payload = build_payload(conn, config, day, briefing_data)

        payload_path = base_dir / "workflow_payload.json"
        report_path = base_dir / "daily_report.txt"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report = render_report(payload)
        report_path.write_text(report, encoding="utf-8")

        final_message = report
        if send_dify:
            dify_response = call_dify(payload)
            (base_dir / "dify_response.json").write_text(json.dumps(dify_response, ensure_ascii=False, indent=2), encoding="utf-8")
            (base_dir / "latest_dify_result.md").write_text(extract_dify_result(dify_response), encoding="utf-8")
        (base_dir / "latest_dify_report.md").write_text(final_message, encoding="utf-8")
        if send_tg:
            send_telegram(format_telegram_report(final_message))

        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, yahoo_count = ?, naver_count = ?, reddit_count = ?, status = ?, message = ?
            WHERE id = ?
            """,
            (now_kst().isoformat(), len(yahoo_items), len(naver_items), len(reddit_items), "ok", f"inserted={inserted}", run_id),
        )
        conn.commit()
        print(
            f"ok: collected={len(all_items)}, inserted={inserted}, earnings_saved={earnings_saved}, "
            f"earnings_synced={earnings_synced}, payload={payload_path}, report={report_path}"
        )
    except Exception as exc:
        conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, message = ? WHERE id = ?",
            (now_kst().isoformat(), "error", str(exc), run_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect finance news/social mentions and build a Dify workflow payload.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="collect sources, update DB, build payload")
    run_parser.add_argument("--config", default="config.json", help="path to config JSON")
    run_parser.add_argument("--send-dify", action="store_true", help="send payload to Dify Workflow API")
    run_parser.add_argument("--send-telegram", action="store_true", help="send report or Dify result to Telegram")

    args = parser.parse_args()
    if args.command == "run":
        run(Path(args.config).resolve(), args.send_dify, args.send_telegram)


if __name__ == "__main__":
    main()
