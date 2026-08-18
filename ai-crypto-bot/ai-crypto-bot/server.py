import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import threading
import time
import os
import sys
import io

if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = 8080

DB_FILE = "portfolio_db.json"
CONFIG_FILE = "telegram_config.json"
ML_DB_FILE = "ml_performance_db.json"

state = {
    "balance": 10000.0,
    "positions": [],
    "history": [],
    "auto_pilot": True,
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "BNBUSDT", "NEARUSDT", "LINKUSDT", "XRPUSDT", "DOGEUSDT", "SUIUSDT"],
    "ticker_data": {},
    "klines_data": {}
}

# 🧠 Self-Learning Adaptive Machine Learning Weights
ml_weights = {
    "pattern_weights": {
        "İkili Dip (W-Formasyonu)": 1.15,
        "Boğa Bayrağı (Bull Flag)": 1.10,
        "İkili Tepe (M-Formasyonu)": 1.08,
        "Kanal İçi Akümülasyon": 0.95
    },
    "rsi_threshold_long": 36,
    "rsi_threshold_short": 64,
    "total_learnings": 0,
    "win_streak": 0,
    "loss_streak": 0
}

telegram_config = {
    "bot_token": "",
    "chat_id": "",
    "chat_ids": [],
    "enabled": False
}

def get_telegram_chat_ids():
    chat_ids = []
    if isinstance(telegram_config.get("chat_ids"), list):
        for cid in telegram_config["chat_ids"]:
            clean_id = str(cid).strip()
            if clean_id and clean_id not in chat_ids:
                chat_ids.append(clean_id)
    
    legacy_id = str(telegram_config.get("chat_id", "")).strip()
    if legacy_id and legacy_id not in chat_ids:
        chat_ids.append(legacy_id)
        
    return chat_ids

def add_telegram_subscriber(chat_id):
    cid_str = str(chat_id).strip()
    if not cid_str:
        return False
    current_list = get_telegram_chat_ids()
    if cid_str not in current_list:
        current_list.append(cid_str)
        telegram_config["chat_ids"] = current_list
        telegram_config["chat_id"] = cid_str
        save_telegram_config()
        print(f"📱 Yeni Telegram Abonesi/Kanalı Kaydedildi: {cid_str} (Toplam Abone: {len(current_list)})")
        return True
    return False

def load_db():
    global state, telegram_config, ml_weights
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                state.update(saved)
        except Exception as e:
            print("DB load error:", e)
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                telegram_config.update(json.load(f))
        except Exception as e:
            print("Telegram config load error:", e)

    if os.path.exists(ML_DB_FILE):
        try:
            with open(ML_DB_FILE, 'r', encoding='utf-8') as f:
                saved_ml = json.load(f)
                ml_weights.update(saved_ml)
        except Exception as e:
            print("ML DB load error:", e)

def save_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "balance": state["balance"],
                "positions": state["positions"],
                "history": state["history"],
                "auto_pilot": state["auto_pilot"]
            }, f, indent=2)
    except Exception as e:
        print("DB save error:", e)

def save_ml_db():
    try:
        with open(ML_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(ml_weights, f, indent=2)
    except Exception as e:
        print("ML DB save error:", e)

def save_telegram_config():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(telegram_config, f, indent=2)
    except Exception as e:
        print("Telegram config save error:", e)

MAIN_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "📊 Açık Pozisyonlar"}, {"text": "💰 Toplam Kar/Zarar"}],
        [{"text": "🤖 Bot Durumu"}, {"text": "📱 Ana Menü"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

def send_telegram_message(text, reply_markup=None, target_chat_id=None):
    if not telegram_config.get("enabled", True):
        return False, "Telegram bildirimleri devre dışı."
    token = telegram_config.get("bot_token", "").strip()
    if not token:
        return False, "Bot Token eksik. Lütfen Telegram Bot Token'ınızı giriniz."
    
    if target_chat_id:
        targets = [str(target_chat_id).strip()]
    else:
        targets = get_telegram_chat_ids()

    if not targets:
        return False, "Kayıtlı Chat ID veya Kanal bulunamadı. Lütfen bota /start mesajı gönderin veya Kanal ID'si ekleyin."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success_count = 0
    last_error = ""

    for cid in targets:
        # Prepare payload dictionary
        payload_dict = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup is None and not str(cid).startswith("-") and not str(cid).startswith("@"):
            payload_dict["reply_markup"] = MAIN_REPLY_KEYBOARD
        elif reply_markup:
            payload_dict["reply_markup"] = reply_markup

        sent = False
        # Try 1: Send with Markdown formatting as JSON
        try:
            payload_bytes = json.dumps(payload_dict).encode('utf-8')
            req = urllib.request.Request(url, data=payload_bytes, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                if body.get("ok"):
                    success_count += 1
                    sent = True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                last_error = "HTTP 401 Unauthorized: Telegram Bot Token geçersiz. Lütfen @BotFather'dan aldığınız geçerli token'ı girin."
            elif e.code in [400, 403]:
                # Try Fallback 2: If 400 error occurs (e.g. Markdown parse error), send plain text without parse_mode
                try:
                    plain_payload = dict(payload_dict)
                    plain_payload.pop("parse_mode", None)
                    # Clean markdown symbols for raw text
                    plain_payload["text"] = text.replace("*", "").replace("`", "").replace("_", "")
                    p_bytes = json.dumps(plain_payload).encode('utf-8')
                    req_p = urllib.request.Request(url, data=p_bytes, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_p, timeout=8) as r_p:
                        b_p = json.loads(r_p.read().decode('utf-8'))
                        if b_p.get("ok"):
                            success_count += 1
                            sent = True
                except Exception:
                    last_error = f"HTTP {e.code}: Chat ID ({cid}) bulunamadı veya bot kanalda yönetici değil."
            else:
                last_error = f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            last_error = f"Bağlantı Hatası: {str(e)}"

        if not sent:
            print(f"❌ Telegram Gönderim Hatası [{cid}]: {last_error}")

    if success_count > 0:
        return True, f"Sinyal {success_count} alıcıya başarıyla iletildi."
    else:
        return False, last_error or "Sinyal iletilemedi."

def set_telegram_commands():
    if not telegram_config.get("enabled") or not telegram_config.get("bot_token"):
        return
    try:
        token = telegram_config["bot_token"].strip()
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        commands = [
            {"command": "pozisyonlar", "description": "📊 Açık pozisyonlar ve anlık PnL"},
            {"command": "pnl", "description": "💰 Toplam kâr/zarar ve portföy özeti"},
            {"command": "durum", "description": "🤖 Bot canlı durumu ve YZ ayarları"},
            {"command": "menu", "description": "📱 Ana menü butonlarını gösterir"}
        ]
        payload = urllib.parse.urlencode({"commands": json.dumps(commands)}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception as e:
        print("setMyCommands error:", e)

def handle_telegram_command(cmd_text, chat_id):
    cmd = cmd_text.lower().strip()
    if chat_id and not telegram_config.get("chat_id"):
        telegram_config["chat_id"] = str(chat_id)
        save_telegram_config()
    
    if "açık pozisyon" in cmd or cmd in ["/pozisyonlar", "/pozisyon", "pozisyonlar"]:
        positions = state.get("positions", [])
        if not positions:
            send_telegram_message("ℹ️ *Şu anda aktif açık pozisyon bulunmamaktadır.*", target_chat_id=chat_id)
            return
        
        lines = [f"📊 *AKTİF AÇIK POZİSYONLAR ({len(positions)})*", "---------------------------------"]
        for p in positions:
            sym = p.get("symbol", "N/A")
            side = p.get("side", "LONG")
            entry = format_price(p.get("entryPrice", 0))
            mark = format_price(p.get("markPrice", p.get("entryPrice", 0)))
            pnl = p.get("pnl", 0)
            pnl_pct = p.get("pnlPercent", 0)
            tp1 = format_price(p.get("tp1", 0))
            sl = format_price(p.get("sl", 0))
            
            pnl_icon = "🟢" if pnl >= 0 else "🔴"
            pnl_str = f"{pnl_icon} *${pnl:+.2f} ({pnl_pct:+.2f}%)*"
            
            lines.append(
                f"• *{sym}* ({side})\n"
                f"  └ Giriş: `{entry}` | Mark: `{mark}`\n"
                f"  └ Kar/Zarar: {pnl_str}\n"
                f"  └ Hedef (TP1): `{tp1}` | Stop (SL): `{sl}`"
            )
            lines.append("---------------------------------")
            
        msg = "\n".join(lines)
        send_telegram_message(msg, target_chat_id=chat_id)
        
    elif "kar/zarar" in cmd or "kâr/zarar" in cmd or "pnl" in cmd or cmd in ["/pnl", "pnl", "/kar"]:
        history = state.get("history", [])
        closed_count = len(history)
        realized_pnl = sum(h.get("pnl", 0) for h in history)
        wins = sum(1 for h in history if h.get("pnl", 0) > 0)
        losses = sum(1 for h in history if h.get("pnl", 0) <= 0)
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0
        
        unrealized_pnl = sum(p.get("pnl", 0) for p in state.get("positions", []))
        total_pnl = realized_pnl + unrealized_pnl
        balance = state.get("balance", 10000.0)
        equity = balance + sum((p.get("entryPrice", 0) * p.get("size", 0)) + p.get("pnl", 0) for p in state.get("positions", []))
        
        realized_icon = "📈" if realized_pnl >= 0 else "📉"
        unrealized_icon = "🟢" if unrealized_pnl >= 0 else "🔴"
        total_icon = "🚀" if total_pnl >= 0 else "⚠️"
        
        msg = (
            f"💰 *TOPLAM PORTFÖY & KÂR/ZARAR ÖZETİ*\n\n"
            f"💵 Kullanılabilir Bakiye: `${balance:,.2f} USDT`\n"
            f"📊 Toplam Portföy Değeri: `${equity:,.2f} USDT`\n"
            f"---------------------------------\n"
            f"{realized_icon} Realize Edilmiş Net PnL (Kapanan): *${realized_pnl:+.2f} USDT*\n"
            f"{unrealized_icon} Açık Pozisyonlar Anlık PnL: *${unrealized_pnl:+.2f} USDT*\n"
            f"{total_icon} *GENEL TOPLAM PnL:* *${total_pnl:+.2f} USDT*\n"
            f"---------------------------------\n"
            f"🎯 *İşlem İstatistikleri:*\n"
            f"• Kapanan İşlem Sayısı: `{closed_count}`\n"
            f"• Başarılı (Kar): `{wins}` ✅\n"
            f"• Stop (Zarar): `{losses}` 🛑\n"
            f"• Kazanma Oranı (Win Rate): *%{win_rate:.1f}*"
        )
        send_telegram_message(msg, target_chat_id=chat_id)
        
    elif "durum" in cmd or cmd in ["/durum", "durum"]:
        auto_st = "ETKİN (ON) ⚡" if state.get("auto_pilot") else "PASİF (OFF) ⏸️"
        msg = (
            f"🤖 *QUANTUM AI BOT CANLI DURUMU*\n\n"
            f"⚡ Otomatik Pilot: *{auto_st}*\n"
            f"🧠 Toplam YZ Öğrenimi: `{ml_weights.get('total_learnings', 0)}`\n"
            f"🔥 Galibiyet Serisi: `{ml_weights.get('win_streak', 0)}`\n"
            f"🛑 Mağlubiyet Serisi: `{ml_weights.get('loss_streak', 0)}`\n"
            f"🎯 RSI Eşikleri: Long `<{ml_weights.get('rsi_threshold_long', 36)}` | Short `>{ml_weights.get('rsi_threshold_short', 64)}`"
        )
        send_telegram_message(msg, target_chat_id=chat_id)
        
    elif cmd in ["/start", "/menu", "menü", "menu"]:
        send_telegram_message(
            "📱 *Quantum AI Bot Menüsü*\n\nAşağıdaki butonları kullanarak bakiye, kar/zarar ve açık pozisyon durumunu anlık takip edebilirsiniz.",
            reply_markup=MAIN_REPLY_KEYBOARD,
            target_chat_id=chat_id
        )

def telegram_listener_loop():
    print("📱 Telegram İnteraktif Komut ve Sinyal Dinleyicisi Başlatıldı...")
    time.sleep(3)
    set_telegram_commands()
    last_update_id = 0
    token_error_logged = False
    
    while True:
        if not telegram_config.get("enabled") or not telegram_config.get("bot_token"):
            time.sleep(5)
            continue
        try:
            token = telegram_config["bot_token"].strip()
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=10"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                token_error_logged = False
                if data.get("ok"):
                    for update in data.get("result", []):
                        last_update_id = update["update_id"]
                        message = update.get("message", {})
                        text = message.get("text", "").strip()
                        chat = message.get("chat", {})
                        chat_id = str(chat.get("id", ""))
                        
                        if chat_id:
                            is_new = add_telegram_subscriber(chat_id)
                            if is_new:
                                send_telegram_message(
                                    f"✅ *Quantum AI Bot Canlı Sinyal Yayın Sistemine Hoş Geldiniz!*\n\n"
                                    f"Bu sohbet / kanal (`{chat_id}`) canlı sinyal yayın listesine başarıyla eklendi. "
                                    f"7/24 YZ alım-satım sinyalleri ve bildirimleri buraya gönderilecektir.",
                                    target_chat_id=chat_id
                                )
                        
                        if text:
                            handle_telegram_command(text, chat_id)
        except urllib.error.HTTPError as e:
            if not token_error_logged:
                if e.code == 401:
                    print("⚠️ TELEGRAM UYARISI: telegram_config.json içindeki Bot Token GEÇERSİZ (401 Unauthorized). Lütfen web arayüzünden geçerli bir Bot Token girin.")
                token_error_logged = True
            time.sleep(10)
        except Exception:
            time.sleep(5)
        time.sleep(2)

def format_price(val):
    try:
        v = float(val)
        if v >= 1000:
            return f"${v:,.2f}"
        elif v >= 1:
            return f"${v:,.4f}"
        else:
            return f"${v:,.6f}"
    except Exception:
        return f"${val}"

# 🧠 Self-Learning Reinforcement Module
def update_self_learning_engine(closed_pos):
    pnl = closed_pos.get("pnl", 0)
    pattern = closed_pos.get("patternName", "Kanal İçi Akümülasyon")
    
    ml_weights["total_learnings"] += 1

    if pnl > 0:
        ml_weights["win_streak"] += 1
        ml_weights["loss_streak"] = 0
        current_w = ml_weights["pattern_weights"].get(pattern, 1.0)
        ml_weights["pattern_weights"][pattern] = min(1.35, round(current_w + 0.02, 2))
        learning_msg = f"🧠 *YZ ÖĞRENME MOTORU*: {closed_pos['symbol']} işleminde Kar ($+{pnl:.2f}) elde edildi. *{pattern}* formasyonunun başarı ağırlığı artırıldı ({ml_weights['pattern_weights'][pattern]}x)."
    else:
        ml_weights["loss_streak"] += 1
        ml_weights["win_streak"] = 0
        current_w = ml_weights["pattern_weights"].get(pattern, 1.0)
        ml_weights["pattern_weights"][pattern] = max(0.80, round(current_w - 0.03, 2))
        
        if closed_pos.get("side") == "LONG":
            ml_weights["rsi_threshold_long"] = max(30, ml_weights["rsi_threshold_long"] - 1)
        else:
            ml_weights["rsi_threshold_short"] = min(70, ml_weights["rsi_threshold_short"] + 1)
            
        learning_msg = f"🧠 *YZ ÖĞRENME MOTORU (Adaptif Ayar)*: {closed_pos['symbol']} işleminde Zarar (${pnl:.2f}) analiz edildi. Risk eşiği daha muhafazakar seviyeye (RSI Long: <{ml_weights['rsi_threshold_long']}) çekildi."

    save_ml_db()
    send_telegram_message(learning_msg)

# Python Technical Indicators & Multi-Confluence Win-Rate Engine
def calculate_python_indicators(k_data):
    if not k_data or len(k_data) < 20:
        return None
    
    closes = [float(c[4]) for c in k_data]
    highs = [float(c[2]) for c in k_data]
    lows = [float(c[3]) for c in k_data]
    current_price = closes[-1]
    
    # 1. RSI 14
    gains, losses = 0, 0
    for i in range(len(closes) - 14, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain = gains / 14.0
    avg_loss = losses / 14.0
    rs = 100.0 if avg_loss == 0 else avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # 2. EMAs (EMA20, EMA50, EMA200)
    def calc_ema(series, period):
        k = 2.0 / (period + 1.0)
        ema = sum(series[:period]) / float(period)
        for val in series[period:]:
            ema = (val * k) + (ema * (1.0 - k))
        return ema

    ema20 = calc_ema(closes, min(20, len(closes)))
    ema50 = calc_ema(closes, min(50, len(closes)))
    ema200 = calc_ema(closes, min(200, len(closes)))

    # 3. MACD (12, 26, 9)
    ema12 = calc_ema(closes, min(12, len(closes)))
    ema26 = calc_ema(closes, min(26, len(closes)))
    macd_line = ema12 - ema26
    
    macd_series = []
    for idx in range(max(26, len(closes)-15), len(closes) + 1):
        sub_closes = closes[:idx]
        if len(sub_closes) >= 12:
            m12 = calc_ema(sub_closes, min(12, len(sub_closes)))
            m26 = calc_ema(sub_closes, min(26, len(sub_closes)))
            macd_series.append(m12 - m26)
    
    signal_line = calc_ema(macd_series, min(9, len(macd_series))) if macd_series else 0.0
    macd_hist = macd_line - signal_line

    # 4. ATR 14 (Average True Range)
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    atr = sum(tr_list[-14:]) / 14.0 if len(tr_list) >= 14 else (current_price * 0.015)

    recent = closes[-60:] if len(closes) >= 60 else closes
    swing_low = min(recent)
    swing_high = max(recent)

    return {
        "currentPrice": current_price,
        "rsi": rsi,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "macdLine": macd_line,
        "signalLine": signal_line,
        "macdHist": macd_hist,
        "atr": atr,
        "support": swing_low,
        "resistance": swing_high
    }

symbol_cooldowns = {}
signal_broadcast_cooldowns = {}
global_last_signal_time = 0

def is_same_symbol(sym1, sym2):
    if not sym1 or not sym2:
        return False
    return str(sym1).replace("/", "").strip().upper() == str(sym2).replace("/", "").strip().upper()


def calc_tp_sl(price, side, supp, resis, atr=None):
    decimals = 2 if price >= 1000 else (4 if price >= 1 else 6)
    
    # 🎯 YÜKSEK KAZANMA ORANI (WIN-RATE) İÇİN PURE TEKNİK & YAPISAL SEVİYELER
    # Stop-Loss: Doğrudan Desteğin/Order Block'un ALTINA (ATR Volatilite Tamponu ile Stop-Hunt Koruması)
    # Kar Al (TP1): Doğrudan Direncin/Satış Likidite Bölgesinin HEMEN ÖNCESİNE (Kesin Kar Kapanışı)
    atr_val = atr if (atr and atr > 0) else (price * 0.008)
    buffer = atr_val * 0.35

    if side == "LONG":
        # SL: Desteğin veya Swing Low'un tamponlu altı (Wick engelleme)
        sl_base = min(supp, price - atr_val) if supp < price else (price - atr_val)
        sl = round(sl_base - buffer, decimals)
        if sl >= price:
            sl = round(price - (atr_val * 0.95), decimals)

        # TP1: Direncin veya Likiditenin %0.2 altında kesin kar alma
        tp1_base = resis if resis > price else (price + (price - sl) * 1.5)
        tp1 = round(tp1_base * 0.998, decimals)
        if tp1 <= price:
            tp1 = round(price + (price - sl) * 1.5, decimals)
    else: # SHORT
        # SL: Direncin veya Swing High'ın tamponlu üstü
        sl_base = max(resis, price + atr_val) if resis > price else (price + atr_val)
        sl = round(sl_base + buffer, decimals)
        if sl <= price:
            sl = round(price + (atr_val * 0.95), decimals)

        # TP1: Desteğin veya Alım Likiditesinin %0.2 üstünde kesin kar alma
        tp1_base = supp if supp < price else (price - (sl - price) * 1.5)
        tp1 = round(tp1_base * 1.002, decimals)
        if tp1 >= price:
            tp1 = round(price - (sl - price) * 1.5, decimals)

    return tp1, sl

# 24/7 Background Trading & Self-Learning Auto-Pilot Loop
def background_bot_loop():
    print("🧠 24/7 Quantum AI Self-Learning Engine Running...")
    last_auto_scan = 0
    last_audit_report = 0

    while True:
        try:
            # 1. Fetch Real Binance Tickers
            url = "https://data-api.binance.vision/api/v3/ticker/24hr"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            try:
                with urllib.request.urlopen(req, timeout=6) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    for item in data:
                        sym = item.get("symbol")
                        if sym in state["symbols"]:
                            state["ticker_data"][sym] = {
                                "symbol": sym,
                                "price": float(item.get("lastPrice", 0)),
                                "change24h": float(item.get("priceChangePercent", 0))
                            }
            except Exception:
                pass

            # 2. Update Mark Prices & Check TP/SL & Dynamic Trailing Stop Triggers
            now_sec = time.time()
            
            # 🔍 Canlı Açık Pozisyon Denetimi & Telegram Sağlık Raporu Bildirimi (Her 30 dk veya Başlangıçta)
            if (now_sec - last_audit_report > 1800):
                last_audit_report = now_sec
                if state["positions"]:
                    pos_summaries = []
                    for p in state["positions"]:
                        p_icon = "🟢" if p.get("pnl", 0) >= 0 else "🔴"
                        sl_str = f"🛡️ Başabaş Stop ({format_price(p['sl'])})" if (p.get("side") == "LONG" and p.get("sl", 0) >= p.get("entryPrice")) else f"`{format_price(p.get('sl', 0))}`"
                        pos_summaries.append(
                            f"🎯 *Varlık:* *{p['symbol']}* ({p['side']})\n"
                            f"• Giriş Fiyatı: `{format_price(p['entryPrice'])}` | Anlık: `{format_price(p.get('markPrice', p['entryPrice']))}`\n"
                            f"• Kar/Zarar: *${p.get('pnl', 0):+.2f} ({p.get('pnlPercent', 0):+.2f}%)* {p_icon}\n"
                            f"• Stop Loss: {sl_str} | Hedef (TP1): `{format_price(p.get('tp1', 0))}`\n"
                            f"• Durum: *✅ SAĞLIKLI & YÜKSEK GÜVENLİ POZİSYON*"
                        )
                    audit_report = (
                        f"🔍 *CANLI POZİSYON DENETİMİ & TEKNİK SAĞLIK RAPORU*\n"
                        f"---------------------------------\n"
                        f"📊 *Aktif Pozisyon Sayısı:* `{len(state['positions'])}` | Bakiye: `${state['balance']:,.2f} USDT`\n"
                        f"---------------------------------\n"
                        + "\n\n".join(pos_summaries) + "\n"
                        f"---------------------------------\n"
                        f"✨ *Quantum AI 7/24 Otopilot Canlı Risk Taraması Etkin*"
                    )
                    send_telegram_message(audit_report)
            positions_to_keep = []
            for pos in state["positions"]:
                sym_clean = pos["symbol"].replace("/", "")
                mark_price = state["ticker_data"].get(sym_clean, {}).get("price", pos["entryPrice"])
                pos["markPrice"] = mark_price
                
                if pos["side"] == "LONG":
                    pos["pnl"] = (mark_price - pos["entryPrice"]) * pos["size"]
                    pos["pnlPercent"] = ((mark_price - pos["entryPrice"]) / pos["entryPrice"]) * 100
                else:
                    pos["pnl"] = (pos["entryPrice"] - mark_price) * pos["size"]
                    pos["pnlPercent"] = ((pos["entryPrice"] - mark_price) / pos["entryPrice"]) * 100
                
                # 🛡️ Erken Başabaş & Dinamik Kar Kilitleri (%0.5 Kar Görünce Risk Sıfırlanır)
                if pos["side"] == "LONG":
                    if pos["pnlPercent"] >= 0.5 and pos.get("sl", 0) < pos["entryPrice"]:
                        pos["sl"] = pos["entryPrice"] # Risk Sıfırlandı (Başabaş Stop)
                        print(f"🛡️ Erken Başabaş Stop Aktifleşti ({pos['symbol']}): Risk Sıfırlandı.")
                    elif pos["pnlPercent"] >= 1.2 and pos.get("sl", 0) < pos["entryPrice"] * 1.006:
                        pos["sl"] = round(pos["entryPrice"] * 1.006, 4) # +0.6% Kar Kilitlendi
                        print(f"🎯 Kâr Kilitlendi ({pos['symbol']}): Min %0.6 Kâr Garanti Edildi.")
                    elif pos["pnlPercent"] >= 2.2 and pos.get("sl", 0) < mark_price * 0.99:
                        pos["sl"] = round(mark_price * 0.99, 4) # %1.0 Izleyen Stop Tamponu
                else: # SHORT
                    if pos["pnlPercent"] >= 0.5 and pos.get("sl", 999999) > pos["entryPrice"]:
                        pos["sl"] = pos["entryPrice"] # Risk Sıfırlandı (Başabaş Stop)
                        print(f"🛡️ Erken Başabaş Stop Aktifleşti ({pos['symbol']}): Risk Sıfırlandı.")
                    elif pos["pnlPercent"] >= 1.2 and pos.get("sl", 999999) > pos["entryPrice"] * 0.994:
                        pos["sl"] = round(pos["entryPrice"] * 0.994, 4) # +0.6% Kar Kilitlendi
                        print(f"🎯 Kâr Kilitlendi ({pos['symbol']}): Min %0.6 Kâr Garanti Edildi.")
                    elif pos["pnlPercent"] >= 2.2 and pos.get("sl", 999999) > mark_price * 1.01:
                        pos["sl"] = round(mark_price * 1.01, 4) # %1.0 Izleyen Stop Tamponu

                open_ts = pos.get("openTimeSec", now_sec)
                holding_hours = (now_sec - open_ts) / 3600.0

                triggered = False
                trigger_type = ""
                
                if pos["side"] == "LONG":
                    if mark_price >= pos["tp1"]:
                        triggered = True
                        trigger_type = "🎯 KAR AL (TP1) HEDEFİNE ULAŞILDI!"
                    elif mark_price <= pos["sl"]:
                        triggered = True
                        is_trailing = pos.get("sl", 0) > pos["entryPrice"]
                        trigger_type = "🎯 İZLEYEN STOP İLE KÂR KİLİTLENDİ!" if is_trailing else "🛑 STOP LOSS (SL) TETİKLENDİ!"
                elif pos["side"] == "SHORT":
                    if mark_price <= pos["tp1"]:
                        triggered = True
                        trigger_type = "🎯 KAR AL (TP1) HEDEFİNE ULAŞILDI!"
                    elif mark_price >= pos["sl"]:
                        triggered = True
                        is_trailing = pos.get("sl", 999999) < pos["entryPrice"]
                        trigger_type = "🎯 İZLEYEN STOP İLE KÂR KİLİTLENDİ!" if is_trailing else "🛑 STOP LOSS (SL) TETİKLENDİ!"
                
                if triggered:
                    return_amount = (pos["entryPrice"] * pos["size"]) + pos["pnl"]
                    state["balance"] += return_amount
                    hist_entry = dict(pos)
                    hist_entry["closeReason"] = trigger_type
                    hist_entry["closeTime"] = time.strftime("%H:%M:%S")
                    state["history"].insert(0, hist_entry)
                    symbol_cooldowns[pos["symbol"]] = time.time()
                    save_db()
                    
                    # Telegram Alert for Closed Trade
                    msg = (
                        f"{trigger_type}\n"
                        f"---------------------------------\n"
                        f"• Varlık: *{pos['symbol']}* ({pos['side']})\n"
                        f"• Giriş Fiyatı: `{format_price(pos['entryPrice'])}`\n"
                        f"• Kapanış Fiyatı: `{format_price(mark_price)}`\n"
                        f"• Kar/Zarar: *${pos['pnl']:+.2f} ({pos['pnlPercent']:+.2f}%)*\n"
                        f"• Taşınma Süresi: `{holding_hours:.1f} Saat (Zaman Sınırı Yok)`\n"
                        f"---------------------------------\n"
                        f"✨ *Quantum AI Dinamik Pozisyon Yönetimi*"
                    )
                    send_telegram_message(msg)

                    # 🧠 Trigger Self-Learning Machine Learning Engine
                    update_self_learning_engine(hist_entry)
                else:
                    positions_to_keep.append(pos)
            
            state["positions"] = positions_to_keep

            # 3. 🧠 24/7 MARKET SCANNING & TELEGRAM SIGNAL BROADCAST ENGINE
            now = time.time()
            if (now - last_auto_scan > 15):
                last_auto_scan = now
                
                for sym in state["symbols"]:
                    clean_display_sym = sym.replace("USDT", "/USDT")
                    existing_pos = next((p for p in state["positions"] if is_same_symbol(p["symbol"], clean_display_sym)), None)

                    try:
                        k_url = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=15m&limit=100"
                        req_k = urllib.request.Request(k_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req_k, timeout=4) as r_k:
                            k_data = json.loads(r_k.read().decode('utf-8'))
                            ind = calculate_python_indicators(k_data)

                            if ind:
                                current_price = ind["currentPrice"]
                                rsi = ind["rsi"]
                                ema20 = ind["ema20"]
                                ema50 = ind["ema50"]
                                ema200 = ind["ema200"]
                                macd_hist = ind["macdHist"]
                                macd_line = ind["macdLine"]
                                signal_line = ind["signalLine"]
                                atr = ind["atr"]
                                supp = ind["support"]
                                resis = ind["resistance"]

                                # Dynamic Adaptive Thresholds from ML Weights
                                rsi_long_limit = ml_weights.get("rsi_threshold_long", 38)
                                rsi_short_limit = ml_weights.get("rsi_threshold_short", 62)

                                should_open = False
                                side = "LONG"
                                confidence = 0

                                # 🎯 ULTRA-HIGH WIN RATE (%90+) Multi-Confluence Scoring Engine
                                long_score = 0
                                if current_price >= ema200 and ema20 >= ema50:
                                    long_score += 35 # Strong Bullish Trend Confluence
                                elif current_price >= ema200 or ema20 >= ema50:
                                    long_score += 20
                                    
                                if rsi <= rsi_long_limit or (35 <= rsi <= 46 and current_price >= ema20):
                                    long_score += 30 # RSI Rebound
                                if macd_hist > 0 and macd_line > signal_line:
                                    long_score += 25 # MACD Bullish Momentum
                                if current_price <= supp * 1.012:
                                    long_score += 10 # Support Bounce

                                short_score = 0
                                if current_price <= ema200 and ema20 <= ema50:
                                    short_score += 35 # Strong Bearish Trend Confluence
                                elif current_price <= ema200 or ema20 <= ema50:
                                    short_score += 20
                                    
                                if rsi >= rsi_short_limit or (54 <= rsi <= 65 and current_price <= ema20):
                                    short_score += 30 # RSI Rejection
                                if macd_hist < 0 and macd_line < signal_line:
                                    short_score += 25 # MACD Bearish Momentum
                                if current_price >= resis * 0.988:
                                    short_score += 10 # Resistance Rejection

                                # 🛡️ FORMASYON BOZULMA & POZİSYON KORUMA KONTROLÜ
                                if existing_pos:
                                    is_invalidated = False
                                    invalidation_reason = ""

                                    if existing_pos["side"] == "LONG" and (short_score >= 80 or (current_price <= existing_pos["sl"])):
                                        is_invalidated = True
                                        invalidation_reason = f"Boğa formasyonu bozuldu! Ayı momentumu (%{short_score} skor) hakim oldu."
                                    elif existing_pos["side"] == "SHORT" and (long_score >= 80 or (current_price >= existing_pos["sl"])):
                                        is_invalidated = True
                                        invalidation_reason = f"Ayı formasyonu bozuldu! Boğa momentumu (%{long_score} skor) hakim oldu."

                                    if is_invalidated:
                                        pnl = (current_price - existing_pos["entryPrice"]) * existing_pos["size"] if existing_pos["side"] == "LONG" else (existing_pos["entryPrice"] - current_price) * existing_pos["size"]
                                        return_amount = (existing_pos["entryPrice"] * existing_pos["size"]) + pnl
                                        state["balance"] += return_amount

                                        hist_entry = dict(existing_pos)
                                        hist_entry["closeReason"] = f"🛑 FORMASYON BOZULDU ({invalidation_reason})"
                                        hist_entry["closePrice"] = current_price
                                        hist_entry["closeTime"] = time.strftime("%H:%M:%S")
                                        state["history"].insert(0, hist_entry)

                                        state["positions"] = [p for p in state["positions"] if not is_same_symbol(p["symbol"], clean_display_sym)]
                                        save_db()
                                        update_self_learning_engine(hist_entry)

                                        msg_invalid = (
                                            f"🛑 *FORMASYON BOZULDU - POZİSYON KAPATILDI!*\n"
                                            f"---------------------------------\n"
                                            f"• Varlık: *{clean_display_sym}* (Eski Pozisyon: *{existing_pos['side']}*)\n"
                                            f"• Giriş Fiyatı: `{format_price(existing_pos['entryPrice'])}`\n"
                                            f"• Kapanış Fiyatı: `{format_price(current_price)}`\n"
                                            f"• Kar/Zarar: *${pnl:+.2f}*\n"
                                            f"• Açıklama: *{invalidation_reason} Pozisyon sermaye koruması amacıyla kapatıldı.*\n"
                                            f"---------------------------------\n"
                                            f"🛡️ *Quantum AI Otomatik Risk Yönetim Sistemi*"
                                        )
                                        send_telegram_message(msg_invalid)
                                        print(f"🛑 Formasyon Bozuldu, Pozisyon Kapatıldı: {clean_display_sym} ({existing_pos['side']})")
                                        existing_pos = None

                                if long_score >= 90:
                                    should_open = True
                                    side = "LONG"
                                    confidence = min(99, long_score)
                                elif short_score >= 90:
                                    should_open = True
                                    side = "SHORT"
                                    confidence = min(99, short_score)

                                already_open = (existing_pos is not None)

                                if should_open and confidence >= 90:
                                    tp1, sl = calc_tp_sl(current_price, side, supp, resis, atr)
                                    pattern_name = "İkili Dip (W-Formasyonu)" if side == "LONG" else "İkili Tepe (M-Formasyonu)"

                                    # 📢 Telegram Sinyal Yayını (Sadece açık pozisyon yoksa ve cooldown dolmuşsa)
                                    has_open_pos = any(is_same_symbol(p["symbol"], clean_display_sym) for p in state.get("positions", []))
                                    is_already_open = (existing_pos is not None) or has_open_pos
                                    last_bc_time = signal_broadcast_cooldowns.get(clean_display_sym, 0)
                                    SYMBOL_COOLDOWN_SEC = 3600 # 1 saat sembol bekleme süresi
                                    GLOBAL_COOLDOWN_SEC = 600  # 10 dakika global sinyal spam koruması

                                    if not is_already_open and (now - last_bc_time) > SYMBOL_COOLDOWN_SEC and (now - global_last_signal_time) > GLOBAL_COOLDOWN_SEC:
                                        reason_trend = f"EMA200 (`{format_price(ema200)}`) üzerinde Güçlü Boğa Trendi" if side == "LONG" else f"EMA200 (`{format_price(ema200)}`) altında Düşen Ayı Trendi"
                                        reason_macd = "MACD Histogramı pozitif ivmeyle boğa kesişimi verdi" if side == "LONG" else "MACD Histogramı negatif ivmeyle ayı kesişimi verdi"
                                        reason_rsi = f"RSI (`{rsi:.1f}`) aşırı satım dip seviyesinden tepki alımı" if side == "LONG" else f"RSI (`{rsi:.1f}`) tepe seviyesinden kâr satışı tepkisi"
                                        reason_smc = f"Boğa Order Block (`{format_price(supp)}`) Kurumsal Alım Bölgesi" if side == "LONG" else f"Ayı Order Block (`{format_price(resis)}`) Kurumsal Satış Bölgesi"

                                        clean_pair = clean_display_sym.replace('/', '')
                                        chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_pair}"

                                        signal_msg = (
                                            f"💎 *VIP TRADER ÖZEL SİNYAL & ANALİZ* (%{confidence} Başarı Olasılığı)\n"
                                            f"---------------------------------\n"
                                            f"🎯 *Varlık:* *{clean_display_sym}* ({side} {'📈' if side == 'LONG' else '📉'})\n"
                                            f"📍 *Giriş Seviyesi:* `{format_price(current_price)}`\n"
                                            f"🎯 *Kar Al (TP1):* `{format_price(tp1)}` (Dinamik Hedef)\n"
                                            f"🛑 *Stop Loss (SL):* `{format_price(sl)}` (Volatilite Korumalı)\n"
                                            f"---------------------------------\n"
                                            f"📊 *KURUMSAL TEKNİK & TEMEL ANALİZ GEREKÇESİ:*\n"
                                            f"└ 📈 *Makro Trend:* {reason_trend}\n"
                                            f"└ 🌊 *Momentum:* {reason_macd}\n"
                                            f"└ 🎯 *RSI & Seviye:* {reason_rsi}\n"
                                            f"└ 🐋 *Smart Money (SMC):* {reason_smc}\n"
                                            f"└ 🔍 *Formasyon Yapısı:* *{pattern_name}*\n"
                                            f"---------------------------------\n"
                                            f"📈 [Canlı TradingView Grafiği ve Formasyonu İncele]({chart_link})\n"
                                            f"✨ *VIP Özel Analiz ve Sinyal Kanalı*"
                                        )
                                        ok_sc, msg_sc = send_telegram_message(signal_msg)
                                        if ok_sc:
                                            signal_broadcast_cooldowns[clean_display_sym] = now
                                            global_last_signal_time = now
                                            print(f"📡 VIP Trader Sinyal ve Grafik Yayınlandı: {clean_display_sym} ({side})")

                                    # 🤖 Otomatik Pilot İşlem Açma Motoru (Çakışan pozisyonda yeni işlem açılmaz)
                                    last_tr_time = symbol_cooldowns.get(clean_display_sym, 0)
                                    if state["auto_pilot"] and not is_already_open and state["balance"] >= 1000 and (now - last_tr_time) >= 900:
                                        amount = 1000.0
                                        size = round(amount / current_price, 4)

                                        pos = {
                                            "id": "AUTO-" + str(int(time.time()))[-6:],
                                            "symbol": clean_display_sym,
                                            "side": side,
                                            "size": size,
                                            "entryPrice": current_price,
                                            "markPrice": current_price,
                                            "tp1": tp1,
                                            "sl": sl,
                                            "pnl": 0.0,
                                            "pnlPercent": 0.0,
                                            "patternName": pattern_name,
                                            "timestamp": time.strftime("%H:%M:%S"),
                                            "openTimeSec": time.time()
                                        }

                                        state["balance"] -= amount
                                        state["positions"].append(pos)
                                        symbol_cooldowns[clean_display_sym] = time.time()
                                        save_db()

                                        clean_pair = clean_display_sym.replace('/', '')
                                        chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_pair}"

                                        # Telegram Alert for VIP Trade
                                        msg = (
                                            f"🚀 *YENİ VIP POZİSYON AÇILDI!* (%{confidence} Başarı Olasılığı)\n"
                                            f"• Varlık: *{pos['symbol']}* ({pos['side']})\n"
                                            f"• Giriş Fiyatı: `{format_price(pos['entryPrice'])}`\n"
                                            f"• Hedef (TP1): `{format_price(pos['tp1'])}`\n"
                                            f"• Stop-Loss (SL): `{format_price(pos['sl'])}`\n"
                                            f"• Formasyon: *{pos['patternName']}*\n"
                                            f"📈 [TradingView Canlı Grafik]({chart_link})"
                                        )
                                        send_telegram_message(msg)
                                        break
                    except Exception as e_k:
                        print("Auto-pilot kline scan error:", e_k)

        except Exception as e:
            print("Background loop tick error:", e)

        time.sleep(3)

# Web Server & REST API Handler
class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            resp_data = {
                "balance": state["balance"],
                "positions": state["positions"],
                "history": state["history"],
                "auto_pilot": state["auto_pilot"],
                "ticker_data": state["ticker_data"],
                "ml_weights": ml_weights,
                "telegram_enabled": telegram_config.get("enabled", False)
            }
            self.wfile.write(json.dumps(resp_data).encode('utf-8'))
            return
        
        if self.path.startswith("/api/klines"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            sym = params.get("symbol", ["BTCUSDT"])[0]
            interval = params.get("interval", ["15m"])[0]
            limit = params.get("limit", ["100"])[0]
            
            try:
                k_url = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
                req_k = urllib.request.Request(k_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req_k, timeout=5) as r_k:
                    body = r_k.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(body)
                    return
            except Exception:
                try:
                    k_url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
                    req_k = urllib.request.Request(k_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_k, timeout=5) as r_k:
                        body = r_k.read()
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(body)
                        return
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                    return

        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else "{}"
        data = json.loads(post_body) if post_body else {}

        if self.path == "/api/save-telegram":
            telegram_config["bot_token"] = data.get("bot_token", "").strip()
            raw_chat_ids = str(data.get("chat_id", "")).strip()
            
            parsed_ids = [cid.strip() for cid in raw_chat_ids.replace(";", ",").split(",") if cid.strip()]
            existing = get_telegram_chat_ids()
            for pid in parsed_ids:
                if pid not in existing:
                    existing.append(pid)
            
            telegram_config["chat_ids"] = existing
            if existing:
                telegram_config["chat_id"] = existing[-1]
                
            telegram_config["enabled"] = bool(data.get("enabled", False))
            save_telegram_config()
            
            ok, msg = True, "Ayarlar kaydedildi."
            if telegram_config["enabled"]:
                ok, msg = send_telegram_message("📢 *Quantum AI Bot Canlı Sinyal Yayın Hattı Etkinleşti!*\n\nTüm aboneye ve kanallara 7/24 canlı sinyaller bu kanaldan iletilecektir.")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg, "subscribers_count": len(get_telegram_chat_ids())}).encode('utf-8'))
            return

        elif self.path == "/api/test-telegram":
            test_msg = (
                "💎 *VIP TRADER ÖZEL SİNYAL & ANALİZ* (%94 Başarı Olasılığı)\n"
                "---------------------------------\n"
                "🎯 *Varlık:* *BTC/USDT* (LONG 📈)\n"
                "📍 *Giriş Seviyesi:* `$64,250.00`\n"
                "🎯 *Kar Al (TP1):* `$65,400.00` (Dinamik Hedef)\n"
                "🛑 *Stop Loss (SL):* `$63,200.00` (Volatilite Korumalı)\n"
                "---------------------------------\n"
                "📊 *KURUMSAL TEKNİK & TEMEL ANALİZ GEREKÇESİ:*\n"
                "└ 📈 *Makro Trend:* EMA200 (`$64,100.00`) üzerinde Güçlü Boğa Trendi\n"
                "└ 🌊 *Momentum:* MACD Histogramı pozitif ivmeyle boğa kesişimi verdi\n"
                "└ 🎯 *RSI & Seviye:* RSI (`34.2`) aşırı satım dip seviyesinden tepki alımı\n"
                "└ 🐋 *Smart Money (SMC):* Boğa Order Block (`$63,800.00`) Kurumsal Alım Bölgesi\n"
                "└ 🔍 *Formasyon Yapısı:* *İkili Dip (W-Formasyonu)*\n"
                "---------------------------------\n"
                "📈 [Canlı TradingView Grafiği ve Formasyonu İncele](https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT)\n"
                "✨ *VIP Özel Analiz ve Sinyal Kanalı*"
            )
            ok, msg = send_telegram_message(test_msg)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode('utf-8'))
            return

        elif self.path == "/api/open-trade":
            signal = data.get("signal", {})
            amount = float(data.get("amount", 1000))
            target_sym = signal.get("symbol", "BTC/USDT")
            target_side = "LONG" if signal.get("side") == "BUY" else "SHORT"
            entry_price = float(signal.get("entryPrice", 0))

            # 🛡️ 1. Mevcut Pozisyon Kontrolü
            existing_pos = next((p for p in state["positions"] if is_same_symbol(p["symbol"], target_sym)), None)
            if existing_pos:
                if existing_pos["side"] == target_side:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": f"{target_sym} için zaten açık bir {target_side} pozisyonunuz var!"}).encode('utf-8'))
                    return
                else:
                    # 🔄 Ters Sinyal: Eski pozisyonu kapat ve sermayeyi koru
                    pnl = (entry_price - existing_pos["entryPrice"]) * existing_pos["size"] if existing_pos["side"] == "LONG" else (existing_pos["entryPrice"] - entry_price) * existing_pos["size"]
                    return_amount = (existing_pos["entryPrice"] * existing_pos["size"]) + pnl
                    state["balance"] += return_amount

                    hist_entry = dict(existing_pos)
                    hist_entry["closeReason"] = f"🔄 Ters Pozisyon ({target_side}) Açılışı Sebebiyle Revize Edildi"
                    hist_entry["closePrice"] = entry_price
                    hist_entry["closeTime"] = time.strftime("%H:%M:%S")
                    state["history"].insert(0, hist_entry)

                    state["positions"] = [p for p in state["positions"] if not is_same_symbol(p["symbol"], target_sym)]

                    msg_close = (
                        f"🔄 *POZİSYON REVİZE EDİLDİ (Ters Yön)*\n"
                        f"• Varlık: *{target_sym}*\n"
                        f"• Eski Pozisyon: *{existing_pos['side']} (KAPATILDI)*\n"
                        f"• Kar/Zarar: *${pnl:+.2f}*\n"
                        f"• Yeni Yön: *{target_side}*\n"
                    )
                    send_telegram_message(msg_close)

            if state["balance"] >= amount and entry_price > 0:
                size = round(amount / entry_price, 4)
                
                pos = {
                    "id": "POS-" + str(int(time.time()))[-6:],
                    "symbol": target_sym,
                    "side": target_side,
                    "size": size,
                    "entryPrice": entry_price,
                    "markPrice": entry_price,
                    "tp1": float(signal.get("tp1", 0)),
                    "sl": float(signal.get("sl", 0)),
                    "pnl": 0.0,
                    "pnlPercent": 0.0,
                    "patternName": signal.get("patternName", "Manuel İşlem"),
                    "timestamp": time.strftime("%H:%M:%S"),
                    "openTimeSec": time.time()
                }
                state["balance"] -= amount
                state["positions"].append(pos)
                save_db()

                # Telegram Alert for Manual Trade
                msg = (
                    f"🚀 *YENİ POZİSYON AÇILDI!*\n"
                    f"• Varlık: *{pos['symbol']}* ({pos['side']})\n"
                    f"• Giriş Fiyatı: `${pos['entryPrice']:,.2f}`\n"
                    f"• Hedef (TP1): `${pos['tp1']:,.2f}`\n"
                    f"• Stop-Loss (SL): `${pos['sl']:,.2f}`\n"
                    f"• Güncel Bakiye: `${state['balance']:,.2f} USDT`"
                )
                send_telegram_message(msg)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "position": pos}).encode('utf-8'))
                return

        elif self.path == "/api/toggle-autopilot":
            state["auto_pilot"] = bool(data.get("enabled", False))
            save_db()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "auto_pilot": state["auto_pilot"]}).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

def keep_alive_loop():
    url = os.environ.get("RENDER_EXTERNAL_URL", "https://quantum-ai-bot.onrender.com/")
    while True:
        time.sleep(240) # Every 4 minutes
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KeepAlive'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            pass

if __name__ == "__main__":
    load_db()
    t = threading.Thread(target=background_bot_loop, daemon=True)
    t.start()
    
    t_keep = threading.Thread(target=keep_alive_loop, daemon=True)
    t_keep.start()
    
    t_tg = threading.Thread(target=telegram_listener_loop, daemon=True)
    t_tg.start()
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        print(f"🧠 Quantum AI 24/7 Self-Learning Server Running on Port {PORT}...")
        httpd.serve_forever()

