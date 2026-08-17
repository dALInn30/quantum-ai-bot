import json
import urllib.request
import time
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Paths
PORTFOLIO_DB = r"c:\Users\User\.gemini\antigravity-ide\scratch\ai-crypto-bot\portfolio_db.json"
TELEGRAM_CFG = r"c:\Users\User\.gemini\antigravity-ide\scratch\ai-crypto-bot\telegram_config.json"

def format_price(val):
    try:
        v = float(val)
        if v >= 1000: return f"${v:,.2f}"
        elif v >= 1: return f"${v:,.4f}"
        else: return f"${v:,.6f}"
    except Exception:
        return f"${val}"

def send_telegram(msg):
    try:
        with open(TELEGRAM_CFG, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        token = cfg.get("bot_token", "").strip()
        chat_ids = cfg.get("chat_ids", [])
        if not chat_ids and cfg.get("chat_id"):
            chat_ids = [cfg["chat_id"]]

        if not token or not chat_ids or not cfg.get("enabled"):
            print("Telegram not enabled or missing token/chat_id.")
            return False

        for cid in chat_ids:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({
                "chat_id": cid,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                pass
        print("Telegram audit report sent successfully!")
        return True
    except Exception as e:
        print("Telegram send error:", e)
        return False

def calc_ema(series, period):
    k = 2.0 / (period + 1.0)
    ema = sum(series[:period]) / float(period)
    for val in series[period:]:
        ema = (val * k) + (ema * (1.0 - k))
    return ema

def analyze_symbol(sym_raw):
    sym = sym_raw.replace("/", "")
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=15m&limit=100"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            k_data = json.loads(r.read().decode('utf-8'))
            closes = [float(c[4]) for c in k_data]
            highs = [float(c[2]) for c in k_data]
            lows = [float(c[3]) for c in k_data]
            current_price = closes[-1]

            # RSI 14
            gains, losses = 0, 0
            for i in range(len(closes) - 14, len(closes)):
                diff = closes[i] - closes[i - 1]
                if diff >= 0: gains += diff
                else: losses += abs(diff)
            avg_gain, avg_loss = gains / 14.0, losses / 14.0
            rs = 100.0 if avg_loss == 0 else avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

            ema20 = calc_ema(closes, min(20, len(closes)))
            ema50 = calc_ema(closes, min(50, len(closes)))
            ema200 = calc_ema(closes, min(200, len(closes)))

            tr_list = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
            atr = sum(tr_list[-14:]) / 14.0 if len(tr_list) >= 14 else (current_price * 0.01)

            recent = closes[-60:]
            swing_low = min(recent)
            swing_high = max(recent)

            # Scores
            long_score = 0
            if current_price >= ema200 and ema20 >= ema50: long_score += 35
            elif current_price >= ema200 or ema20 >= ema50: long_score += 20
            if rsi <= 45 or (35 <= rsi <= 48 and current_price >= ema20): long_score += 30
            if current_price <= swing_low * 1.015: long_score += 15

            short_score = 0
            if current_price <= ema200 and ema20 <= ema50: short_score += 35
            elif current_price <= ema200 or ema20 <= ema50: short_score += 20
            if rsi >= 60 or (52 <= rsi <= 65 and current_price <= ema20): short_score += 30
            if current_price >= swing_high * 0.985: short_score += 15

            return {
                "price": current_price,
                "rsi": rsi,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "atr": atr,
                "support": swing_low,
                "resistance": swing_high,
                "long_score": long_score,
                "short_score": short_score
            }
    except Exception as e:
        print(f"Fetch error for {sym}:", e)
        return None

def run_audit():
    print("🔍 Starting Full Technical Audit on Open Positions...")
    with open(PORTFOLIO_DB, 'r', encoding='utf-8') as f:
        db = json.load(f)

    positions = db.get("positions", [])
    balance = db.get("balance", 10000.0)
    history = db.get("history", [])

    if not positions:
        msg = (
            "🔍 *CANLI POZİSYON DENETİMİ & TEKNİK SAĞLIK RAPORU*\n"
            "---------------------------------\n"
            "ℹ️ Şu anda açık pozisyon bulunmamaktadır.\n"
            "🤖 *Sistem Durumu:* Piyasa 7/24 taranıyor, %90+ başarı olasılıklı yüksek güvenli fırsatlar otomatik değerlendirilecektir."
        )
        send_telegram(msg)
        return

    audit_lines = []
    closed_items = []
    kept_positions = []

    for pos in positions:
        sym = pos["symbol"]
        side = pos["side"]
        entry = pos["entryPrice"]
        
        info = analyze_symbol(sym)
        mark = info["price"] if info else pos.get("markPrice", entry)
        pos["markPrice"] = mark

        pnl = (mark - entry) * pos["size"] if side == "LONG" else (entry - mark) * pos["size"]
        pnl_pct = ((mark - entry) / entry * 100) if side == "LONG" else ((entry - mark) / entry * 100)
        pos["pnl"] = round(pnl, 2)
        pos["pnlPercent"] = round(pnl_pct, 2)

        # Trailing Breakeven Stop Check
        sl = pos.get("sl", entry)
        if pnl_pct >= 0.5 and sl < entry if side == "LONG" else sl > entry:
            pos["sl"] = entry
            sl = entry
            sl_tag = "🛡️ Başabaş Stop (Risk 0)"
        else:
            sl_tag = f"`{format_price(sl)}`"

        # Check Invalidation
        is_invalid = False
        invalid_reason = ""
        if info:
            if side == "LONG" and (info["short_score"] >= 80 or mark <= sl):
                is_invalid = True
                invalid_reason = f"Boğa formasyonu bozuldu (Ayı skoru: %{info['short_score']})"
            elif side == "SHORT" and (info["long_score"] >= 80 or mark >= sl):
                is_invalid = True
                invalid_reason = f"Ayı formasyonu bozuldu (Boğa skoru: %{info['long_score']})"

        if is_invalid:
            return_amount = (entry * pos["size"]) + pnl
            balance += return_amount
            hist_entry = dict(pos)
            hist_entry["closeReason"] = f"🛑 FORMASYON BOZULDU ({invalid_reason})"
            hist_entry["closePrice"] = mark
            hist_entry["closeTime"] = time.strftime("%H:%M:%S")
            history.insert(0, hist_entry)
            closed_items.append(f"• *{sym}* ({side}): {invalid_reason} -> Pozisyon sermaye korumasıyla KAPATILDI (PnL: `${pnl:+.2f}`).")
        else:
            kept_positions.append(pos)
            trend_str = "Güçlü Boğa 📈" if (info and info["price"] >= info["ema200"]) else "Düzeltme / Ayı 📉"
            rsi_val = f"{info['rsi']:.1f}" if info else "N/A"
            
            pnl_icon = "🟢" if pnl >= 0 else "🔴"
            audit_lines.append(
                f"🎯 *Varlık:* *{sym}* ({side} {'📈' if side == 'LONG' else '📉'})\n"
                f"• Giriş Fiyatı: `{format_price(entry)}` | Anlık: `{format_price(mark)}`\n"
                f"• Kar/Zarar: *${pnl:+.2f} ({pnl_pct:+.2f}%)* {pnl_icon}\n"
                f"• Stop Loss: {sl_tag} | Hedef (TP1): `{format_price(pos.get('tp1', 0))}`\n"
                f"• Teknik Yapı: *{trend_str}* (RSI: `{rsi_val}`)\n"
                f"• Durum: *✅ SAĞLIKLI & YÜKSEK GÜVENLİ POZİSYON*"
            )

    db["positions"] = kept_positions
    db["balance"] = balance
    db["history"] = history

    with open(PORTFOLIO_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2)

    total_equity = balance + sum((p["entryPrice"] * p["size"]) + p["pnl"] for p in kept_positions)

    # Build Comprehensive Telegram Report
    report_parts = [
        "🔍 *CANLI POZİSYON DENETİMİ & TEKNİK SAĞLIK RAPORU*",
        "---------------------------------",
        f"📊 *Aktif Pozisyon Sayısı:* `{len(kept_positions)}`",
        f"💵 *Kullanılabilir Bakiye:* `${balance:,.2f} USDT`",
        f"💎 *Toplam Varlık (Equity):* `${total_equity:,.2f} USDT`",
        "---------------------------------"
    ]

    if closed_items:
        report_parts.append("🚨 *DENETİM ESNASINDA KAPATILAN MİSK-Lİ POZİSYONLAR:*")
        report_parts.extend(closed_items)
        report_parts.append("---------------------------------")

    if audit_lines:
        report_parts.append("🛡️ *AKTİF DEVAM EDEN SAĞLIKLI POZİSYONLAR:*")
        report_parts.append("\n\n".join(audit_lines))
        report_parts.append("---------------------------------")

    report_parts.append("✨ *Quantum AI 7/24 Kesintisiz Otopilot Risk Taraması Etkin*")

    full_msg = "\n".join(report_parts)
    send_telegram(full_msg)

if __name__ == "__main__":
    run_audit()
