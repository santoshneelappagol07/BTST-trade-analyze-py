"""
server.py — Flask application for NIFTY Market Analysis Dashboard.
Serves the dashboard UI and provides the /api/analyze endpoint.
Now includes FII/DII data and Intraday predictions alongside BTST.

RESILIENCE:
  - FII/DII fetch is wrapped in try/except — if it fails, the rest
    of the analysis (news scraping, sentiment) still works.
  - Debug endpoint /api/debug/fii-dii helps diagnose which data
    sources work on the deployment environment.
"""

import json
import logging
import traceback
from flask import Flask, render_template, jsonify

from scraper import scrape_all_news
from analyzer import analyze_news
from fii_dii_scraper import fetch_fii_dii_data, diagnose_nse_connectivity
from intraday_analyzer import generate_intraday_prediction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Trigger full news scraping + FII/DII fetch + sentiment analysis
    + intraday prediction. Returns the complete prediction JSON.

    RESILIENCE: FII/DII fetch failure does NOT crash the endpoint.
    If FII/DII fails, analysis proceeds with empty institutional data.
    """
    try:
        logger.info("━━━ Starting market analysis ━━━")

        # Phase 1: Scrape news
        logger.info("Phase 1: Scraping news from all sources...")
        news_items = scrape_all_news()
        logger.info(f"Scraped {len(news_items)} news items.")

        # Phase 2: Fetch FII/DII data (resilient — never crashes)
        logger.info("Phase 2: Fetching FII/DII institutional flow data...")
        try:
            fii_dii_data = fetch_fii_dii_data()
            logger.info(
                f"FII/DII data: FII Net={fii_dii_data['fii']['net_value']}, "
                f"DII Net={fii_dii_data['dii']['net_value']} "
                f"(Source: {fii_dii_data.get('source', 'Unknown')})"
            )
        except Exception as fii_err:
            logger.error(f"FII/DII fetch crashed: {fii_err}")
            logger.error(traceback.format_exc())
            fii_dii_data = {
                "fii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
                "dii": {"buy_value": 0.0, "sell_value": 0.0, "net_value": 0.0},
                "date": "",
                "source": "Unavailable (error)",
                "estimated": True,
                "error": f"FII/DII fetch failed: {str(fii_err)}",
            }

        # Phase 3: Analyze sentiment (BTST prediction)
        logger.info("Phase 3: Running sentiment analysis (BTST)...")
        result = analyze_news(news_items, fii_dii_data=fii_dii_data)
        logger.info(
            f"BTST Analysis — Prediction: {result['prediction']}, "
            f"Confidence: {result['confidence']}%"
        )

        # Phase 4: Generate intraday prediction
        logger.info("Phase 4: Generating intraday prediction...")
        try:
            intraday = generate_intraday_prediction(
                fii_dii_data=fii_dii_data,
                news_sentiment=result["news_sentiment"],
                gap_prediction=result["prediction"],
                event_risk=result["event_risk"],
                scores=result["scores"],
                bullish_factors=result["bullish_factors"],
                bearish_factors=result["bearish_factors"],
                sector_summary=result["sector_summary"],
            )
            logger.info(
                f"Intraday — Bias: {intraday['intraday_bias']['bias']}, "
                f"Pattern: {intraday['intraday_pattern']['pattern']}, "
                f"Volatility: {intraday['volatility']['level']}"
            )
        except Exception as intraday_err:
            logger.error(f"Intraday prediction failed: {intraday_err}")
            logger.error(traceback.format_exc())
            intraday = {
                "intraday_bias": {"bias": "NEUTRAL", "description": "Intraday prediction unavailable"},
                "intraday_pattern": {"pattern": "UNKNOWN", "description": ""},
                "volatility": {"level": "MEDIUM", "description": ""},
                "error": str(intraday_err),
            }

        # Merge everything into the result
        result["fii_dii"] = fii_dii_data
        result["intraday"] = intraday

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Analysis failed: {str(e)}",
        }), 500


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "NIFTY Market Analyzer (BTST + Intraday)"})


@app.route("/api/debug/fii-dii", methods=["GET"])
def debug_fii_dii():
    """
    Debug endpoint: diagnose FII/DII data source connectivity.

    Returns status of each data source (NSE, MoneyControl, etc.)
    and whether they're reachable from this server.

    Use this after deploying to Render to see which tiers work.
    """
    try:
        logger.info("Running FII/DII connectivity diagnostics...")
        diagnostics = diagnose_nse_connectivity()

        # Also try an actual fetch to see which tier succeeds
        logger.info("Attempting actual FII/DII data fetch...")
        try:
            data = fetch_fii_dii_data()
            fetch_result = {
                "success": not data.get("estimated", True),
                "source": data.get("source", "unknown"),
                "fii_net": data["fii"]["net_value"],
                "dii_net": data["dii"]["net_value"],
                "date": data.get("date", ""),
                "error": data.get("error", None),
            }
        except Exception as e:
            fetch_result = {
                "success": False,
                "error": str(e),
            }

        return jsonify({
            "status": "ok",
            "diagnostics": diagnostics,
            "fetch_result": fetch_result,
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500


if __name__ == "__main__":
    print("\n" + "━" * 60)
    print("  🚀 NIFTY Market Analysis Dashboard")
    print("  📊 BTST + Intraday + FII/DII Intelligence")
    print("  🌐 Open: http://localhost:5000")
    print("━" * 60 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
