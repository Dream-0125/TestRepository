#!/usr/bin/env python3
"""
币安全市场多空信号扫描器 - 纯推送版（部署到 Railway）
- 每5分钟扫描一次
- 发现信号直接推送到飞书
"""

import requests
import time
import json
from datetime import datetime
import numpy as np

# ==================== 配置区 ====================
FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/33753bb0-cde4-422f-8352-b2e93bd42d35"

SCAN_INTERVAL = 300                # 扫描间隔（秒），5分钟
WHALE_THRESHOLD_USDT = 50000       # 鲸鱼单门槛（USDT）
WHALE_WINDOW_MINUTES = 60

# ----- 做多配置 -----
LONG_SCORE_THRESHOLD = 5
LONG_WEIGHTS = {"drop": 2.0, "vol_ratio": 1.0, "funding": 1.5, "ls_retail": 1.0, "ls_top": 1.5, "whale": 1.0, "ma25": 1.0}
LONG_PARAMS = {"min_drop": 5.0, "vol_ratio_min": 1.2, "funding_max": -0.0003, "ls_retail_max": 0.9, "ls_top_min": 1.1, "whale_min": 2}

# ----- 做空配置 -----
SHORT_SCORE_THRESHOLD = 5
SHORT_WEIGHTS = {"gain": 2.0, "vol_ratio": 1.0, "funding": 1.5, "high_dist": 1.0, "ls_retail": 1.0, "ls_top": 1.5, "whale": 1.0}
SHORT_PARAMS = {"min_gain": 6.0, "vol_ratio_max": 0.85, "funding_min": 0.0003, "high_dist_max": 0.04, "ls_retail_min": 1.5, "ls_top_max": 0.9, "whale_min": 2}
# ===============================================

BASE_URL = "https://fapi.binance.com"
session = requests.Session()

# ---------- 辅助函数 ----------

def safe_get(url, params=None, timeout=10):
    try:
        resp = session.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except:
        return None

def get_all_symbols():
    data = safe_get(f"{BASE_URL}/fapi/v1/exchangeInfo")
    if not data or "symbols" not in data:
        return []
    return [s["symbol"] for s in data["symbols"] if s["symbol"].endswith("USDT") and s["status"] == "TRADING"]

def get_tickers():
    data = safe_get(f"{BASE_URL}/fapi/v1/ticker/24hr")
    if not data:
        return []
    result = []
    for item in data:
        if not item["symbol"].endswith("USDT"):
            continue
        try:
            result.append({
                "symbol": item["symbol"],
                "change": float(item["priceChangePercent"]),
                "vol": float(item["volume"]),
                "price": float(item["lastPrice"]),
            })
        except:
            continue
    return result

def get_kdata(symbol):
    result = {"volumes": [], "closes": [], "high_30d": 0}
    data1 = safe_get(f"{BASE_URL}/fapi/v1/klines", params={"symbol": symbol, "interval": "1h", "limit": 30})
    if data1:
        result["volumes"] = [float(k[5]) for k in data1 if len(k) > 5]
        result["closes"] = [float(k[4]) for k in data1 if len(k) > 4]
    data2 = safe_get(f"{BASE_URL}/fapi/v1/klines", params={"symbol": symbol, "interval": "1d", "limit": 30})
    if data2:
        highs = [float(k[2]) for k in data2 if len(k) > 2]
        result["high_30d"] = max(highs) if highs else 0
    return result

def get_ls(symbol):
    result = {"retail": None, "top": None}
    data = safe_get(f"{BASE_URL}/futures/data/globalLongShortAccountRatio", params={"symbol": symbol, "period": "1h", "limit": 1})
    if data and data:
        try: result["retail"] = float(data[0]["longShortRatio"])
        except: pass
    data2 = safe_get(f"{BASE_URL}/futures/data/topLongShortPositionRatio", params={"symbol": symbol, "period": "1h", "limit": 1})
    if data2 and data2:
        try: result["top"] = float(data2[0]["longShortRatio"])
        except: pass
    return result

def get_funding(symbol):
    data = safe_get(f"{BASE_URL}/fapi/v1/premiumIndex", params={"symbol": symbol})
    if data and "lastFundingRate" in data:
        return float(data["lastFundingRate"])
    return 0.0

def get_whale(symbol):
    result = {"buy": 0, "sell": 0}
    data = safe_get(f"{BASE_URL}/fapi/v1/trades", params={"symbol": symbol, "limit": 100})
    if not data:
        return result
    cutoff = time.time() - WHALE_WINDOW_MINUTES * 60
    for trade in data:
        if int(trade["time"]) / 1000 < cutoff:
            continue
        if float(trade["quoteQty"]) < WHALE_THRESHOLD_USDT:
            continue
        if trade["isBuyerMaker"]:
            result["sell"] += 1
        else:
            result["buy"] += 1
    return result

def analyze(ticker):
    symbol = ticker["symbol"]
    price = ticker["price"]
    change = ticker["change"]

    kdata = get_kdata(symbol)
    volumes = kdata["volumes"]
    if len(volumes) < 5:
        return None
    ma5 = np.mean(volumes[-5:])
    vol_ratio = ticker["vol"] / ma5 if ma5 > 0 else 0
    ma25 = np.mean(kdata["closes"]) if kdata["closes"] else 0
    above_ma25 = price > ma25 if ma25 > 0 else False
    dist_to_high = (kdata["high_30d"] - price) / price if kdata["high_30d"] > 0 else 999

    rate = get_funding(symbol)
    ls = get_ls(symbol)
    whale = get_whale(symbol)

    # 做多评分
    long_score = 0.0
    long_reasons = []
    if change < -LONG_PARAMS["min_drop"]:
        long_score += LONG_WEIGHTS["drop"]; long_reasons.append(f"跌幅{change:.2f}%")
    if vol_ratio > LONG_PARAMS["vol_ratio_min"]:
        long_score += LONG_WEIGHTS["vol_ratio"]; long_reasons.append(f"放量{vol_ratio:.2f}倍")
    if rate < LONG_PARAMS["funding_max"]:
        long_score += LONG_WEIGHTS["funding"]; long_reasons.append(f"费率{rate*100:.3f}%")
    if ls["retail"] and ls["retail"] < LONG_PARAMS["ls_retail_max"]:
        long_score += LONG_WEIGHTS["ls_retail"]; long_reasons.append(f"散户恐慌{ls['retail']:.2f}")
    if ls["top"] and ls["top"] > LONG_PARAMS["ls_top_min"]:
        long_score += LONG_WEIGHTS["ls_top"]; long_reasons.append(f"大户看多{ls['top']:.2f}")
    if whale["buy"] >= LONG_PARAMS["whale_min"]:
        long_score += LONG_WEIGHTS["whale"]; long_reasons.append(f"鲸鱼买入{whale['buy']}笔")
    if above_ma25:
        long_score += LONG_WEIGHTS["ma25"]; long_reasons.append("站上MA25")

    # 做空评分
    short_score = 0.0
    short_reasons = []
    if change > SHORT_PARAMS["min_gain"]:
        short_score += SHORT_WEIGHTS["gain"]; short_reasons.append(f"涨幅{change:.2f}%")
    if vol_ratio < SHORT_PARAMS["vol_ratio_max"]:
        short_score += SHORT_WEIGHTS["vol_ratio"]; short_reasons.append(f"缩量{vol_ratio:.2f}倍")
    if rate > SHORT_PARAMS["funding_min"]:
        short_score += SHORT_WEIGHTS["funding"]; short_reasons.append(f"费率{rate*100:.3f}%")
    if dist_to_high < SHORT_PARAMS["high_dist_max"]:
        short_score += SHORT_WEIGHTS["high_dist"]; short_reasons.append(f"距前高{dist_to_high*100:.2f}%")
    if ls["retail"] and ls["retail"] > SHORT_PARAMS["ls_retail_min"]:
        short_score += SHORT_WEIGHTS["ls_retail"]; short_reasons.append(f"散户贪婪{ls['retail']:.2f}")
    if ls["top"] and ls["top"] < SHORT_PARAMS["ls_top_max"]:
        short_score += SHORT_WEIGHTS["ls_top"]; short_reasons.append(f"大户看空{ls['top']:.2f}")
    if whale["sell"] >= SHORT_PARAMS["whale_min"]:
        short_score += SHORT_WEIGHTS["whale"]; short_reasons.append(f"鲸鱼卖出{whale['sell']}笔")

    details = {
        "symbol": symbol, "price": price, "change": change,
        "vol_ratio": vol_ratio, "funding_rate": rate * 100,
        "ls_retail": ls["retail"], "ls_top": ls["top"],
        "whale_buy": whale["buy"], "whale_sell": whale["sell"],
        "above_ma25": above_ma25, "dist_to_high_pct": dist_to_high * 100,
    }
    return long_score, short_score, long_reasons, short_reasons, details

# ---------- 飞书推送 ----------

def send_feishu(message):
    if "你的HookID" in FEISHU_WEBHOOK_URL:
        print("⚠️ 请先配置飞书 Webhook URL")
        return
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        resp = session.post(FEISHU_WEBHOOK_URL, headers={"Content-Type": "application/json"}, json=data, timeout=5)
        if resp.status_code != 200:
            print(f"推送失败: {resp.text}")
    except Exception as e:
        print(f"推送异常: {e}")

# ---------- 主扫描 ----------

def scan():
    print(f"[{datetime.now()}] 开始扫描...")
    all_symbols = get_all_symbols()
    if not all_symbols:
        print("获取合约列表失败")
        return
    tickers = get_tickers()
    if not tickers:
        return

    candidates = [t for t in tickers if abs(t["change"]) >= 3.0]
    candidates.sort(key=lambda x: abs(x["change"]), reverse=True)
    candidates = candidates[:30]  # 只分析前30个

    long_signals, short_signals = [], []
    for ticker in candidates:
        try:
            result = analyze(ticker)
            if not result:
                continue
            long_score, short_score, lr, sr, details = result
            if long_score >= LONG_SCORE_THRESHOLD:
                long_signals.append({"score": long_score, "reasons": lr, **details})
            if short_score >= SHORT_SCORE_THRESHOLD:
                short_signals.append({"score": short_score, "reasons": sr, **details})
        except Exception as e:
            print(f"分析 {ticker.get('symbol')} 出错: {e}")
        time.sleep(0.1)

    # 推送汇总
    if long_signals or short_signals:
        msg = f"🔄 扫描: {datetime.now().strftime('%H:%M')}\n"
        if long_signals:
            msg += f"📈 做多 {len(long_signals)} 个:\n"
            for s in long_signals[:3]:
                msg += f"  {s['symbol']} 得分{s['score']:.1f} 跌幅{s['change']:.1f}%\n"
        if short_signals:
            msg += f"📉 做空 {len(short_signals)} 个:\n"
            for s in short_signals[:3]:
                msg += f"  {s['symbol']} 得分{s['score']:.1f} 涨幅{s['change']:.1f}%\n"
        send_feishu(msg)
        print(f"推送完成: 做多{len(long_signals)}, 做空{len(short_signals)}")
    else:
        print("无信号")

# ---------- 主循环 ----------

if __name__ == "__main__":
    print("=" * 50)
    print("币安扫描器已启动（纯推送模式）")
    print(f"扫描间隔: {SCAN_INTERVAL}秒")
    print("=" * 50)

    while True:
        try:
            scan()
        except Exception as e:
            print(f"扫描出错: {e}")
        time.sleep(SCAN_INTERVAL)
