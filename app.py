from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from flask import Flask, Response, abort, jsonify, render_template_string, request, url_for

APP_TITLE = "Susan's Earnings Dashboard"
NZ_TZ = ZoneInfo("Pacific/Auckland")
UTC = timezone.utc

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
EODHD_API_TOKEN = os.getenv("EODHD_API_TOKEN", "").strip()

BASE_DIR = Path(__file__).resolve().parent
HOLDINGS_PATH = BASE_DIR / "holdings.json"

app = Flask(__name__)

# CORS allowlist for your frontend
ALLOWED_ORIGINS = {
    "https://flabbywhiteboy.github.io",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
}

# ASX/NZX mappings for your frontend watchlist
SYMBOL_MAP = {
    "A2M": "A2M.AU",
    "CCR": "CCR.AU",
    "CSL": "CSL.AU",
    "HGH": "HGH.AU",
    "MQG": "MQG.AU",
    "SIG": "SIG.AU",
    "XRO": "XRO.AU",
}


@dataclass
class Event:
    ticker: str
    name: str
    category: str
    type: str
    title: str
    start_dt_nz: datetime
    end_dt_nz: Optional[datetime]
    listen_url: Optional[str]
    ir_page: Optional[str]
    notes: Optional[str] = None
    amount: Optional[str] = None


def add_cors_headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return resp


@app.after_request
def apply_cors(resp):
    return add_cors_headers(resp)


@app.route("/api/quote/<ticker>", methods=["GET", "OPTIONS"])
def api_quote(ticker: str):
    if request.method == "OPTIONS":
        return add_cors_headers(Response(status=204))

    ticker = ticker.upper().strip()
    symbol = SYMBOL_MAP.get(ticker)

    if not symbol:
        return jsonify({"ok": False, "error": f"No EODHD symbol mapping for {ticker}"}), 404

    if not EODHD_API_TOKEN:
        return jsonify({"ok": False, "error": "EODHD_API_TOKEN is missing"}), 500

    try:
        resp = requests.get(
            f"https://eodhd.com/api/eod/{symbol}",
            params={
                "filter": "last_close",
                "api_token": EODHD_API_TOKEN,
                "fmt": "json",
            },
            timeout=30,
        )

        raw_text = resp.text[:500]

        if not resp.ok:
            return jsonify({
                "ok": False,
                "error": f"EODHD HTTP {resp.status_code}",
                "raw": raw_text
            }), 502

        data = resp.json()

        if isinstance(data, (int, float)):
            price = float(data)
        elif isinstance(data, str):
            price = float(data)
        else:
            return jsonify({
                "ok": False,
                "error": "Unexpected EODHD response type",
                "raw": data
            }), 502

        return jsonify({
    "ok": True,
    "ticker": ticker,
    "sourceSymbol": symbol,
    "marker": "NEW_BACKEND_CODE_IS_RUNNING",
    "quote": {
        "c": price,
        "dp": None
    }
})

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": repr(e)
        }), 502


def load_holdings() -> List[Dict[str, Any]]:
    with open(HOLDINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_holdings_by_ticker() -> Dict[str, Dict[str, Any]]:
    return {h["ticker"]: h for h in load_holdings()}


def now_nz() -> datetime:
    return datetime.now(tz=NZ_TZ)


def start_of_week_nz(d: datetime) -> datetime:
    return (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_alpha_date(value: str) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def nz_datetime_for_date(d: date, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=NZ_TZ)


def fetch_price(ticker: str) -> Optional[float]:
    try:
        info = yf.Ticker(ticker).fast_info
        if hasattr(info, "get"):
            price = info.get("lastPrice") or info.get("last_price")
            if price is not None:
                return float(price)
    except Exception:
        pass

    try:
        hist = yf.Ticker(ticker).history(period="2d")
        if not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        pass

    return None


def fetch_eodhd_last_close(symbol: str) -> Optional[float]:
    if not EODHD_API_TOKEN:
        print("EODHD_API_TOKEN is missing")
        return None

    try:
        resp = requests.get(
            f"https://eodhd.com/api/eod/{symbol}",
            params={
                "filter": "last_close",
                "api_token": EODHD_API_TOKEN,
                "fmt": "json",
            },
            timeout=30,
        )

        print("EODHD status:", resp.status_code)
        print("EODHD text:", resp.text[:500])

        resp.raise_for_status()

        data = resp.json()

        if isinstance(data, (int, float)):
            return float(data)

        if isinstance(data, str):
            return float(data)

        print("EODHD returned unexpected JSON type:", type(data), data)
        return None

    except Exception as e:
        print("EODHD fetch exception:", repr(e))
        return None


def alpha_vantage_text(params: Dict[str, str]) -> Optional[str]:
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        query = dict(params)
        query["apikey"] = ALPHAVANTAGE_API_KEY
        resp = requests.get("https://www.alphavantage.co/query", params=query, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def alpha_vantage_json(params: Dict[str, str]) -> Any:
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        query = dict(params)
        query["apikey"] = ALPHAVANTAGE_API_KEY
        resp = requests.get("https://www.alphavantage.co/query", params=query, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def fetch_earnings_map() -> Dict[str, date]:
    results: Dict[str, date] = {}
    text = alpha_vantage_text({"function": "EARNINGS_CALENDAR", "horizon": "3month"})
    if not text:
        return results

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return results

    headers = [h.strip() for h in lines[0].split(",")]
    try:
        symbol_i = headers.index("symbol")
        report_i = headers.index("reportDate")
    except ValueError:
        return results

    wanted = {h["ticker"] for h in load_holdings()}

    for row in lines[1:]:
        cols = [c.strip() for c in row.split(",")]
        if len(cols) <= max(symbol_i, report_i):
            continue
        symbol = cols[symbol_i]
        if symbol not in wanted:
            continue
        report_date = parse_alpha_date(cols[report_i])
        if not report_date:
            continue
        current = results.get(symbol)
        if current is None or report_date < current:
            results[symbol] = report_date
    return results


def fetch_dividend_map() -> Dict[str, Dict[str, Any]]:
    today = now_nz().date()
    output: Dict[str, Dict[str, Any]] = {}

    for h in load_holdings():
        ticker = h["ticker"]
        data = alpha_vantage_json({"function": "DIVIDENDS", "symbol": ticker})
        if not isinstance(data, dict):
            continue

        series = data.get("data") or []
        next_row = None
        next_pay = None

        for row in series:
            pay_date = parse_alpha_date(row.get("payment_date", ""))
            if not pay_date or pay_date < today:
                continue
            if next_pay is None or pay_date < next_pay:
                next_pay = pay_date
                next_row = row

        if next_row and next_pay:
            output[ticker] = {
                "payment_date": next_pay,
                "record_date": parse_alpha_date(next_row.get("record_date", "")),
                "ex_dividend_date": parse_alpha_date(next_row.get("ex_dividend_date", "")),
                "amount": next_row.get("amount"),
                "currency": next_row.get("currency"),
            }
    return output


def build_events(window_start_nz: datetime, window_end_nz: datetime) -> List[Event]:
    holdings = get_holdings_by_ticker()
    events: List[Event] = []

    earnings_map = fetch_earnings_map()
    dividend_map = fetch_dividend_map()

    for ticker, report_date in earnings_map.items():
        if not (window_start_nz.date() <= report_date <= window_end_nz.date()):
            continue
        h = holdings[ticker]
        start_dt = nz_datetime_for_date(report_date, 9, 0)
        events.append(
            Event(
                ticker=ticker,
                name=h["name"],
                category=h["category"],
                type="earnings",
                title="Earnings report",
                start_dt_nz=start_dt,
                end_dt_nz=start_dt + timedelta(hours=1),
                listen_url=h.get("webcast_url"),
                ir_page=h.get("ir_page"),
                notes="Date sourced automatically. Confirm exact time and webcast on the IR page.",
            )
        )

    for ticker, div in dividend_map.items():
        payment_date = div["payment_date"]
        if not (window_start_nz.date() <= payment_date <= window_end_nz.date()):
            continue
        h = holdings[ticker]
        start_dt = nz_datetime_for_date(payment_date, 9, 0)
        amount = None
        if div.get("amount"):
            amount = f'{div["amount"]} {div.get("currency", "")}'.strip()

        note_parts = []
        if div.get("ex_dividend_date"):
            note_parts.append(f'Ex-dividend: {div["ex_dividend_date"].isoformat()}')
        if div.get("record_date"):
            note_parts.append(f'Record date: {div["record_date"].isoformat()}')

        events.append(
            Event(
                ticker=ticker,
                name=h["name"],
                category=h["category"],
                type="dividend",
                title="Dividend payment",
                start_dt_nz=start_dt,
                end_dt_nz=None,
                listen_url=None,
                ir_page=h.get("ir_page"),
                notes=" • ".join(note_parts) if note_parts else None,
                amount=amount,
            )
        )

    events.sort(key=lambda e: (e.start_dt_nz, e.name))
    return events


def build_price_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for h in load_holdings():
        price = fetch_price(h["ticker"])
        target = h.get("price_target")
        status = None
        if price is not None and target is not None:
            status = "below target" if price <= target else "above target"
        rows.append(
            {
                "ticker": h["ticker"],
                "name": h["name"],
                "category": h["category"],
                "price": price,
                "price_target": target,
                "status": status,
                "ir_page": h.get("ir_page"),
            }
        )
    rows.sort(key=lambda r: (r["category"], r["name"]))
    return rows


def event_to_ics(event: Event) -> str:
    uid = f'{event.ticker}-{event.start_dt_nz.strftime("%Y%m%dT%H%M%S")}-susan-dashboard'
    dtstamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    dtstart = event.start_dt_nz.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    dtend_dt = event.end_dt_nz or (event.start_dt_nz + timedelta(hours=1))
    dtend = dtend_dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    description_parts = []
    if event.notes:
        description_parts.append(event.notes)
    if event.listen_url:
        description_parts.append(f"Listen: {event.listen_url}")
    elif event.ir_page:
        description_parts.append(f"IR page: {event.ir_page}")
    description = "\\n".join(description_parts).replace(",", "\\,").replace(";", "\\;")

    title = f"{event.name} - {event.title}".replace(",", "\\,").replace(";", "\\;")
    url = event.listen_url or event.ir_page or ""

    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//OpenAI//Susan Earnings Dashboard//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{description}",
            f"URL:{url}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def two_week_window() -> tuple[datetime, datetime]:
    current = now_nz()
    start = start_of_week_nz(current)
    end = start + timedelta(days=13, hours=23, minutes=59)
    return start, end


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ app_title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <style>
    :root {
      --bg: #f6f7fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #dbe1ea;
      --accent: #0f62fe;
      --green: #0a7f3f;
      --red: #b42318;
      --shadow: 0 6px 18px rgba(0,0,0,0.06);
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); }
    .wrap { max-width: 980px; margin: 0 auto; padding: 16px 14px 40px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 18px; padding: 14px; box-shadow: var(--shadow); margin-bottom: 14px; }
    h1 { margin: 0 0 6px; font-size: 1.8rem; }
    .sub,.tiny,.notes,.meta { color: var(--muted); }
    .day { font-weight: 700; font-size: 1.05rem; margin-bottom: 10px; }
    .event { border-top: 1px solid var(--border); padding: 12px 0; }
    .event:first-of-type { border-top: none; padding-top: 0; }
    .name { font-weight: 700; font-size: 1.02rem; }
    .pill { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 0.78rem; background: #eef3ff; color: #2643a2; margin-right: 6px; }
    .pill.watch { background: #fff4e5; color: #8a4b00; }
    .pill.div { background: #ecfdf3; color: var(--green); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .btn { text-decoration: none; border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; color: var(--text); font-weight: 600; background: white; }
    .btn.primary { background: var(--accent); color: white; border-color: var(--accent); }
    table { width: 100%; border-collapse: collapse; font-size: 0.95rem; }
    th, td { padding: 10px 8px; border-top: 1px solid var(--border); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    tr:first-child th, tr:first-child td { border-top: none; }
    .price-good { color: var(--green); font-weight: 700; }
    .price-bad { color: var(--red); font-weight: 700; }
    .banner { background: #fff8dd; border: 1px solid #ead58c; color: #6f5b12; border-radius: 14px; padding: 10px 12px; margin-bottom: 14px; font-size: 0.93rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <div style="margin-bottom:16px;">
      <h1>{{ app_title }}</h1>
      <div class="sub">This week + next week, shown in New Zealand time.</div>
    </div>

    {% if not has_api_key %}
      <div class="banner">
        Add an Alpha Vantage API key later for automatic earnings and dividend dates.
      </div>
    {% endif %}

    <div class="card">
      <div class="day">Upcoming events</div>
      {% if grouped_events %}
        {% for day_label, events in grouped_events %}
          <div style="margin-top: 12px;">
            <div class="day">{{ day_label }}</div>
            {% for e in events %}
              <div class="event">
                <div class="name">{{ e.name }} ({{ e.ticker }})</div>
                <div class="meta">
                  {% if e.category == "watchlist" %}
                    <span class="pill watch">Watchlist</span>
                  {% else %}
                    <span class="pill">Portfolio</span>
                  {% endif %}
                  {% if e.type == "dividend" %}
                    <span class="pill div">Dividend</span>
                  {% else %}
                    <span class="pill">Earnings</span>
                  {% endif %}
                  {{ e.start_dt_nz.strftime("%a %-d %b %Y, %-I:%M %p") }}
                </div>
                {% if e.amount %}
                  <div class="meta">Amount: {{ e.amount }}</div>
                {% endif %}
                {% if e.notes %}
                  <div class="notes" style="margin-top:4px;">{{ e.notes }}</div>
                {% endif %}
                <div class="actions">
                  {% if e.listen_url %}
                    <a class="btn primary" href="{{ e.listen_url }}" target="_blank" rel="noopener">Listen</a>
                  {% endif %}
                  {% if e.ir_page %}
                    <a class="btn" href="{{ e.ir_page }}" target="_blank" rel="noopener">IR page</a>
                  {% endif %}
                  <a class="btn" href="{{ url_for('calendar_file', ticker=e.ticker, start=e.start_dt_nz.strftime('%Y%m%dT%H%M')) }}">Add to calendar</a>
                </div>
              </div>
            {% endfor %}
          </div>
        {% endfor %}
      {% else %}
        <div class="tiny">No events found in the current two-week window yet.</div>
      {% endif %}
    </div>

    <div class="card">
      <div class="day">Prices</div>
      <table>
        <tr><th>Name</th><th>Ticker</th><th>Category</th><th>Price</th><th>Target</th><th>Status</th></tr>
        {% for row in price_rows %}
          <tr>
            <td>{{ row.name }}</td>
            <td>{{ row.ticker }}</td>
            <td>{{ "Watchlist" if row.category == "watchlist" else "Portfolio" }}</td>
            <td>{{ "%.2f"|format(row.price) if row.price is not none else "—" }}</td>
            <td>{{ "%.2f"|format(row.price_target) if row.price_target is not none else "—" }}</td>
            <td>
              {% if row.status == "below target" %}
                <span class="price-good">Below target</span>
              {% elif row.status == "above target" %}
                <span class="price-bad">Above target</span>
              {% else %}
                —
              {% endif %}
            </td>
          </tr>
        {% endfor %}
      </table>
    </div>
  </div>
</body>
</html>
"""


@app.route("/")
def index() -> str:
    start, end = two_week_window()
    events = build_events(start, end)
    grouped: Dict[str, List[Event]] = {}
    for e in events:
        label = e.start_dt_nz.strftime("%A, %-d %B %Y")
        grouped.setdefault(label, []).append(e)

    return render_template_string(
        HTML,
        app_title=APP_TITLE,
        grouped_events=list(grouped.items()),
        price_rows=build_price_rows(),
        has_api_key=bool(ALPHAVANTAGE_API_KEY),
    )


@app.route("/calendar/<ticker>/<start>")
def calendar_file(ticker: str, start: str):
    holdings = get_holdings_by_ticker()
    if ticker not in holdings:
        abort(404)

    start_dt = datetime.strptime(start, "%Y%m%dT%H%M").replace(tzinfo=NZ_TZ)
    h = holdings[ticker]
    event = Event(
        ticker=ticker,
        name=h["name"],
        category=h["category"],
        type="manual",
        title="Investor event",
        start_dt_nz=start_dt,
        end_dt_nz=start_dt + timedelta(hours=1),
        listen_url=h.get("webcast_url"),
        ir_page=h.get("ir_page"),
        notes="Created from Susan's dashboard",
    )
    ics = event_to_ics(event)
    filename = f"{ticker}-{start_dt.strftime('%Y%m%dT%H%M')}.ics"
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

