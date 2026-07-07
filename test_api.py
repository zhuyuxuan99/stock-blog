import json
import requests

TOKEN = "f6833eb29d6eb93772f06a29d64b3b1f40e2325fde0ea955bc5758ac"

def test_api(date):
    url = "https://api.tushare.pro"
    payload = {
        "api_name": "daily",
        "token": TOKEN,
        "trade_date": date.replace("-", "")
    }
    
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    
    if data.get("code") == 0 and data.get("data"):
        items = data["data"].get("items", [])
        fields = data["data"].get("fields", [])
        
        # 查找300058.SZ的数据
        for item in items:
            if isinstance(item, list) and len(item) > 0:
                if item[0] == "300058.SZ":
                    row = dict(zip(fields, item))
                    print(f"{date} - 300058.SZ:")
                    print(f"  trade_date: {row.get('trade_date')}")
                    print(f"  close: {row.get('close')}")
                    print(f"  pct_chg: {row.get('pct_chg')}")
                    return

# 测试多个日期
test_api("2026-06-12")
test_api("2026-06-18")
test_api("2026-06-20")