"""
scraper.py — Multi-source financial news scraper for Indian markets.
Fetches news from RSS feeds (Google News, Livemint, Economic Times)
without requiring any API keys.
"""

import re
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests
import feedparser
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class NewsItem:
    """Represents a single scraped news article."""
    headline: str
    source: str
    published_date: str
    link: str
    snippet: str = ""
    sector: str = "General"
    category: str = "general"  # macro, india, commodity, corporate, event

    def to_dict(self) -> dict:
        return asdict(self)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sector Classification Keywords
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Banking & Finance": [
        "bank", "banking", "nbfc", "npa", "credit", "loan", "deposit",
        "hdfc", "icici", "kotak", "axis bank", "sbi", "pnb", "bob",
        "bajaj finance", "bajaj finserv", "rbi", "reserve bank", "interest rate",
        "monetary policy", "repo rate", "lending", "financial services",
        "insurance", "lic", "mutual fund",
    ],
    "Information Technology": [
        "infosys", "tcs", "wipro", "hcl tech", "tech mahindra", "l&t technology",
        "it sector", "information technology", "software", "saas", "cloud computing",
        "artificial intelligence", " ai ", "digital transformation", "cybersecurity",
        "it services", "mphasis", "persistent", "coforge", "ltimindtree",
    ],
    "Pharma & Healthcare": [
        "pharma", "pharmaceutical", "drug", "fda", "usfda", "healthcare",
        "hospital", "sun pharma", "dr reddy", "cipla", "lupin", "biocon",
        "divi's lab", "apollo hospital", "max health", "fortis", "medicine",
        "vaccine", "generic drug", "biosimilar",
    ],
    "Automobile": [
        "auto", "automobile", "car", "vehicle", "ev ", "electric vehicle",
        "maruti", "tata motors", "mahindra", "bajaj auto", "hero motocorp",
        "eicher", "ashok leyland", "tvs motor", "ola electric",
        "two-wheeler", "passenger vehicle", "commercial vehicle",
    ],
    "Energy & Oil": [
        "oil", "petroleum", "crude", "brent", "opec", "natural gas",
        "reliance", "ongc", "ioc", "bpcl", "hpcl", "gail",
        "adani green", "adani energy", "ntpc", "power grid", "tata power",
        "renewable energy", "solar", "wind energy", "coal",
    ],
    "Metals & Mining": [
        "metal", "steel", "iron ore", "copper", "aluminium", "zinc", "gold",
        "silver", "tata steel", "jsw steel", "hindalco", "vedanta",
        "coal india", "nmdc", "mining", "commodity metal",
    ],
    "FMCG": [
        "fmcg", "consumer goods", "hindustan unilever", "itc", "nestle",
        "britannia", "dabur", "marico", "godrej consumer", "colgate",
        "procter", "consumer staple", "packaged food",
    ],
    "Real Estate & Infrastructure": [
        "real estate", "realty", "housing", "dlf", "godrej properties",
        "oberoi realty", "prestige", "brigade", "infrastructure", "infra",
        "construction", "cement", "ultratech", "ambuja", "acc",
        "l&t", "larsen", "road", "highway", "smart city",
    ],
    "Telecom & Media": [
        "telecom", "jio", "airtel", "vodafone", "idea", "bsnl",
        "5g", "spectrum", "broadband", "media", "zee", "star",
        "disney", "hotstar", "ott",
    ],
    "Defence & Aerospace": [
        "defence", "defense", "hal", "bharat electronics", "bel",
        "bharat dynamics", "missile", "fighter jet", "military",
        "aerospace", "drdo", "naval", "army", "air force",
    ],
    "Agriculture": [
        "agriculture", "agri", "crop", "monsoon", "kharif", "rabi",
        "msp", "fertilizer", "urea", "pesticide", "food grain",
        "wheat", "rice", "sugar", "cotton",
    ],
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# News Category Keywords (for analyzer)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "macro": [
        "us economy", "fed", "federal reserve", "inflation", "cpi", "wpi",
        "gdp", "trade war", "tariff", "us market", "wall street", "s&p 500",
        "nasdaq", "dow jones", "treasury", "bond yield", "dollar index",
        "global recession", "imf", "world bank", "us jobs", "nonfarm",
        "ecb", "bank of japan", "china economy", "europe economy",
    ],
    "india": [
        "rbi", "reserve bank", "nifty", "sensex", "bse", "nse",
        "fii", "dii", "india gdp", "indian economy", "rupee",
        "fiscal deficit", "gst", "tax", "modi", "budget", "sebi",
        "indian market", "domestic", "india growth",
    ],
    "commodity": [
        "crude", "oil", "brent", "wti", "gold", "silver", "copper",
        "commodity", "opec", "natural gas", "metal price",
    ],
    "corporate": [
        "earnings", "quarterly result", "profit", "revenue", "order",
        "acquisition", "merger", "ipo", "buyback", "dividend",
        "upgrade", "downgrade", "rating", "target price",
    ],
    "event": [
        "rbi policy", "fed meeting", "fomc", "budget", "election",
        "g20", "g7", "cpi data", "jobs report", "expiry",
    ],
    "geopolitical": [
        "war", "conflict", "tension", "sanction", "missile", "attack",
        "ceasefire", "peace", "nato", "russia", "ukraine", "china taiwan",
        "middle east", "iran", "israel", "north korea",
    ],
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RSS Feed Sources
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GOOGLE_NEWS_RSS_QUERIES: list[dict[str, str]] = [
    # India-specific
    {"query": "NIFTY 50 stock market India today", "category": "india"},
    {"query": "RBI monetary policy India", "category": "india"},
    {"query": "FII DII activity India stock market", "category": "india"},
    {"query": "Indian economy GDP growth", "category": "india"},
    {"query": "Sensex NIFTY market today", "category": "india"},
    # Global macro
    {"query": "US Federal Reserve interest rate", "category": "macro"},
    {"query": "US inflation CPI data", "category": "macro"},
    {"query": "Wall Street S&P 500 Nasdaq today", "category": "macro"},
    {"query": "global economy recession 2025 2026", "category": "macro"},
    # Commodities
    {"query": "crude oil price today Brent WTI", "category": "commodity"},
    {"query": "gold price today international", "category": "commodity"},
    # Geopolitics
    {"query": "geopolitical tension war trade conflict", "category": "geopolitical"},
    # Corporate India
    {"query": "India corporate earnings quarterly results", "category": "corporate"},
    {"query": "India IT sector Infosys TCS Wipro", "category": "corporate"},
    {"query": "India banking sector HDFC ICICI SBI", "category": "corporate"},
]

DIRECT_RSS_FEEDS: list[dict[str, str]] = [
    {"url": "https://www.livemint.com/rss/markets", "source": "Livemint", "category": "india"},
    {"url": "https://www.livemint.com/rss/money", "source": "Livemint", "category": "india"},
    {"url": "https://www.livemint.com/rss/industry", "source": "Livemint", "category": "corporate"},
    {
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "source": "Economic Times",
        "category": "india",
    },
    {
        "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
        "source": "Economic Times",
        "category": "macro",
    },
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scraper Utilities
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _clean_html(raw_html: str) -> str:
    """Remove HTML tags from a string."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _classify_sector(text: str) -> str:
    """Classify a news headline/snippet into a market sector."""
    text_lower = text.lower()
    sector_scores: dict[str, int] = {}

    for sector, keywords in SECTOR_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                score += 1
        if score > 0:
            sector_scores[sector] = score

    if not sector_scores:
        return "General"

    # Return the sector with the highest keyword match count
    return max(sector_scores, key=sector_scores.get)


def _classify_category(text: str, default_category: str = "general") -> str:
    """Classify news into analysis categories (macro, india, commodity, etc.)."""
    text_lower = text.lower()
    cat_scores: dict[str, int] = {}

    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            cat_scores[cat] = score

    if not cat_scores:
        return default_category

    return max(cat_scores, key=cat_scores.get)


def _is_recent(published_parsed, hours: int = 48) -> bool:
    """Check if a feed entry was published within the last N hours."""
    if not published_parsed:
        return True  # If no date, include it anyway

    try:
        pub_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return pub_dt >= cutoff
    except Exception:
        return True


def _format_date(published_parsed) -> str:
    """Format a feedparser date tuple into a human-readable string."""
    if not published_parsed:
        return datetime.now().strftime("%d %b %Y, %I:%M %p")
    try:
        dt = datetime(*published_parsed[:6])
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return datetime.now().strftime("%d %b %Y, %I:%M %p")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Core Scraping Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def fetch_google_news_rss(query: str, category: str = "general", max_items: int = 8) -> list[NewsItem]:
    """Fetch news from Google News RSS search."""
    encoded_query = requests.utils.quote(query)
    url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    items: list[NewsItem] = []
    try:
        feed = feedparser.parse(
            url,
            request_headers=HEADERS,
        )

        for entry in feed.entries[:max_items]:
            if not _is_recent(entry.get("published_parsed"), hours=48):
                continue

            headline = _clean_html(entry.get("title", ""))
            snippet = _clean_html(entry.get("summary", entry.get("description", "")))
            link = entry.get("link", "")

            # Google News titles often end with " - Source Name"
            source = "Google News"
            if " - " in headline:
                parts = headline.rsplit(" - ", 1)
                if len(parts) == 2 and len(parts[1]) < 50:
                    source = parts[1].strip()
                    headline = parts[0].strip()

            combined_text = f"{headline} {snippet}"

            items.append(
                NewsItem(
                    headline=headline,
                    source=source,
                    published_date=_format_date(entry.get("published_parsed")),
                    link=link,
                    snippet=snippet[:300],
                    sector=_classify_sector(combined_text),
                    category=_classify_category(combined_text, default_category=category),
                )
            )
    except Exception as e:
        logger.error(f"Error fetching Google News RSS for '{query}': {e}")

    return items


def fetch_direct_rss(url: str, source_name: str, category: str = "general", max_items: int = 10) -> list[NewsItem]:
    """Fetch news from a direct RSS feed URL (Livemint, ET, etc.)."""
    items: list[NewsItem] = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)

        for entry in feed.entries[:max_items]:
            if not _is_recent(entry.get("published_parsed"), hours=48):
                continue

            headline = _clean_html(entry.get("title", ""))
            snippet = _clean_html(
                entry.get("summary", entry.get("description", ""))
            )
            link = entry.get("link", "")

            combined_text = f"{headline} {snippet}"

            items.append(
                NewsItem(
                    headline=headline,
                    source=source_name,
                    published_date=_format_date(entry.get("published_parsed")),
                    link=link,
                    snippet=snippet[:300],
                    sector=_classify_sector(combined_text),
                    category=_classify_category(combined_text, default_category=category),
                )
            )
    except Exception as e:
        logger.error(f"Error fetching RSS from '{url}': {e}")

    return items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Deduplication
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    """Remove near-duplicate headlines using simple word-overlap heuristic."""
    seen_keys: set[str] = set()
    unique: list[NewsItem] = []

    for item in items:
        # Normalise headline to a fingerprint
        words = set(re.sub(r"[^a-z0-9\s]", "", item.headline.lower()).split())
        # Remove very short words for better matching
        sig_words = frozenset(w for w in words if len(w) > 3)
        key = " ".join(sorted(sig_words))

        # Check overlap with existing
        is_dup = False
        for seen in seen_keys:
            seen_set = set(seen.split())
            overlap = len(sig_words & seen_set)
            union = len(sig_words | seen_set)
            if union > 0 and overlap / union > 0.6:
                is_dup = True
                break

        if not is_dup and key:
            seen_keys.add(key)
            unique.append(item)

    return unique


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def scrape_all_news() -> list[dict]:
    """
    Master function: scrape all sources, deduplicate, classify sectors,
    and return a list of dicts ready for the analyzer.
    """
    all_items: list[NewsItem] = []

    # 1. Google News RSS (multiple queries)
    logger.info("Fetching Google News RSS feeds...")
    for qinfo in GOOGLE_NEWS_RSS_QUERIES:
        items = fetch_google_news_rss(
            query=qinfo["query"],
            category=qinfo["category"],
            max_items=6,
        )
        all_items.extend(items)
        # Small random delay to be polite
        time.sleep(random.uniform(0.3, 0.8))

    # 2. Direct RSS Feeds (Livemint, ET)
    logger.info("Fetching direct RSS feeds (Livemint, ET)...")
    for finfo in DIRECT_RSS_FEEDS:
        items = fetch_direct_rss(
            url=finfo["url"],
            source_name=finfo["source"],
            category=finfo["category"],
            max_items=8,
        )
        all_items.extend(items)
        time.sleep(random.uniform(0.2, 0.5))

    # 3. Deduplicate
    logger.info(f"Total raw items: {len(all_items)}. Deduplicating...")
    unique_items = _deduplicate(all_items)
    logger.info(f"Unique items after dedup: {len(unique_items)}")

    return [item.to_dict() for item in unique_items]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI Test
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import json
    results = scrape_all_news()
    print(json.dumps(results[:5], indent=2, ensure_ascii=False))
    print(f"\nTotal news items: {len(results)}")
