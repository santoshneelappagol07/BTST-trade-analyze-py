"""
fii_dii_scraper.py — FII/DII data scraper using Trendlyne.

Changes: Moved exclusively to Trendlyne via curl_cffi for reliable
data fetching without Akamai bot blocks, replacing the legacy multi-tier system.
"""

import logging
import re
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# In-Memory Cache (30-minute TTL)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_cache_lock = threading.Lock()
_cached_data: Optional[dict] = None
_cache_timestamp: Optional[datetime] = None
_CACHE_TTL_MINUTES = 30


def _get_cached() -> Optional[dict]:
    """Return cached data if still valid (within TTL)."""
    global _cached_data, _cache_timestamp
    with _cache_lock:
        if _cached_data and _cache_timestamp:
            age = datetime.now() - _cache_timestamp
            if age < timedelta(minutes=_CACHE_TTL_MINUTES):
                logger.info(
                    f"Cache HIT — using data from {age.seconds // 60}m {age.seconds % 60}s ago "
                    f"(source: {_cached_data.get('source', '?')})"
                )
                return _cached_data.copy()
    return None


def _set_cache(data: dict) -> None:
    """Store data in cache with current timestamp."""
    global _cached_data, _cache_timestamp
    with _cache_lock:
        _cached_data = data.copy()
        _cache_timestamp = datetime.now()
        logger.info(f"Cache SET — stored data from {data.get('source', '?')}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Trendlyne Scraper 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRENDLYNE_URL = "https://trendlyne.com/macro-data/fii-dii/latest/cash-pastmonth/"


def _parse_value(s: str) -> float:
    """Parse string val like '-8331.15' to float."""
    try:
        cleaned = re.sub(r"[^\d.\-]", "", s)
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def _empty_result(reason: str = "") -> dict:
    return {
        "fii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "dii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
        "date": datetime.now().strftime("%d %b %Y"),
        "source": "Trendlyne (Failed)",
        "estimated": True,
        "error": reason,
    }


def fetch_fii_dii_data() -> dict:
    """
    Fetch FII/DII data from Trendlyne using curl_cffi.
    """
    cached = _get_cached()
    if cached:
        return cached

    logger.info("Fetching FII/DII data from Trendlyne...")
    
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.error("curl_cffi not installed. Run: pip install curl-cffi")
        return _empty_result("curl_cffi not installed.")

    try:
        session = cffi_requests.Session(impersonate="chrome131")
        resp = session.get(
            TRENDLYNE_URL, 
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://trendlyne.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        
        if resp.status_code != 200:
            logger.warning(f"Trendlyne returned HTTP {resp.status_code}")
            return _empty_result(f"HTTP {resp.status_code}")
            
        text = resp.text
        fii_net = 0.0
        dii_net = 0.0
        
        # Extract FII Value using Regex
        fii_match = re.search(r'>(?:\s|\\n)*FII(?:\s|\\n)*<[^₹]+?₹(?:\s|\\n)*([-\d.,]+)(?:\s|\\n)*Cr', text, re.IGNORECASE)
        # Fallback if structure changes slightly
        if not fii_match:
            fii_match = re.search(r'FII[^₹]+?₹\s*([-\d.,]+)\s*Cr', text, re.IGNORECASE)
            
        if fii_match:
            fii_net = _parse_value(fii_match.group(1))

        # Extract DII Value using Regex
        dii_match = re.search(r'>(?:\s|\\n)*DII(?:\s|\\n)*<[^₹]+?₹(?:\s|\\n)*([-\d.,]+)(?:\s|\\n)*Cr', text, re.IGNORECASE)
        if not dii_match:
            dii_match = re.search(r'DII[^₹]+?₹\s*([-\d.,]+)\s*Cr', text, re.IGNORECASE)

        if dii_match:
            dii_net = _parse_value(dii_match.group(1))

        if fii_net == 0.0 and dii_net == 0.0:
            logger.warning("Could not extract FII/DII data from Trendlyne HTML (pattern match failed).")
            return _empty_result("Pattern match failed")

        result = {
            # Since Trendlyne dashboard easily provides the net cash value, we just assign it to net_value
            "fii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": fii_net},
            "dii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": dii_net},
            "date": datetime.now().strftime("%d %b %Y"),
            "source": "Trendlyne",
            "estimated": False,
        }
        
        logger.info(f"✅ Trendlyne Extract: FII net={fii_net}, DII net={dii_net}")
        _set_cache(result)
        return result

    except Exception as e:
        logger.error(f"Trendlyne fetch failed: {e}")
        return _empty_result(str(e))


def diagnose_nse_connectivity() -> dict:
    """Diagnostic helper maintained for compatibility with server.py."""
    results = {}
    
    # We rename the internals to check Trendlyne but keep the function name
    # the same so we don't break server imports.
    try:
        import requests
        resp = requests.get(TRENDLYNE_URL, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
        })
        results["Trendlyne (Requests)"] = {
            "url": TRENDLYNE_URL,
            "status": resp.status_code,
            "ok": resp.status_code == 200,
            "bytes": len(resp.content),
        }
    except Exception as e:
        results["Trendlyne"] = {
            "url": TRENDLYNE_URL,
            "status": None,
            "ok": False,
            "error": str(e)
        }
        
    try:
        import curl_cffi
        results["curl_cffi"] = {
            "installed": True,
            "version": getattr(curl_cffi, "__version__", "unknown"),
        }
    except ImportError:
        results["curl_cffi"] = {
            "installed": False,
            "note": "pip install curl-cffi",
        }
        
    # Cache status
    with _cache_lock:
        if _cached_data and _cache_timestamp:
            age = datetime.now() - _cache_timestamp
            results["cache"] = {
                "has_data": True,
                "age_seconds": int(age.total_seconds()),
                "source": _cached_data.get("source", "?"),
                "ttl_remaining": max(0, _CACHE_TTL_MINUTES * 60 - int(age.total_seconds())),
            }
        else:
            results["cache"] = {"has_data": False}

    return results


if __name__ == "__main__":
    import json
    import argparse
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    parser = argparse.ArgumentParser(description="Trendlyne FII/DII Data Fetcher")
    parser.add_argument("--diagnose", action="store_true", help="Run connectivity diagnostics")
    args = parser.parse_args()

    if args.diagnose:
        print("\n=== FII/DII Source Connectivity Diagnostics ===")
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
