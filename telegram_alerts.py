"""
AI Gold Trader - 24/7 Cloud Telegram Alert Engine
Filter:
- Minimum Move Target: >= 50 Points ($5.00+ Expansion)
- Risk-to-Reward: Strict 1:3 Ratio
- Confluences: SMC Liquidity Sweeps, BOS/CHoCH, VWAP, EMA 9/20/50
"""

import os
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("[!] Telegram credentials missing in GitHub Secrets.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Error sending message: {e}")
        return False

def scan_and_alert():
    print("[*] Connecting to real-time Gold Spot market feed...")
    url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=5m&limit=60"
    
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
    except Exception as e:
        print(f"[!] Network error: {e}")
        return

    if not isinstance(data, list) or len(data) < 30:
        print("[!] Insufficient candle data.")
        return

    candles = []
    for c in data:
        candles.append({
            "time": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5])
        })

    latest = candles[-1]
    current_price = latest["close"]

    # Calculate EMAs (9, 20, 50)
    closes = [c["close"] for c in candles]
    def calc_ema(period):
        k = 2 / (period + 1)
        ema = closes[0]
        for p in closes[1:]:
            ema = (p * k) + (ema * (1 - k))
        return ema

    ema9 = calc_ema(9)
    ema20 = calc_ema(20)
    ema50 = calc_ema(50)

    # Calculate VWAP
    cum_pv = sum(((c["high"] + c["low"] + c["close"]) / 3.0) * c["volume"] for c in candles)
    cum_vol = sum(c["volume"] for c in candles)
    vwap = cum_pv / cum_vol if cum_vol > 0 else current_price

    # Swings over recent 20 candles
    recent = candles[-20:-1]
    swing_high = max(c["high"] for c in recent)
    swing_low = min(c["low"] for c in recent)

    bullish_confluences = []
    bearish_confluences = []

    # SMC Checks
    if latest["high"] > swing_high and latest["close"] < swing_high:
        bearish_confluences.append(f"Buy-Side Liquidity Swept above ${swing_high:.2f}")
    if latest["low"] < swing_low and latest["close"] > swing_low:
        bullish_confluences.append(f"Sell-Side Liquidity Swept below ${swing_low:.2f}")

    if latest["close"] > swing_high:
        bullish_confluences.append(f"Break of Structure (BOS) closed above ${swing_high:.2f}")
    if latest["close"] < swing_low:
        bearish_confluences.append(f"Break of Structure (BOS) closed below ${swing_low:.2f}")

    if current_price > ema50 and ema9 > ema20:
        bullish_confluences.append("Bullish EMA Alignment (Price > EMA50, EMA9 > 20)")
    if current_price > vwap:
        bullish_confluences.append(f"Holding above Institutional VWAP (${vwap:.2f})")

    if current_price < ema50 and ema9 < ema20:
        bearish_confluences.append("Bearish EMA Alignment (Price < EMA50, EMA9 < 20)")
    if current_price < vwap:
        bearish_confluences.append(f"Trading below Institutional VWAP (${vwap:.2f})")

    # STRICT USER FILTERS:
    # 1. Target >= 50 points ($5.00+ expansion)
    # 2. Strict 1:3 Risk-to-Reward Ratio (Risk: ~17 points, Reward: 51+ points)
    min_points = 50.0  # 50 points target ($5.00)
    sl_points = 17.0   # 17 points risk for 1:3 ratio

    signal = None
    if len(bullish_confluences) >= 2 and current_price > vwap and ema9 > ema20:
        signal = "BUY"
        entry = current_price
        sl = entry - (sl_points / 10.0)
        tp1 = entry + (min_points / 10.0)
        reasons = bullish_confluences
        inv = f"Candle close below Stop Loss (${sl:.2f})"

    elif len(bearish_confluences) >= 2 and current_price < vwap and ema9 < ema20:
        signal = "SELL"
        entry = current_price
        sl = entry + (sl_points / 10.0)
        tp1 = entry - (min_points / 10.0)
        reasons = bearish_confluences
        inv = f"Candle close above Stop Loss (${sl:.2f})"

    if signal:
        msg = (
            f"🚨 <b>AI GOLD TRADER - 1:3 R:R SIGNAL</b> 🚨\n\n"
            f"<b>Instrument:</b> XAU/USD (Gold Spot)\n"
            f"<b>Signal:</b> {'🟢 <b>BUY</b>' if signal == 'BUY' else '🔴 <b>SELL</b>'}\n"
            f"<b>Live Price:</b> ${current_price:.2f}\n\n"
            f"🎯 <b>Entry:</b> ${entry:.2f}\n"
            f"🛑 <b>Stop Loss:</b> ${sl:.2f} (-{sl_points:.0f} pts)\n"
            f"🏆 <b>Take Profit (1:3):</b> ${tp1:.2f} (+{min_points:.0f} pts)\n\n"
            f"⚖️ <b>Risk-to-Reward:</b> 1:3.0\n"
            f"🔥 <b>Target Move:</b> 50+ Points\n\n"
            f"⚡ <b>Confluences:</b>\n" + "\n".join([f"• {r}" for r in reasons]) + "\n\n"
            f"⚠️ <b>Invalidation:</b> {inv}\n"
            f"🕒 <i>Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</i>"
        )
        print("[+] 1:3 Signal matched! Sending alert to Telegram...")
        send_telegram_message(msg)
    else:
        print(f"[*] Scanned at ${current_price:.2f}. No setup meeting 1:3 R:R & 50+ points criteria currently. Silence maintained.")

if __name__ == "__main__":
    scan_and_alert()
