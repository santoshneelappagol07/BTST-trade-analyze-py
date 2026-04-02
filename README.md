# 🚀 NIFTY Market Analyzer — AI-Powered Gap Prediction Engine

> Real-time NIFTY 50 next-day gap prediction using multi-source news sentiment analysis, institutional flows, and market microstructure signals.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-Private-red?style=for-the-badge)]()

---

## 📊 What It Does

This system predicts whether NIFTY 50 will **GAP UP**, **GAP DOWN**, or open **FLAT** the next trading day — and recommends **BTST (Buy Today Sell Tomorrow)** trades with confidence scores.

### Key Predictions
| Output | Description |
|--------|-------------|
| **Gap Prediction** | GAP UP / GAP DOWN / FLAT |
| **Confidence %** | 10% – 92% (clamped) |
| **BTST Bias** | BUY CE / BUY PE / NO TRADE |
| **Intraday Pattern** | Trend continuation, reversal, range-bound |

---

## 🧠 How It Works

### 1. Multi-Source News Scraping
- **20+ sources** via RSS feeds (zero API keys required)
- Google News (15 curated queries), Livemint, Economic Times
- Only last **48 hours** of news, auto-deduplicated

### 2. 4-Layer NLP Sentiment Engine
| Layer | Technique | What It Catches |
|-------|-----------|-----------------|
| 🔍 Regex Patterns | Morphological matching | All word forms — fell/falling/fallen |
| 📖 Synonym Dictionary | Paraphrase expansion | "oil prices drop" = "crude fall" |
| 📝 Keyword Fallback | 140+ weighted keywords | Traditional keyword matching |
| 🚫 Negation Detection | 5-word pre-window scan | "unlikely to cut rates" → flips sentiment |

### 3. Smart Multipliers
- **Sector Weight** — Banking (1.5x) > IT (1.3x) > Energy (1.2x) > Defence (0.7x)
- **Recency Decay** — Today (1.0x) → Yesterday (0.65x) → 2 days (0.4x)
- **Category Importance** — Macro/India/Geopolitical (2.0x) > Commodity/Corporate (1.5x)
- **Volume Normalization** — Prevents 100 weak articles from overpowering 5 strong ones

### 4. Market Microstructure Signals
| Signal | Weight | Accuracy |
|--------|--------|----------|
| 🎯 **GIFT Nifty** | Up to ±20 pts | ~65-70% directional accuracy alone |
| 🏦 **FII/DII Flows** | Up to ±12 pts each | Institutional momentum |
| 📈 **India VIX** | Confidence modifier | Risk/fear gauge |
| ⚖️ **Put-Call Ratio** | Up to ±12 pts | Contrarian signal |
| 🌍 **Global Markets** | S&P 500 (3x), NASDAQ (2.5x) | Overnight correlation |

### 5. Signal Confluence
Only recommends trades when **multiple independent signals agree** — prevents false signals from any single indicator.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Flask Dashboard                    │
│              (index.html + script.js)                │
├─────────────────────────────────────────────────────┤
│                    server.py                         │
│            API endpoint: /api/analyze                │
├──────────┬──────────┬──────────┬────────────────────┤
│ scraper  │ analyzer │ fii_dii  │ intraday_analyzer  │
│   .py    │   .py    │ scraper  │       .py          │
│          │          │   .py    │                    │
├──────────┴──────────┴──────────┴────────────────────┤
│              RSS Feeds & Web Sources                 │
│   Google News • Livemint • Economic Times • More    │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
news/
├── server.py              # Flask app — routes & API
├── scraper.py             # Multi-source RSS news scraper
├── analyzer.py            # 4-layer sentiment engine + market signals
├── fii_dii_scraper.py     # FII/DII institutional flow data
├── intraday_analyzer.py   # Intraday pattern & bias prediction
├── templates/
│   └── index.html         # Dashboard UI
├── static/
│   ├── style.css          # Dashboard styling
│   └── script.js          # Frontend logic & API calls
├── requirements.txt       # Python dependencies
├── Procfile               # Production server config
├── render.yaml            # Render.com deployment blueprint
└── .gitignore             # Git ignore rules
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/nifty-news-analyzer.git
cd nifty-news-analyzer

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Run Locally

```bash
python server.py
```

Open **http://localhost:5000** in your browser → Click **Analyze** to run the prediction engine.

---

## 🌐 Deployment

### Deploy to Render (Recommended)

1. Push code to GitHub (private repo)
2. Sign up at [render.com](https://render.com) with GitHub
3. New → Web Service → Connect your repo
4. Render auto-reads `render.yaml` — click Deploy
5. Live at `https://your-app.onrender.com`

### Deploy to Railway

1. Sign up at [railway.app](https://railway.app) with GitHub
2. New Project → Deploy from GitHub → Select repo
3. Railway auto-reads `Procfile` — auto-deploys
4. Generate domain in Settings → Networking

---

## 📡 API Reference

### `POST /api/analyze`

Triggers full analysis pipeline. No request body needed.

**Response:**
```json
{
  "status": "success",
  "data": {
    "prediction": "GAP UP",
    "confidence": 72,
    "btst_bias": "BUY CE",
    "news_sentiment": "BULLISH",
    "bullish_factors": ["GIFT Nifty up +0.85%", "FII buying ₹1,200Cr"],
    "bearish_factors": ["Crude oil surge"],
    "event_risk": "LOW",
    "confluence": {
      "agree_count": 3,
      "total_signals": 4,
      "recommendation": "GOOD — majority signals aligned"
    },
    "major_news": [...],
    "sector_summary": [...],
    "fii_dii": {...},
    "intraday": {...}
  }
}
```

### `GET /api/health`

Health check endpoint.

---

## 🛡️ Disclaimer

> **This tool is for educational and informational purposes only.** It does not constitute financial advice. Stock market trading involves significant risk. Past performance and prediction confidence scores do not guarantee future results. Always do your own research and consult a financial advisor before making trading decisions.

---

## 🔧 Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11, Flask |
| Scraping | feedparser, BeautifulSoup4, requests |
| NLP | Custom rule-based engine (regex + keywords) |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Production Server | Gunicorn |
| Data Sources | Google News RSS, Livemint, Economic Times |

---

<p align="center">
  Built with ❤️ for Indian market traders
</p>
