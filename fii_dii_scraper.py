"""
fii_dii_scraper.py — NSE-only FII/DII data scraper.

WHY NSE ONLY:
  NSE is the authoritative source. Multiple third-party sites
  just re-publish NSE data with potential delays and formatting
  differences, adding failure points without adding accuracy.

HOW NSE BLOCKS SCRAPERS (and how we solve it):
  NSE uses Akamai Bot Manager which validates:
    1. TLS fingerprint  (Python ≠ Chrome → blocked)
    2. HTTP/2 settings
    3. JavaScript challenges (bm_sz cookie)
    4. Cookie chain: nsit → nseappid → ak_bmsc → bm_sv

  SOLUTION — 3-tier approach, all NSE sources:
    Tier 1: curl_cffi  — mimics Chrome TLS fingerprint exactly.
                         Solves Akamai without Selenium.
                         Requires: pip install curl-cffi
    Tier 2: NSE Archives CSV — nsearchives.nseindia.com is a
                         static file server, no Akamai protection.
                         Slightly delayed (EOD batch), but accurate.
    Tier 3: Plain requests with retry — works on some networks
                         where Akamai is less aggressive, or when
                         the session cookie from Tier 1 is reused.

NSE API RESPONSE STRUCTURE:
  Endpoint: GET /api/fiidiiTradeReact
  Returns a JSON array, typically 2 entries:
    [
      {
        "category": "FII/FPI *",
        "buyValue":  "14523.45",   # Crores, string
        "sellValue": "12411.34",   # Crores, string
        "netValue":  "2112.11",    # Can be negative: "-469.13"
        "date":      "28-Mar-2026"
      },
      {
        "category": "DII",
        ...same fields...
      }
    ]

INSTALL:
  pip install curl-cffi requests
"""

import csv
import io
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NSE URLs — all official NSE domains only
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NSE_HOME_URL       = "https://www.nseindia.com"
NSE_FII_DII_PAGE   = "https://www.nseindia.com/market-data/fii-dii"
NSE_FII_DII_API    = "https://www.nseindia.com/api/fiidiiTradeReact"

# Static file server — no Akamai. Updated EOD by NSE.
NSE_ARCHIVES_CSV   = "https://nsearchives.nseindia.com/content/fo/fii_dii_data.csv"

# Standard browser headers (used by both tiers)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Cache-Control":   "no-cache",
    "Pragma":          "no-cache",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared Value Parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_nse_value(value: Any) -> float:
    """
    Robustly parse a value from NSE API into a float (crores).

    Handles all formats NSE has been observed to return:
      '14523.45'    →  14523.45
      '-469.13'     →  -469.13
      '2,111.11'    →  2111.11
      '-2,400.00'   →  -2400.0
      '(1500.00)'   →  -1500.0   (parenthetical negative)
      12345.67      →  12345.67  (already numeric)
      ''            →  0.0
      None          →  0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    s = str(value).strip()
    if not s:
        return 0.0

    # Parenthetical negative: (1500.00) → -1500.00
    is_paren_neg = s.startswith("(") and s.endswith(")")

    # Strip everything except digits, dot, minus
    cleaned = re.sub(r"[^\d.\-]", "", s)
    if not cleaned or cleaned in (".", "-"):
        return 0.0

    try:
        val = float(cleaned)
        return round(-abs(val) if is_paren_neg else val, 2)
    except ValueError:
        return 0.0


def _empty_result(source: str = "NSE", reason: str = "") -> dict:
    """Return a zero-valued result dict when all fetches fail."""
    return {
        "fii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "dii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "date":      datetime.now().strftime("%d %b %Y"),
        "source":    source,
        "estimated": True,
        "error":     reason,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Common: NSE API Response Parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_nse_api_response(raw: list | dict) -> Optional[dict]:
    """
    Parse the NSE /api/fiidiiTradeReact JSON response.

    NSE returns a list of category dicts. Category names observed:
      "FII/FPI *"  — Foreign Institutional / Portfolio Investors
      "DII"        — Domestic Institutional Investors
      "FII"        — older format (rare)

    Returns standardized dict or None if no usable data found.
    """
    entries = raw if isinstance(raw, list) else [raw]

    result = {
        "fii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "dii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "date":      datetime.now().strftime("%d %b %Y"),
        "source":    "NSE India",
        "estimated": False,
    }

    found_fii = False
    found_dii = False

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        category = str(entry.get("category", "")).upper().strip()

        buy  = _parse_nse_value(entry.get("buyValue",  0))
        sell = _parse_nse_value(entry.get("sellValue", 0))
        net  = _parse_nse_value(entry.get("netValue",  0))

        # If netValue is missing / zero but buy and sell are present, compute it
        if net == 0.0 and (buy != 0.0 or sell != 0.0):
            net = round(buy - sell, 2)

        # Date parsing — NSE format: "28-Mar-2026"
        raw_date = entry.get("date", "")
        if raw_date:
            try:
                parsed = datetime.strptime(raw_date.strip(), "%d-%b-%Y")
                result["date"] = parsed.strftime("%d %b %Y")
            except ValueError:
                pass  # Keep default

        if "FII" in category or "FPI" in category:
            result["fii"]["buy_value"]  = buy
            result["fii"]["sell_value"] = sell
            result["fii"]["net_value"]  = net
            found_fii = True

        elif "DII" in category:
            result["dii"]["buy_value"]  = buy
            result["dii"]["sell_value"] = sell
            result["dii"]["net_value"]  = net
            found_dii = True

    if not found_fii and not found_dii:
        return None  # Response had no recognisable categories

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 1: curl_cffi — Chrome TLS Impersonation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_nse_curl_cffi() -> Optional[dict]:
    """
    Fetch NSE FII/DII using curl_cffi which mimics Chrome's exact
    TLS fingerprint (JA3 hash). This bypasses Akamai Bot Manager
    without needing Selenium or a real browser.

    Requires: pip install curl-cffi

    Session flow (mirrors what Chrome does):
      1. GET nseindia.com        → gets nsit, bm_sz cookies
      2. GET /market-data/fii-dii → validates session, sets ak_bmsc
      3. GET /api/fiidiiTradeReact → returns JSON data
    """
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.debug("curl_cffi not installed. Run: pip install curl-cffi")
        return None

    try:
        session = cffi_requests.Session(impersonate="chrome131")
        session.headers.update(_BROWSER_HEADERS)

        # Step 1: Homepage — establishes initial session cookies
        logger.debug("curl_cffi: Step 1 — visiting NSE homepage")
        session.get(
            NSE_HOME_URL,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
            timeout=12,
        )
        time.sleep(0.8)

        # Step 2: FII/DII page — Akamai validates the session
        logger.debug("curl_cffi: Step 2 — visiting FII/DII page")
        session.get(
            NSE_FII_DII_PAGE,
            headers={
                "Accept":  "text/html,application/xhtml+xml,*/*;q=0.8",
                "Referer": NSE_HOME_URL,
            },
            timeout=12,
        )
        time.sleep(0.5)

        # Step 3: API call — now we have valid session cookies
        logger.debug("curl_cffi: Step 3 — calling FII/DII API")
        resp = session.get(
            NSE_FII_DII_API,
            headers={
                "Accept":           "application/json, text/plain, */*",
                "Referer":          NSE_FII_DII_PAGE,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )

        if resp.status_code != 200:
            logger.warning(f"curl_cffi: NSE API returned HTTP {resp.status_code}")
            return None

        raw = resp.json()
        result = _parse_nse_api_response(raw)

        if result:
            result["source"] = "NSE India (curl_cffi)"
            logger.info(
                f"✅ Tier 1 (curl_cffi): FII net={result['fii']['net_value']}, "
                f"DII net={result['dii']['net_value']}"
            )

        return result

    except Exception as e:
        logger.warning(f"curl_cffi fetch failed: {type(e).__name__}: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 2: NSE Archives CSV (no Akamai protection)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_nse_archives_csv() -> Optional[dict]:
    """
    Download the FII/DII CSV from NSE Archives static server.

    URL: https://nsearchives.nseindia.com/content/fo/fii_dii_data.csv

    This server is distinct from www.nseindia.com and does NOT
    use Akamai Bot Manager — plain requests works fine here.

    The CSV contains historical data. We parse the most recent
    row that matches today's date (or the latest available date).

    Known CSV columns (NSE format):
      Date, FII Buy, FII Sell, FII Net, DII Buy, DII Sell, DII Net

    Limitation: Updated once per day after market hours (~6 PM IST).
    During market hours, this reflects the previous day's data.
    """
    try:
        resp = requests.get(
            NSE_ARCHIVES_CSV,
            headers={
                **_BROWSER_HEADERS,
                "Accept":  "text/csv,text/plain,*/*",
                "Referer": NSE_FII_DII_PAGE,
            },
            timeout=15,
        )
        resp.raise_for_status()

        content = resp.content.decode("utf-8-sig", errors="replace")
        return _parse_nse_csv(content)

    except requests.exceptions.RequestException as e:
        logger.warning(f"NSE Archives CSV fetch failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"NSE Archives CSV parsing failed: {e}")
        return None


def _parse_nse_csv(csv_content: str) -> Optional[dict]:
    """
    Parse the NSE FII/DII CSV content.

    NSE CSV header variations observed:
      'Date,FII/FPI Buy,FII/FPI Sell,FII/FPI Net,DII Buy,DII Sell,DII Net'
      'Date,Buy Value,Sell Value,Net Value,Buy Value,Sell Value,Net Value'

    We handle both by position + header keyword matching.
    Returns the most recent available row's data.
    """
    reader = csv.reader(io.StringIO(csv_content.strip()))
    rows = list(reader)

    if len(rows) < 2:
        logger.warning("NSE CSV: not enough rows")
        return None

    # Parse header to identify column positions
    header = [h.strip().upper() for h in rows[0]]
    logger.debug(f"NSE CSV header: {header}")

    # Try to find column indices by header keywords
    def _find_col(keywords: list[str], start: int = 0) -> int:
        """Find first column index containing any of the keywords after `start`."""
        for i in range(start, len(header)):
            if any(kw in header[i] for kw in keywords):
                return i
        return -1

    date_col = _find_col(["DATE"], 0)
    if date_col == -1:
        date_col = 0  # Default: first column

    # FII columns — look for BUY, SELL, NET in first half of headers
    fii_buy_col  = _find_col(["BUY"],  date_col + 1)
    fii_sell_col = _find_col(["SELL"], fii_buy_col + 1 if fii_buy_col != -1 else date_col + 1)
    fii_net_col  = _find_col(["NET"],  date_col + 1)

    # DII columns — look for BUY, SELL, NET in second half
    midpoint = len(header) // 2
    dii_buy_col  = _find_col(["BUY"],  max(midpoint, fii_buy_col + 1))
    dii_sell_col = _find_col(["SELL"], max(midpoint, fii_sell_col + 1))
    dii_net_col  = _find_col(["NET"],  max(midpoint, fii_net_col + 1))

    # If header detection failed, fall back to positional mapping
    # Standard NSE CSV: Date(0), FIIBuy(1), FIISell(2), FIINet(3),
    #                   DIIBuy(4), DIISell(5), DIINet(6)
    if fii_buy_col == -1:  fii_buy_col  = 1
    if fii_sell_col == -1: fii_sell_col = 2
    if fii_net_col == -1:  fii_net_col  = 3
    if dii_buy_col == -1:  dii_buy_col  = 4
    if dii_sell_col == -1: dii_sell_col = 5
    if dii_net_col == -1:  dii_net_col  = 6

    # Parse data rows — find the most recent valid row
    today_str = datetime.now().strftime("%d-%b-%Y").upper()
    best_row = None
    best_date = None

    for row in reversed(rows[1:]):   # Iterate from most recent
        if len(row) < 4:
            continue
        row_date_str = row[date_col].strip().upper() if date_col < len(row) else ""
        if not row_date_str:
            continue

        # Parse the date for comparison
        try:
            row_date = datetime.strptime(row_date_str, "%d-%b-%Y")
        except ValueError:
            try:
                row_date = datetime.strptime(row_date_str, "%d/%m/%Y")
            except ValueError:
                continue

        if best_date is None or row_date > best_date:
            best_date = row_date
            best_row = row

        # Prefer today's data if found
        if row_date_str == today_str:
            break

    if best_row is None:
        logger.warning("NSE CSV: no valid data rows found")
        return None

    def _safe_get(row: list, idx: int) -> float:
        try:
            return _parse_nse_value(row[idx]) if idx < len(row) else 0.0
        except Exception:
            return 0.0

    fii_buy  = _safe_get(best_row, fii_buy_col)
    fii_sell = _safe_get(best_row, fii_sell_col)
    fii_net  = _safe_get(best_row, fii_net_col)
    dii_buy  = _safe_get(best_row, dii_buy_col)
    dii_sell = _safe_get(best_row, dii_sell_col)
    dii_net  = _safe_get(best_row, dii_net_col)

    # Recompute net if it looks wrong
    if fii_net == 0.0 and (fii_buy != 0.0 or fii_sell != 0.0):
        fii_net = round(fii_buy - fii_sell, 2)
    if dii_net == 0.0 and (dii_buy != 0.0 or dii_sell != 0.0):
        dii_net = round(dii_buy - dii_sell, 2)

    date_str = best_date.strftime("%d %b %Y") if best_date else datetime.now().strftime("%d %b %Y")

    # Warn if we're using previous day's data
    if best_date and best_date.date() < datetime.now().date():
        logger.info(
            f"NSE CSV: using data from {date_str} "
            f"(today's data not yet available — NSE updates CSV after market close)"
        )

    result = {
        "fii": {"buy_value": fii_buy, "sell_value": fii_sell, "net_value": fii_net},
        "dii": {"buy_value": dii_buy, "sell_value": dii_sell, "net_value": dii_net},
        "date":      date_str,
        "source":    "NSE Archives CSV",
        "estimated": False,
    }

    logger.info(
        f"✅ Tier 2 (NSE Archives CSV): FII net={fii_net}, DII net={dii_net} "
        f"(data date: {date_str})"
    )
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 3: Plain requests with session retry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_nse_plain_requests(max_retries: int = 2) -> Optional[dict]:
    """
    Attempt NSE API with plain requests library.
    Works on some networks where Akamai is less aggressive,
    or after a previous curl_cffi call has warmed the session.

    Uses exponential backoff on failures.
    """
    for attempt in range(1, max_retries + 1):
        try:
            session = requests.Session()
            session.headers.update(_BROWSER_HEADERS)

            # Step 1: Homepage
            session.get(
                NSE_HOME_URL,
                headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                timeout=10,
            )
            time.sleep(0.6)

            # Step 2: FII/DII page
            session.get(
                NSE_FII_DII_PAGE,
                headers={
                    "Accept":  "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Referer": NSE_HOME_URL,
                },
                timeout=10,
            )
            time.sleep(0.4)

            # Step 3: API
            resp = session.get(
                NSE_FII_DII_API,
                headers={
                    "Accept":           "application/json, text/plain, */*",
                    "Referer":          NSE_FII_DII_PAGE,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=12,
            )

            if resp.status_code == 401 or resp.status_code == 403:
                logger.warning(
                    f"Plain requests: attempt {attempt}/{max_retries} — "
                    f"NSE returned {resp.status_code} (Akamai block)"
                )
                # Exponential backoff before retry
                time.sleep(2 ** attempt)
                continue

            resp.raise_for_status()
            raw = resp.json()
            result = _parse_nse_api_response(raw)

            if result:
                result["source"] = "NSE India (requests)"
                logger.info(
                    f"✅ Tier 3 (plain requests): FII net={result['fii']['net_value']}, "
                    f"DII net={result['dii']['net_value']}"
                )
            return result

        except requests.exceptions.RequestException as e:
            logger.warning(f"Plain requests: attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Plain requests: JSON parse error: {e}")
            return None

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Validation & Sanity Check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _validate_result(data: dict) -> bool:
    """
    Sanity-check the FII/DII result.

    Rules:
      - FII buy/sell values should be plausible (0–50,000 Cr)
      - Net should approximately equal buy - sell (within 5%)
      - At least one of FII or DII should have non-zero values

    Returns True if data looks valid.
    """
    if not data:
        return False

    fii = data.get("fii", {})
    dii = data.get("dii", {})

    fii_net = fii.get("net_value", 0)
    dii_net = dii.get("net_value", 0)

    # Both zero → probably a failed fetch that returned 0s
    if fii_net == 0.0 and dii_net == 0.0:
        return False

    # Implausibly large values (likely parsing error)
    MAX_PLAUSIBLE = 100_000  # 1 lakh crore — extreme upper bound
    for val in [fii.get("buy_value", 0), fii.get("sell_value", 0),
                dii.get("buy_value", 0), dii.get("sell_value", 0)]:
        if abs(val) > MAX_PLAUSIBLE:
            logger.warning(f"Validation: implausible value {val} — discarding result")
            return False

    # Verify net ≈ buy - sell (within 2% tolerance)
    for label, group in [("FII", fii), ("DII", dii)]:
        buy  = group.get("buy_value",  0)
        sell = group.get("sell_value", 0)
        net  = group.get("net_value",  0)
        computed = round(buy - sell, 2)
        if buy != 0 and sell != 0:
            tolerance = max(abs(computed) * 0.02, 5.0)  # 2% or 5 Cr, whichever larger
            if abs(net - computed) > tolerance:
                logger.warning(
                    f"Validation: {label} net mismatch: "
                    f"reported={net}, computed={computed} — auto-correcting"
                )
                group["net_value"] = computed  # Auto-correct

    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_fii_dii_data() -> dict:
    """
    Fetch FII/DII data from NSE India with 3-tier fallback.
    All sources are NSE official domains — no third-party sites.

    Tier 1 (curl_cffi)  : Bypasses Akamai, real-time data.
                          Best choice during market hours.
    Tier 2 (NSE CSV)    : Static file server, no Akamai, EOD data.
                          Reliable fallback, previous day after hours.
    Tier 3 (requests)   : Plain HTTP, works on some networks.
                          Last NSE-based attempt before giving up.

    Returns
    -------
    dict with structure:
        {
            "fii": {
                "buy_value":  float,   # Crores
                "sell_value": float,   # Crores
                "net_value":  float,   # buy - sell (negative = net selling)
            },
            "dii": { ...same... },
            "date":      str,    # "28 Mar 2026"
            "source":    str,    # which tier succeeded
            "estimated": bool,   # True only if all tiers failed
            "error":     str,    # only present if all tiers failed
        }
    """
    logger.info("Fetching FII/DII data from NSE...")

    # ── Tier 1: curl_cffi ─────────────────────────────
    logger.info("Tier 1: curl_cffi Chrome impersonation...")
    data = _fetch_nse_curl_cffi()
    if data and _validate_result(data):
        return data

    # ── Tier 2: NSE Archives CSV ──────────────────────
    logger.info("Tier 2: NSE Archives CSV (nsearchives.nseindia.com)...")
    data = _fetch_nse_archives_csv()
    if data and _validate_result(data):
        return data

    # ── Tier 3: Plain requests with retry ─────────────
    logger.info("Tier 3: Plain requests with retry...")
    data = _fetch_nse_plain_requests(max_retries=2)
    if data and _validate_result(data):
        return data

    # All tiers failed
    logger.error(
        "All NSE fetch tiers failed. "
        "Check network connectivity to nseindia.com and nsearchives.nseindia.com."
    )
    return _empty_result(
        source="NSE (unavailable)",
        reason=(
            "All NSE fetch attempts failed. "
            "Possible causes: network restriction, NSE maintenance, "
            "or Akamai block. Install curl-cffi for best results: "
            "pip install curl-cffi"
        ),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Diagnostic Helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def diagnose_nse_connectivity() -> dict:
    """
    Run connectivity checks against NSE endpoints.
    Useful for debugging why scraping is failing.

    Returns a dict of endpoint → status.
    """
    results = {}
    endpoints = {
        "NSE Homepage":     NSE_HOME_URL,
        "NSE FII/DII Page": NSE_FII_DII_PAGE,
        "NSE API":          NSE_FII_DII_API,
        "NSE Archives CSV": NSE_ARCHIVES_CSV,
    }

    for name, url in endpoints.items():
        try:
            resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=8)
            results[name] = {
                "url":    url,
                "status": resp.status_code,
                "ok":     resp.status_code == 200,
                "bytes":  len(resp.content),
            }
        except Exception as e:
            results[name] = {
                "url":   url,
                "status": None,
                "ok":    False,
                "error": str(e),
            }

    # Check curl_cffi availability
    try:
        import curl_cffi
        results["curl_cffi"] = {
            "installed": True,
            "version": curl_cffi.__version__,
        }
    except ImportError:
        results["curl_cffi"] = {
            "installed": False,
            "note": "Install with: pip install curl-cffi",
        }

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="NSE FII/DII Data Fetcher")
    parser.add_argument(
        "--diagnose", action="store_true",
        help="Run connectivity diagnostics instead of fetching data",
    )
    args = parser.parse_args()

    if args.diagnose:
        print("\n=== NSE Connectivity Diagnostics ===")
        diag = diagnose_nse_connectivity()
        print(json.dumps(diag, indent=2))
    else:
        print("\n=== Fetching FII/DII Data ===")
        result = fetch_fii_dii_data()
        print(json.dumps(result, indent=2, ensure_ascii=False))

        print("\n=== Summary ===")
        print(f"Source:   {result['source']}")
        print(f"Date:     {result['date']}")
        print(f"FII Net:  ₹{result['fii']['net_value']:,.2f} Cr  "
              f"({'BUY' if result['fii']['net_value'] > 0 else 'SELL'})")
        print(f"DII Net:  ₹{result['dii']['net_value']:,.2f} Cr  "
              f"({'BUY' if result['dii']['net_value'] > 0 else 'SELL'})")
        if result.get("estimated"):
            print(f"\n⚠️  Note: {result.get('error', 'Data is estimated')}")