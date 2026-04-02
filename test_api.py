"""Quick test script for the analyze API endpoint."""
import requests
import json

r = requests.post("http://localhost:5000/api/analyze")
data = r.json()
d = data.get("data", {})

print("Status:", data.get("status"))
print("Prediction:", d.get("prediction"))
print("Confidence:", d.get("confidence"))
print("BTST Bias:", d.get("btst_bias"))
print("Sentiment:", d.get("news_sentiment"))
print("Event Risk:", d.get("event_risk"))
print("Total News:", d.get("total_news_analyzed"))
print()

print("=== SECTORS ===")
for s in d.get("sector_summary", []):
    print(f"  {s['sector']}: {s['sentiment']} (Bull:{s['bullish_score']} Bear:{s['bearish_score']} News:{s['news_count']})")

print()
print("=== BULLISH FACTORS ===")
for f in d.get("bullish_factors", []):
    print(f"  + {f}")

print()
print("=== BEARISH FACTORS ===")
for f in d.get("bearish_factors", []):
    print(f"  - {f}")

print()
print("=== KEY DRIVERS ===")
for drv in d.get("key_drivers", []):
    print(f"  > {drv}")

print()
print("=== SUMMARY ===")
print(d.get("final_summary", ""))
