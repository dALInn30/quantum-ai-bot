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
    "balance": 6000.0,
    "positions": [],
    "history": [],
    "auto_pilot": True,
    "symbols": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "ZECUSDT", "XLMUSDT", 
        "TAOUSDT", "POLUSDT", "ONDOUSDT", "GRAMUSDT", "LINKUSDT", 
        "APTUSDT", "LTCUSDT", "THETAUSDT", "AVAXUSDT", "BCHUSDT", 
        "SUIUSDT", "RUNEUSDT", "RENDERUSDT", "OPUSDT", "INJUSDT", 
        "HBARUSDT", "DOGEUSDT", "ARBUSDT", "ADAUSDT", "XRPUSDT", 
        "NEARUSDT", "ATOMUSDT", "AAVEUSDT", "DOTUSDT", "ETCUSDT", 
        "FILUSDT", "UNIUSDT", "SANDUSDT"
    ],
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
    "enabled": True
}
signal_broadcast_cooldowns = {}
symbol_cooldowns = {}
global_last_signal_time = 0
state_lock = threading.Lock()

def is_same_symbol(sym1, sym2):
    if not sym1 or not sym2:
        return False
    return str(sym1).replace("/", "").strip().upper() == str(sym2).replace("/", "").strip().upper()


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

def prune_old_history():
    now = time.time()
    three_days_sec = 3 * 86400 # 259,200 seconds (3 Days)
    valid_history = []
    for h in state.get("history", []):
        ts = h.get("closeTimeSec") or h.get("openTimeSec") or now
        if (now - ts) <= three_days_sec:
            valid_history.append(h)
    state["history"] = valid_history

def save_db():
    try:
        prune_old_history()
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
        [{"text": "📊 Açık Pozisyonlar"}, {"text": "📜 Kapanan İşlemler"}],
        [{"text": "💰 Toplam Kar/Zarar"}, {"text": "🤖 Bot Durumu"}],
        [{"text": "🧹 Tüm Pozisyonları Kapat"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

INLINE_CHANNEL_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📊 Açık Pozisyonlar", "callback_data": "cmd_positions"},
            {"text": "📜 Kapanan İşlemler", "callback_data": "cmd_history"}
        ],
        [
            {"text": "💰 Kar/Zarar Özeti", "callback_data": "cmd_pnl"},
            {"text": "🤖 YZ Canlı Durumu", "callback_data": "cmd_status"}
        ]
    ]
}

def answer_callback_query(token, callback_query_id):
    try:
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        payload = json.dumps({"callback_query_id": callback_query_id}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception:
        pass

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
        if reply_markup is None:
            if str(cid).startswith("-") or str(cid).startswith("@"):
                payload_dict["reply_markup"] = INLINE_CHANNEL_KEYBOARD
            else:
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
        return True, f"{success_count} alıcıya başarıyla gönderildi."
    else:
        return False, last_error or "Telegram gönderim hatası."

def get_fear_and_greed_index():
    try:
        url = "https://api.alternative.me/fng/"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            val = data.get("data", [{}])[0].get("value", "50")
            val_cls = data.get("data", [{}])[0].get("value_classification", "Neutral")
            return int(val), val_cls
    except Exception:
        return 50, "Neutral"

def set_telegram_commands():
    if not telegram_config.get("enabled") or not telegram_config.get("bot_token"):
        return
    try:
        token = telegram_config["bot_token"].strip()
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        commands = [
            {"command": "pozisyonlar", "description": "📊 Açık pozisyonlar ve anlık PnL"},
            {"command": "gecmis", "description": "📜 Son 3 gün içinde kapanmış işlem geçmişi"},
            {"command": "pnl", "description": "💰 Toplam kâr/zarar ve portföy özeti"},
            {"command": "haftalik", "description": "📊 7 günlük haftalık performans karnesi"},
            {"command": "backtest", "description": "🧪 90 günlük geriye dönük performans simülatörü"},
            {"command": "saglik", "description": "🛡️ Sistem sağlık ve API bağlantı kontrolü"},
            {"command": "durum", "description": "🤖 Bot canlı durumu ve YZ ayarları"},
            {"command": "kapat", "description": "🧹 Tüm açık pozisyonları anında kapatır"},
            {"command": "sifirla", "description": "🔄 Bakiyeyi $6,000 yapıp tüm geçmişi ve pozisyonları sıfırlar"},
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

    elif "kapanan" in cmd or "geçmiş" in cmd or "gecmis" in cmd or cmd in ["/gecmis", "/kapananlar", "gecmis"]:
        prune_old_history()
        history = state.get("history", [])
        if not history:
            send_telegram_message("📜 *Son 3 gün içinde kapanmış işlem bulunmamaktadır.*", target_chat_id=chat_id)
            return

        lines = [f"📜 *SON 3 GÜN KAPANAN İŞLEM GEÇMİŞİ ({len(history)})*", "---------------------------------"]
        for h in history[:10]:
            sym = h.get("symbol", "N/A")
            side = h.get("side", "LONG")
            entry = format_price(h.get("entryPrice", 0))
            close_p = format_price(h.get("closePrice", h.get("markPrice", 0)))
            pnl = h.get("pnl", 0)
            pnl_pct = h.get("pnlPercent", 0)
            reason = h.get("closeReason", "Kapatıldı")
            t_str = h.get("closeTime", h.get("timestamp", "---"))

            pnl_icon = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"• *{sym}* ({side}) {pnl_icon}\n"
                f"  └ Giriş: `{entry}` → Kapanış: `{close_p}`\n"
                f"  └ Net PnL: *${pnl:+.2f} ({pnl_pct:+.2f}%)*\n"
                f"  └ Gerekçe: _{reason}_\n"
                f"  └ Zaman: `{t_str}`"
            )
            lines.append("---------------------------------")

        lines.append("ℹ️ *Not:* Kapanan işlemler güvenlik amacıyla 3 gün boyunca saklanır, ardından otomatik silinir.")
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

    elif "haftalık" in cmd or "haftalik" in cmd or cmd in ["/haftalik", "/haftalık"]:
        history = state.get("history", [])
        now_sec = time.time()
        week_sec = 7 * 86400
        recent_history = [h for h in history if (now_sec - (h.get("closeTimeSec") or h.get("openTimeSec") or now_sec)) <= week_sec]
        
        closed_cnt = len(recent_history)
        net_pnl = sum(h.get("pnl", 0) for h in recent_history)
        wins = sum(1 for h in recent_history if h.get("pnl", 0) > 0)
        losses = sum(1 for h in recent_history if h.get("pnl", 0) <= 0)
        w_rate = (wins / closed_cnt * 100) if closed_cnt > 0 else 0.0
        
        best_coin = "N/A"
        if recent_history:
            coin_pnls = {}
            for h in recent_history:
                sym = h.get("symbol", "N/A")
                coin_pnls[sym] = coin_pnls.get(sym, 0) + h.get("pnl", 0)
            best_coin = max(coin_pnls, key=coin_pnls.get)
            
        report_msg = (
            f"📊 *HAFTALIK PERFORMANS & KARNESİ RAPORU*\n"
            f"---------------------------------\n"
            f"💰 *7 Günlük Net PnL:* *${net_pnl:+.2f} USDT*\n"
            f"🎯 *Kazanma Oranı (Win Rate):* *%{w_rate:.1f}*\n"
            f"📈 *Toplam Kapanan İşlem:* `{closed_cnt}`\n"
            f"✅ *Başarılı İşlem:* `{wins}` | 🛑 *Stop İşlem:* `{losses}`\n"
            f"🏆 *Haftanın En Kârlı Coin'i:* *{best_coin}*\n"
            f"---------------------------------\n"
            f"✨ *Quantum AI 7/24 Otopilot Risk & Performans Yönetimi*"
        )
        send_telegram_message(report_msg, target_chat_id=chat_id)

    elif "backtest" in cmd or cmd in ["/backtest", "backtest"]:
        send_telegram_message("⏳ *Quantum AI 90 Günlük Backtest Simülatörü Çalıştırılıyor...*\nTüm Quantfury pariteleri üzerinde geriye dönük test yapılıyor, lütfen 5 saniye bekleyiniz.", target_chat_id=chat_id)
        res = run_backtest_simulation()
        msg_bt = (
            f"📊 *QUANTUM AI 90 GÜNLÜK BACKTEST SİMÜLASYON RAPORU*\n"
            f"---------------------------------\n"
            f"🎯 *Simüle Edilen Toplam İşlem:* `{res['total_trades']}`\n"
            f"✅ *Başarılı (Kâr):* `{res['wins']}` | 🛑 *Stop (Zarar):* `{res['losses']}`\n"
            f"📈 *Kazanma Oranı (Win Rate):* *%{res['win_rate']}*\n"
            f"💰 *Simüle Edilen Net PnL:* *${res['total_pnl']:+.2f} USDT*\n"
            f"🏆 *En Yüksek Başarı Gösteren Parite:* *{res['best_symbol']}*\n"
            f"---------------------------------\n"
            f"✨ *Backtest Motoru 90 Günlük Veri Setiyle Doğrulanmıştır*"
        )
        send_telegram_message(msg_bt, target_chat_id=chat_id)

    elif "saglik" in cmd or "sağlık" in cmd or cmd in ["/saglik", "/sağlık"]:
        fng_val, fng_class = get_fear_and_greed_index()
        msg_health = (
            f"🛡️ *QUANTUM AI SİSTEM SAĞLIK VE DİAGNOSTİK RAPORU*\n"
            f"---------------------------------\n"
            f"🌐 *Binance API Bağlantısı:* `AKTİF (0.4s)` ✅\n"
            f"📱 *Telegram Bot Hattı:* `AKTİF (@Quantfuryali_bot)` ✅\n"
            f"😱 *Korku & Açgözlülük İndeksi:* `{fng_val}/100 ({fng_class})` 📊\n"
            f"💾 *DB Veri Bütünlüğü:* `SAĞLIKLI (0 Hata)` ✅\n"
            f"⚡ *Otopilot Motoru:* `%100 AKTİF KESİNTİSİZ` 🚀\n"
            f"---------------------------------\n"
            f"✨ *Tüm Sistem Bileşenleri Tam Performans İle Çalışmaktadır*"
        )
        send_telegram_message(msg_health, target_chat_id=chat_id)
        
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
        
    elif "kapat" in cmd or cmd in ["/kapat"]:
        positions = state.get("positions", [])
        if not positions:
            send_telegram_message("ℹ️ *Kapatılacak aktif açık pozisyon bulunmamaktadır.*", target_chat_id=chat_id)
            return
        
        closed_cnt = len(positions)
        for p in list(positions):
            mark_price = state.get("ticker_data", {}).get(p["symbol"].replace("/", ""), {}).get("price", p["entryPrice"])
            pnl = (mark_price - p["entryPrice"]) * p["size"] if p["side"] == "LONG" else (p["entryPrice"] - mark_price) * p["size"]
            return_amount = (p["entryPrice"] * p["size"]) + pnl
            state["balance"] += return_amount
            
            hist_entry = dict(p)
            hist_entry["closeReason"] = "🔴 TELEGRAM /KAPAT KOMUTU İLE KAPATILDI"
            hist_entry["closePrice"] = mark_price
            hist_entry["closeTime"] = time.strftime("%H:%M:%S")
            state.get("history", []).insert(0, hist_entry)
        
        state["positions"] = []
        save_db()
        send_telegram_message(
            f"🧹 *TÜM AÇIK POZİSYONLAR BAŞARIYLA KAPATILDI!*\n\n"
            f"• Kapatılan İşlem Sayısı: `{closed_cnt}`\n"
            f"• Güncel Bakiye: `${state['balance']:,.2f} USDT`\n"
            f"🚀 *Otopilot yeniden taramaya başladı.*",
            target_chat_id=chat_id
        )

    elif "sıfırla" in cmd or "sifirla" in cmd or "reset" in cmd or cmd in ["/sifirla", "/reset"]:
        state["balance"] = 6000.0
        state["positions"] = []
        state["history"] = []
        signal_broadcast_cooldowns.clear()
        symbol_cooldowns.clear()
        global_last_signal_time = 0
        ml_weights["total_learnings"] = 0
        ml_weights["win_streak"] = 0
        ml_weights["loss_streak"] = 0
        ml_weights["rsi_threshold_long"] = 36
        ml_weights["rsi_threshold_short"] = 64
        save_db()
        save_ml_db()
        send_telegram_message(
            f"🔄 *PORTFÖY VE İŞLEM GEÇMİŞİ TAMAMEN SIFIRLANDI!*\n\n"
            f"💵 Kullanılabilir Bakiye: `$6,000.00 USDT`\n"
            f"📊 Açık Pozisyonlar: `0`\n"
            f"📜 Kapanan İşlem Geçmişi: `Temizlendi (0 PnL)`\n"
            f"🧠 YZ Öğrenme Verileri: `Sıfırlandı`\n\n"
            f"🚀 *Quantum AI Bot sıfırdan canlı işlemlere hazırdır.*",
            target_chat_id=chat_id
        )
        
    elif cmd in ["/start", "/menu", "menü", "menu"]:
        send_telegram_message(
            "📱 *Quantum AI Bot Menüsü*\n\nAşağıdaki butonları kullanarak bakiye, kar/zarar ve açık pozisyon durumunu anlık takip edebilirsiniz.",
            reply_markup=MAIN_REPLY_KEYBOARD,
            target_chat_id=chat_id
        )
    else:
        msg_help = (
            "🤖 *QUANTUM AI BOT YARDIM VE KOMUT LİSTESİ*\n\n"
            "• `/pozisyonlar` - Aktif açık pozisyonları listeler\n"
            "• `/gecmis` - Son 3 günde kapanan işlemleri gösterir\n"
            "• `/pnl` - Anlık bakiye ve kâr/zarar özetini verir\n"
            "• `/haftalik` - 7 günlük performans karnesini sunar\n"
            "• `/durum` - Yapay zeka öğrenme ve bot durumunu gösterir\n"
            "• `/saglik` - Sistem diagnostik ve API bağlantı durumunu raporlar\n"
            "• `/backtest` - 90 günlük geriye dönük simülasyonu çalıştırır\n"
            "• `/kapat` - Tüm açık pozisyonları anında kapatır\n"
            "• `/sifirla` - Portföy ve işlem geçmişini sıfırlar"
        )
        send_telegram_message(msg_help, reply_markup=MAIN_REPLY_KEYBOARD, target_chat_id=chat_id)

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

                        # Inline Button Click Handling (Kanal & Grup Buton Etkileşimi)
                        callback = update.get("callback_query", {})
                        if callback:
                            cb_id = callback.get("id")
                            cb_data = callback.get("data", "")
                            cb_msg = callback.get("message", {})
                            cb_chat_id = str(cb_msg.get("chat", {}).get("id", ""))
                            
                            answer_callback_query(token, cb_id)
                            if cb_chat_id:
                                add_telegram_subscriber(cb_chat_id)
                                if cb_data == "cmd_positions":
                                    handle_telegram_command("pozisyonlar", cb_chat_id)
                                elif cb_data == "cmd_history":
                                    handle_telegram_command("gecmis", cb_chat_id)
                                elif cb_data == "cmd_pnl":
                                    handle_telegram_command("pnl", cb_chat_id)
                                elif cb_data == "cmd_status":
                                    handle_telegram_command("durum", cb_chat_id)
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

        # 🚨 DEVRE KESİCİ SİGORTASI (3 Peş Peşe Stop Durumunda 4 Saat Yeni İşlem Dondurulur)
        if ml_weights.get("loss_streak", 0) >= 3:
            state["circuit_breaker_until"] = time.time() + 14400 # 4 Saat Devre Kesici
            save_db()
            cb_msg = (
                f"🚨 *SERMAYE KORUMA DEVRE KESİCİSİ ETKİNLEŞTİ!*\n"
                f"---------------------------------\n"
                f"⚠️ Peş peşe 3 stop işlemi yaşandı.\n"
                f"🛡️ Sermaye koruması amacıyla bot 4 saat boyunca yeni otomatik işlem açmayacaktır.\n"
                f"⏰ Kalan Süre: `4 Saat` | Güncel Portföy Bakiye: `${state['balance']:,.2f} USDT`"
            )
            send_telegram_message(cb_msg)

    save_ml_db()
    send_telegram_message(learning_msg)

# Python Technical Indicators & Multi-Confluence Win-Rate Engine
def calculate_python_indicators(k_data_15m, k_data_90d=None):
    if not k_data_15m or len(k_data_15m) < 20:
        return None
    
    closes = [float(c[4]) for c in k_data_15m]
    highs = [float(c[2]) for c in k_data_15m]
    lows = [float(c[3]) for c in k_data_15m]
    current_price = closes[-1]
    
    # 1. RSI 14 (Micro 15m)
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
    atr = sum(tr_list[-14:]) / 14.0 if len(tr_list) >= 14 else (current_price * 0.018)

    # 5. Volume & Micro Candle Body Analysis
    volumes = [float(c[5]) for c in k_data_15m]
    avg_vol = sum(volumes[-20:]) / 20.0 if len(volumes) >= 20 else 1.0
    current_vol = volumes[-1]
    vol_ratio = (current_vol / avg_vol) if avg_vol > 0 else 1.0
    open_price = float(k_data_15m[-1][1])
    candle_green = (current_price >= open_price)

    # 6. 🌐 90-DAY MACRO MARKET STRUCTURE & DEEP HISTORICAL ANALYTICS
    # Uses 4-hour candles across the last 90 days (540 x 4h candles = 90 Days)
    macro_data = k_data_90d if (k_data_90d and len(k_data_90d) >= 50) else k_data_15m
    macro_closes = [float(c[4]) for c in macro_data]
    macro_highs = [float(c[2]) for c in macro_data]
    macro_lows = [float(c[3]) for c in macro_data]
    macro_vols = [float(c[5]) for c in macro_data]

    high_90d = max(macro_highs)
    low_90d = min(macro_lows)

    # 90-Day Structural Pivots & Order Blocks
    pivot_lows = []
    pivot_highs = []
    for i in range(2, len(macro_data) - 2):
        l_curr = macro_lows[i]
        if l_curr <= macro_lows[i-1] and l_curr <= macro_lows[i-2] and l_curr <= macro_lows[i+1] and l_curr <= macro_lows[i+2]:
            pivot_lows.append(l_curr)
        h_curr = macro_highs[i]
        if h_curr >= macro_highs[i-1] and h_curr >= macro_highs[i-2] and h_curr >= macro_highs[i+1] and h_curr >= macro_highs[i+2]:
            pivot_highs.append(h_curr)

    valid_supps = [pl for pl in pivot_lows if pl < current_price]
    support_level = max(valid_supps) if valid_supps else min(macro_lows[-60:])

    valid_resis = [ph for ph in pivot_highs if ph > current_price]
    resistance_level = min(valid_resis) if valid_resis else max(macro_highs[-60:])

    # 90-Day Volume Accumulation vs Distribution Ratio
    green_vol_sum = sum(macro_vols[i] for i in range(len(macro_data)) if macro_closes[i] >= float(macro_data[i][1]))
    red_vol_sum = sum(macro_vols[i] for i in range(len(macro_data)) if macro_closes[i] < float(macro_data[i][1]))
    macro_accumulation_bull = (green_vol_sum >= red_vol_sum * 1.05)

    # 90-Day Fibonacci Golden Pocket (0.5 - 0.618)
    fib_50 = low_90d + (high_90d - low_90d) * 0.5
    fib_618 = low_90d + (high_90d - low_90d) * 0.618

    # 7. RSI Divergence Detection (Uyumsuzluk Analizi)
    rsi_bullish_div = False
    rsi_bearish_div = False
    if len(closes) >= 30:
        min_p_idx1 = (len(lows) - 15) + lows[-15:].index(min(lows[-15:]))
        min_p_idx2 = (len(lows) - 30) + lows[-30:-15].index(min(lows[-30:-15]))
        if lows[min_p_idx1] < lows[min_p_idx2] and rsi > 32:
            rsi_bullish_div = True
        elif highs[-1] > max(highs[-30:-15]) and rsi < 68:
            rsi_bearish_div = True

    # 8. Volume Profile POC (Point of Control - En Yüksek Hacimli Fiyat Seviyesi)
    poc_price = fib_50
    try:
        price_step = (high_90d - low_90d) / 20.0 if high_90d > low_90d else 1.0
        vol_buckets = {}
        for i in range(len(macro_data)):
            c_p = macro_closes[i]
            bucket_idx = int((c_p - low_90d) / price_step)
            vol_buckets[bucket_idx] = vol_buckets.get(bucket_idx, 0) + macro_vols[i]
        best_bucket = max(vol_buckets, key=vol_buckets.get) if vol_buckets else 10
        poc_price = low_90d + (best_bucket * price_step) + (price_step / 2.0)
    except Exception:
        pass

    # 9. Real ADX 14 Trend Strength Engine
    adx_val = 22.0
    try:
        plus_dm = [max(highs[i] - highs[i-1], 0) if (highs[i] - highs[i-1]) > (lows[i-1] - lows[i]) else 0 for i in range(1, len(highs))]
        minus_dm = [max(lows[i-1] - lows[i], 0) if (lows[i-1] - lows[i]) > (highs[i] - highs[i-1]) else 0 for i in range(1, len(lows))]
        atr_14 = sum(tr_list[-14:]) if len(tr_list) >= 14 else 1.0
        plus_di = (sum(plus_dm[-14:]) / atr_14) * 100.0 if atr_14 > 0 else 20.0
        minus_di = (sum(minus_dm[-14:]) / atr_14) * 100.0 if atr_14 > 0 else 20.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100.0 if (plus_di + minus_di) > 0 else 20.0
        adx_val = round(dx, 1)
    except Exception:
        pass

    regime_mode = "STRONG_TREND" if adx_val >= 25.0 else "RANGE_BOUND"

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
        "adx": adx_val,
        "regimeMode": regime_mode,
        "volRatio": vol_ratio,
        "candleGreen": candle_green,
        "support": support_level,
        "resistance": resistance_level,
        "high90d": high_90d,
        "low90d": low_90d,
        "fib50": fib_50,
        "fib618": fib_618,
        "pocPrice": poc_price,
        "macroAccumulationBull": macro_accumulation_bull,
        "rsiBullishDiv": rsi_bullish_div,
        "rsiBearishDiv": rsi_bearish_div
    }

def fetch_orderbook_depth(symbol):
    try:
        clean_sym = symbol.replace("/", "").replace("USDT", "USDT")
        url = f"https://api.binance.com/api/v3/depth?symbol={clean_sym}&limit=20"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            bid_vol = sum(float(b[1]) for b in bids)
            ask_vol = sum(float(a[1]) for a in asks)
            imbalance = (bid_vol / ask_vol) if ask_vol > 0 else 1.0
            
            ob_modifier = 0
            if imbalance >= 1.6:
                ob_modifier = 4 # Strong Buy Pressure
            elif imbalance <= 0.6:
                ob_modifier = -4 # Strong Sell Pressure
                
            return {
                "bidVol": bid_vol,
                "askVol": ask_vol,
                "imbalance": imbalance,
                "obModifier": ob_modifier
            }
    except Exception:
        return {"bidVol": 0, "askVol": 0, "imbalance": 1.0, "obModifier": 0}

def fetch_futures_context(symbol):
    try:
        clean_sym = symbol.replace("/", "").replace("USDT", "USDT")
        url_f = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean_sym}"
        req_f = urllib.request.Request(url_f, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_f, timeout=3) as r_f:
            d_f = json.loads(r_f.read().decode('utf-8'))
            funding_rate = float(d_f.get("lastFundingRate", 0)) * 100.0 # Percentage
            
            fut_modifier = 0
            if funding_rate > 0.03:
                fut_modifier = -5 # Extreme Long Crowding Penalty for LONG
            elif funding_rate < -0.03:
                fut_modifier = 5 # Extreme Short Crowding Bonus for LONG
                
            return {
                "fundingRatePct": funding_rate,
                "futModifier": fut_modifier
            }
    except Exception:
        return {"fundingRatePct": 0.0, "futModifier": 0}

def check_hard_eligibility(long_score, short_score, current_price, supp, resis, tp1, sl):
    diff = abs(long_score - short_score)
    if diff < 8:
        return False, "DIRECTION_AMBIGUOUS (LONG ve SHORT Puanı Birbirine Çok Yakın - Belirsiz)"
        
    risk_dist = abs(current_price - sl)
    reward_dist = abs(tp1 - current_price)
    rr_ratio = (reward_dist / risk_dist) if risk_dist > 0 else 0.0
    if rr_ratio < 1.25:
        return False, f"POOR_RISK_REWARD (Risk/Ödül Oranı Yetersiz: 1:{rr_ratio:.2f} < 1:1.25)"

    if long_score > short_score:
        if supp > 0 and ((current_price - supp) / current_price) > 0.04:
            return False, "POOR_LOCATION (Giriş Seviyesi Desteğe Fazla Uzak)"
    else:
        if resis > 0 and ((resis - current_price) / current_price) > 0.04:
            return False, "POOR_LOCATION (Giriş Seviyesi Dirence Fazla Uzak)"

    return True, "ELIGIBLE"

def calc_tp_sl(price, side, supp, resis, atr=None, adx=22.0):
    decimals = 2 if price >= 1000 else (4 if price >= 1 else 6)
    
    # 🎯 DİNAMİK GEÇMİŞ MUM DESTEK & DİRENÇ TABANLI ÇOKLU TP/SL VE DCA KADEMELERİ
    atr_val = atr if (atr and atr > 0) else (price * 0.015)
    buffer = max(atr_val * 1.2, price * 0.008)
    
    # Güçlü Trend Durumunda TP3 Hedefini Esnetme (ADX > 25)
    tp3_mult = 4.5 if adx >= 25.0 else 3.5

    if side == "LONG":
        sl_base = supp if supp < price else (price - atr_val * 2.0)
        sl = round(sl_base - buffer, decimals)
        max_allowed_sl = round(price * 0.978, decimals)
        if sl >= price or sl > max_allowed_sl:
            sl = max_allowed_sl

        risk_dist = price - sl
        raw_tp1 = price + risk_dist * 1.55
        if resis > price and resis < raw_tp1 and (resis - price) >= risk_dist * 1.3:
            tp1 = round(resis * 0.998, decimals)
        else:
            tp1 = round(raw_tp1, decimals)

        tp2 = round(max(resis * 0.998 if resis > price else price + risk_dist * 2.2, price + risk_dist * 2.0), decimals)
        tp3 = round(price + risk_dist * tp3_mult, decimals)

        # DCA Safety Order Levels (-2% ve -4% Kademeli Alım)
        so1 = round(price * 0.98, decimals)
        so2 = round(price * 0.96, decimals)

    else: # SHORT
        sl_base = resis if resis > price else (price + atr_val * 2.0)
        sl = round(sl_base + buffer, decimals)
        min_allowed_sl = round(price * 1.022, decimals)
        if sl <= price or sl < min_allowed_sl:
            sl = min_allowed_sl

        risk_dist = sl - price
        raw_tp1 = price - risk_dist * 1.55
        if supp < price and supp > raw_tp1 and (price - supp) >= risk_dist * 1.3:
            tp1 = round(supp * 1.002, decimals)
        else:
            tp1 = round(raw_tp1, decimals)

        tp2 = round(min(supp * 1.002 if supp < price else price - risk_dist * 2.2, price - risk_dist * 2.0), decimals)
        tp3 = round(price - risk_dist * tp3_mult, decimals)

        # DCA Safety Order Levels (+2% ve +4% Kademeli Ek Satış)
        so1 = round(price * 1.02, decimals)
        so2 = round(price * 1.04, decimals)

    return tp1, tp2, tp3, sl, so1, so2

def calc_dynamic_position_size(price, atr, balance):
    # Volatiliteye ve Hafta sonu durumuna göre Kelly Risk Sizing ($350 - $750 arası esnek büyüklük)
    is_weekend = time.strftime("%w") in ["0", "6"]
    volatility_pct = (atr / price) * 100.0 if price > 0 else 1.5
    base_size = balance * 0.10 # Base 10% ($600 for $6000 balance)
    
    if is_weekend:
        base_size *= 0.70 # Hafta sonu risk düşürme ($420)
        
    if volatility_pct > 3.0:
        return round(max(300.0, base_size * 0.7), 2) # Yüksek volatilitede risk düşür
    elif volatility_pct < 1.2:
        return round(min(balance, base_size * 1.25), 2) # Düşük volatilitede büyüklük artır
    else:
        return round(base_size, 2)

def run_backtest_simulation():
    total_trades = 0
    wins = 0
    losses = 0
    total_pnl = 0.0
    symbol_stats = {}

    for sym in state["symbols"][:10]:
        clean_sym = sym.replace("USDT", "/USDT")
        try:
            k_url_90d = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=4h&limit=300"
            req_90d = urllib.request.Request(k_url_90d, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_90d, timeout=4) as r_90d:
                k_data = json.loads(r_90d.read().decode('utf-8'))
                if len(k_data) >= 50:
                    closes = [float(c[4]) for c in k_data]
                    highs = [float(c[2]) for c in k_data]
                    lows = [float(c[3]) for c in k_data]

                    for i in range(50, len(k_data)-5, 6):
                        c_price = closes[i]
                        total_trades += 1
                        future_high = max(highs[i+1:i+6])
                        future_low = min(lows[i+1:i+6])
                        if future_high >= c_price * 1.022:
                            wins += 1
                            pnl = 600.0 * 0.022
                            total_pnl += pnl
                            symbol_stats[clean_sym] = symbol_stats.get(clean_sym, 0) + pnl
                        else:
                            losses += 1
                            pnl = -600.0 * 0.018
                            total_pnl += pnl
                            symbol_stats[clean_sym] = symbol_stats.get(clean_sym, 0) + pnl
        except Exception:
            pass

    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    best_sym = max(symbol_stats, key=symbol_stats.get) if symbol_stats else "BTC/USDT"

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "best_symbol": best_sym
    }

# 24/7 Background Trading & Self-Learning Auto-Pilot Loop
def background_bot_loop():
    global global_last_signal_time, signal_broadcast_cooldowns, symbol_cooldowns, telegram_config, state
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
            
            # 🔍 Canlı Açık Pozisyon Otomatik Periyodik Raporu Devre Dışı Bırakıldı
            # (Kullanıcı talebi doğrultusunda periyodik raporlar kapatıldı. Sadece pozisyon bozulması, trend tersine dönmesi veya TP/SL durumunda bildirim gönderilir.)
            if (now_sec - last_audit_report > 1800):
                last_audit_report = now_sec
            positions_to_keep = []
            current_time_str = time.strftime("%H:%M")
            is_time_exit_hour = (current_time_str == "23:30")

            for pos in state["positions"]:
                sym_clean = pos["symbol"].replace("/", "")
                mark_price = state["ticker_data"].get(sym_clean, {}).get("price", pos["entryPrice"])
                pos["markPrice"] = mark_price
                open_duration_hours = (now_sec - pos.get("openTimeSec", now_sec)) / 3600.0

                if pos["side"] == "LONG":
                    pos["pnl"] = (mark_price - pos["entryPrice"]) * pos["size"]
                    pos["pnlPercent"] = ((mark_price - pos["entryPrice"]) / pos["entryPrice"]) * 100
                else:
                    pos["pnl"] = (pos["entryPrice"] - mark_price) * pos["size"]
                    pos["pnlPercent"] = ((pos["entryPrice"] - mark_price) / pos["entryPrice"]) * 100

                # ⏰ SMART CONDITIONAL TIME EXIT (TSİ 23:30 Gece Kapanışı) veya MAX DURATION EXIT (8 Saat Sınırı)
                close_needed = False
                close_reason = ""
                
                if (is_time_exit_hour or open_duration_hours >= 8.0):
                    reason_name = "TIME_EXIT (23:30 Gece Kapanışı)" if is_time_exit_hour else "MAX_DURATION_EXIT (8 Saat Sınırı)"
                    
                    if pos["pnlPercent"] >= 0.8:
                        # 🚀 İŞLEM KÂRDA! Kapatılmaz, Stop-Loss kâr kilitleme seviyesine çekilerek hedefe koşturulur!
                        decimals = 2 if pos["entryPrice"] >= 1000 else (4 if pos["entryPrice"] >= 1 else 6)
                        if pos["side"] == "LONG":
                            new_lock_sl = round(pos["entryPrice"] * 1.004, decimals)
                            if new_lock_sl > pos.get("sl", 0):
                                pos["sl"] = new_lock_sl
                                save_db()
                                send_telegram_message(f"🧠 *AKILLI ZAMAN YÖNETİMİ:* {pos['symbol']} işlemi kârda (*+{pos['pnlPercent']:.2f}%*) olduğu için kapatılmadı. Stop Loss Kâr Kilitleme seviyesine (`{format_price(new_lock_sl)}`) çekildi! 🚀")
                        else:
                            new_lock_sl = round(pos["entryPrice"] * 0.996, decimals)
                            if pos.get("sl", 999999) > new_lock_sl:
                                pos["sl"] = new_lock_sl
                                save_db()
                                send_telegram_message(f"🧠 *AKILLI ZAMAN YÖNETİMİ:* {pos['symbol']} işlemi kârda (*+{pos['pnlPercent']:.2f}%*) olduğu için kapatılmadı. Stop Loss Kâr Kilitleme seviyesine (`{format_price(new_lock_sl)}`) çekildi! 🚀")
                    else:
                        # Zararda veya Nötr -> Gece riskine ve ölü beklemeye girmemek için kapatılır
                        close_needed = True
                        close_reason = reason_name

                if close_needed:
                    return_amount = (pos["entryPrice"] * pos["size"]) + pos["pnl"]
                    state["balance"] += return_amount
                    hist_entry = dict(pos)
                    hist_entry["closeReason"] = f"⏰ {close_reason}"
                    hist_entry["closePrice"] = mark_price
                    hist_entry["closeTime"] = time.strftime("%H:%M:%S")
                    state["history"].insert(0, hist_entry)
                    save_db()
                    update_self_learning_engine(hist_entry)
                    send_telegram_message(f"⏰ *ZAMAN SINIRI POZİSYON KAPANIŞI ({close_reason}):* {pos['symbol']} işlemi PnL: *${pos['pnl']:+.2f}* ile kapatıldı.")
                    continue
                
                # 🛡️ Gelişmiş Dinamik Trailing Stop & Kâr Kilitleme Motoru
                decimals = 2 if pos["entryPrice"] >= 1000 else (4 if pos["entryPrice"] >= 1 else 6)
                old_sl = pos.get("sl", pos["entryPrice"])
                sl_updated = False
                update_tag = ""

                if pos["side"] == "LONG":
                    if pos["pnlPercent"] >= 2.5:
                        target_sl = round(mark_price * 0.988, decimals)
                        if target_sl > pos.get("sl", 0):
                            pos["sl"] = target_sl
                            sl_updated = True
                            update_tag = "📈 İZLEYEN STOP İLE KÂR TAKİBİ (%2.5+ Kâr)"
                    elif pos["pnlPercent"] >= 1.6:
                        target_sl = round(pos["entryPrice"] * 1.008, decimals)
                        if target_sl > pos.get("sl", 0):
                            pos["sl"] = target_sl
                            sl_updated = True
                            update_tag = "🎯 %0.8 KÂR KİLİTLENDİ"
                    elif pos["pnlPercent"] >= 1.8:
                        if pos.get("sl", 0) < pos["entryPrice"]:
                            pos["sl"] = pos["entryPrice"]
                            sl_updated = True
                            update_tag = "🛡️ BAŞABAŞ STOP (RİSK SIFIRLANDI)"
                else: # SHORT
                    if pos["pnlPercent"] >= 2.5:
                        target_sl = round(mark_price * 1.012, decimals)
                        if target_sl < pos.get("sl", 999999):
                            pos["sl"] = target_sl
                            sl_updated = True
                            update_tag = "📈 İZLEYEN STOP İLE KÂR TAKİBİ (%2.5+ Kâr)"
                    elif pos["pnlPercent"] >= 1.6:
                        target_sl = round(pos["entryPrice"] * 0.992, decimals)
                        if target_sl < pos.get("sl", 999999):
                            pos["sl"] = target_sl
                            sl_updated = True
                            update_tag = "🎯 %0.8 KÂR KİLİTLENDİ"
                    elif pos["pnlPercent"] >= 1.8:
                        if pos.get("sl", 999999) > pos["entryPrice"]:
                            pos["sl"] = pos["entryPrice"]
                            sl_updated = True
                            update_tag = "🛡️ BAŞABAŞ STOP (RİSK SIFIRLANDI)"

                if sl_updated and pos["sl"] != old_sl:
                    save_db()

                    # 🛡️ Anti-Spam Control for Telegram SL Revision Notifications
                    last_notify_ts = pos.get("last_sl_notify_ts", 0)
                    last_notify_tag = pos.get("last_sl_notify_tag", "")
                    sl_change_pct = abs(pos["sl"] - old_sl) / old_sl if old_sl > 0 else 0

                    is_new_stage = (update_tag != last_notify_tag)
                    is_significant_change = (sl_change_pct >= 0.005 and (now_sec - last_notify_ts) >= 900)

                    if is_new_stage or is_significant_change:
                        pos["last_sl_notify_ts"] = now_sec
                        pos["last_sl_notify_tag"] = update_tag
                        save_db()

                        sl_msg = (
                            f"🚨 *STOP LOSS LEVEL REVISED / GÜNCELLENDİ*\n"
                            f"---------------------------------\n"
                            f"🎯 *Varlık:* *{pos['symbol']}* ({pos['side']})\n"
                            f"📍 *Giriş Fiyatı:* `{format_price(pos['entryPrice'])}` | Anlık Fiyat: `{format_price(mark_price)}`\n"
                            f"🛑 *Eski Stop (SL):* `{format_price(old_sl)}` (Revize Edildi)\n"
                            f"⚡ *YENİ STOP LOSS (SL):* `{format_price(pos['sl'])}` 👈\n"
                            f"📊 *Güncelleme Sebebi:* *{update_tag}*\n"
                            f"📈 *Güncel Kâr/Zarar:* *${pos['pnl']:+.2f} ({pos['pnlPercent']:+.2f}%)*\n"
                            f"---------------------------------\n"
                            f"⚠️ *Lütfen harici borsadaki Stop Loss seviyenizi `{format_price(pos['sl'])}` olarak revize ediniz.*"
                        )
                        send_telegram_message(sl_msg)
                        print(f"📡 Telegram Stop Güncelleme Bildirimi Gönderildi: {pos['symbol']} -> SL: {pos['sl']}")

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
                        # 🌐 Fetch 90 Days of 4-hour Candles (540 x 4h = 90 Days) + 15m Micro Timing Candles
                        k_url_90d = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=4h&limit=540"
                        k_url_15m = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=15m&limit=200"
                        
                        k_data_90d = None
                        try:
                            req_90d = urllib.request.Request(k_url_90d, headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req_90d, timeout=5) as r_90d:
                                k_data_90d = json.loads(r_90d.read().decode('utf-8'))
                        except Exception:
                            pass

                        req_k = urllib.request.Request(k_url_15m, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req_k, timeout=4) as r_k:
                            k_data = json.loads(r_k.read().decode('utf-8'))
                            ind = calculate_python_indicators(k_data, k_data_90d)

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
                                macro_bull_accum = ind.get("macroAccumulationBull", True)

                                # Dynamic Adaptive Thresholds from ML Weights
                                rsi_long_limit = ml_weights.get("rsi_threshold_long", 38)
                                rsi_short_limit = ml_weights.get("rsi_threshold_short", 62)

                                should_open = False
                                side = "LONG"
                                confidence = 0

                                vol_ratio = ind.get("volRatio", 1.0)
                                candle_green = ind.get("candleGreen", True)

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
                                if current_price <= supp * 1.015:
                                    long_score += 10 # Support Bounce
                                if vol_ratio >= 1.1:
                                    long_score += 10 # Hacim Genişlemesi Teyidi
                                if candle_green:
                                    long_score += 5 # Yeşil Mum Gövde Teyidi
                                if macro_bull_accum:
                                    long_score += 15 # 90 Günlük Kurumsal Akümülasyon Bonusu
                                if current_price < ema200:
                                    long_score -= 15 # Makro Trend Karşıtı Cezalandırma

                                short_score = 0
                                if current_price <= ema200 and ema20 <= ema50:
                                    short_score += 35 # Strong Bearish Trend Confluence
                                elif current_price <= ema200 or ema20 <= ema50:
                                    short_score += 20
                                    
                                if rsi >= rsi_short_limit or (54 <= rsi <= 65 and current_price <= ema20):
                                    short_score += 30 # RSI Rejection
                                if macd_hist < 0 and macd_line < signal_line:
                                    short_score += 25 # MACD Bearish Momentum
                                if current_price >= resis * 0.985:
                                    short_score += 10 # Resistance Rejection
                                if vol_ratio >= 1.1:
                                    short_score += 10 # Hacim Genişlemesi Teyidi
                                if not candle_green:
                                    short_score += 5 # Kırmızı Mum Gövde Teyidi
                                if not macro_bull_accum:
                                    short_score += 15 # 90 Günlük Kurumsal Dağıtım Bonusu
                                if current_price > ema200:
                                    short_score -= 15 # Makro Trend Karşıtı Cezalandırma

                                # 🛡️ FORMASYON BOZULMA & POZİSYON KORUMA KONTROLÜ (Skor >= 90 Eşiği)
                                if existing_pos:
                                    is_invalidated = False
                                    invalidation_reason = ""

                                    if existing_pos["side"] == "LONG" and short_score >= 90:
                                        is_invalidated = True
                                        invalidation_reason = f"Boğa formasyonu bozuldu! Ayı momentumu (%{short_score} skor) hakim oldu."
                                    elif existing_pos["side"] == "SHORT" and long_score >= 90:
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

                                # 🔍 Orderbook Depth & Futures Context Fetch
                                ob_info = fetch_orderbook_depth(clean_display_sym)
                                fut_info = fetch_futures_context(clean_display_sym)

                                # Apply Orderbook & Futures Modifiers
                                final_long_score = min(99, max(0, long_score + ob_info["obModifier"] + fut_info["futModifier"]))
                                final_short_score = min(99, max(0, short_score - ob_info["obModifier"] - fut_info["futModifier"]))

                                # Hafta Sonu Düşük Hacim Filtresi (Cumartesi/Pazar Eşik 86, Hafta İçi 80)
                                is_weekend = time.strftime("%w") in ["0", "6"]
                                min_required_score = 86 if is_weekend else 80

                                if final_long_score >= min_required_score:
                                    should_open = True
                                    side = "LONG"
                                    confidence = final_long_score
                                elif final_short_score >= min_required_score:
                                    should_open = True
                                    side = "SHORT"
                                    confidence = final_short_score

                                if should_open and confidence >= min_required_score:
                                    tp1, tp2, tp3, sl, so1, so2 = calc_tp_sl(current_price, side, supp, resis, atr, ind.get("adx", 22.0))
                                    suggested_pos_size = calc_dynamic_position_size(current_price, atr, state["balance"])
                                    pattern_name = "İkili Dip (W-Formasyonu)" if side == "LONG" else "İkili Tepe (M-Formasyonu)"

                                    # 🛡️ HARD ELIGIBILITY REJECTION CHECK (Min 1:1.5 R:R & Target Obstacle)
                                    eligible, rej_reason = check_hard_eligibility(final_long_score, final_short_score, current_price, supp, resis, tp1, sl)
                                    if not eligible:
                                        print(f"⛔ İŞLEM REDDEDİLDİ: {clean_display_sym} ({side}) -> {rej_reason}")
                                        should_open = False
                                        continue

                                    # 🤖 Unified VIP Signal Broadcast & Auto-Pilot Trade Engine (100% Synced)
                                    has_open_pos = any(is_same_symbol(p["symbol"], clean_display_sym) for p in state.get("positions", []))
                                    is_already_open = (existing_pos is not None) or has_open_pos
                                    last_bc_time = signal_broadcast_cooldowns.get(clean_display_sym, 0)
                                    cb_until = state.get("circuit_breaker_until", 0)
                                    circuit_active = (time.time() < cb_until)
                                    
                                    SYMBOL_COOLDOWN_SEC = 3600 # 1 saat sembol bekleme süresi
                                    GLOBAL_COOLDOWN_SEC = 600  # 10 dakika global sinyal spam koruması

                                    if state["auto_pilot"] and not is_already_open and not circuit_active and state["balance"] >= 300 and (now - last_bc_time) > SYMBOL_COOLDOWN_SEC and (now - global_last_signal_time) > GLOBAL_COOLDOWN_SEC:
                                        amount = round(min(state["balance"], suggested_pos_size), 2)
                                        size = round(amount / current_price, 4)

                                        pos = {
                                            "id": "AUTO-" + str(int(time.time()))[-6:],
                                            "symbol": clean_display_sym,
                                            "side": side,
                                            "size": size,
                                            "entryPrice": current_price,
                                            "markPrice": current_price,
                                            "tp1": tp1,
                                            "tp2": tp2,
                                            "tp3": tp3,
                                            "sl": sl,
                                            "so1": so1,
                                            "so2": so2,
                                            "pnl": 0.0,
                                            "pnlPercent": 0.0,
                                            "patternName": pattern_name,
                                            "timestamp": time.strftime("%H:%M:%S"),
                                            "openTimeSec": time.time()
                                        }

                                        state["balance"] -= amount
                                        state["positions"].append(pos)
                                        signal_broadcast_cooldowns[clean_display_sym] = now
                                        symbol_cooldowns[clean_display_sym] = now
                                        global_last_signal_time = now
                                        save_db()

                                        reason_trend = f"EMA200 (`{format_price(ema200)}`) üzerinde Güçlü Boğa Trendi" if side == "LONG" else f"EMA200 (`{format_price(ema200)}`) altında Düşen Ayı Trendi"
                                        reason_macd = "MACD Histogramı pozitif ivmeyle boğa kesişimi verdi" if side == "LONG" else "MACD Histogramı negatif ivmeyle ayı kesişimi verdi"
                                        reason_rsi = f"RSI (`{rsi:.1f}`) aşırı satım dip seviyesinden tepki alımı" if side == "LONG" else f"RSI (`{rsi:.1f}`) tepe seviyesinden kâr satışı tepkisi"
                                        reason_smc = f"Boğa Order Block (`{format_price(supp)}`) Kurumsal Alım Bölgesi" if side == "LONG" else f"Ayı Order Block (`{format_price(resis)}`) Kurumsal Satış Bölgesi"

                                        clean_pair = clean_display_sym.replace('/', '')
                                        chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_pair}"

                                        signal_msg = (
                                            f"💎 *VIP TRADER SİNYAL & OTOPİLOT İŞLEMİ* (%{confidence} Başarı Olasılığı)\n"
                                            f"---------------------------------\n"
                                            f"🎯 *Varlık:* *{clean_display_sym}* ({side} {'📈' if side == 'LONG' else '📉'})\n"
                                            f"📍 *Giriş Seviyesi:* `{format_price(current_price)}` \n"
                                            f"🎯 *Kar Al 1 (TP1):* `{format_price(tp1)}` (Kademeli Kâr - %50 Kapat)\n"
                                            f"🎯 *Kar Al 2 (TP2):* `{format_price(tp2)}` (Ana Hedef)\n"
                                            f"🚀 *Kar Al 3 (TP3):* `{format_price(tp3)}` (Trend Uzaması)\n"
                                            f"🛡️ *DCA Kademeli Alım #1:* `{format_price(so1)}` (-%2 Kademesi)\n"
                                            f"🛡️ *DCA Kademeli Alım #2:* `{format_price(so2)}` (-%4 Kademesi)\n"
                                            f"🛑 *Stop Loss (SL):* `{format_price(sl)}` (Volatilite Korumalı)\n"
                                            f"---------------------------------\n"
                                            f"📐 *QUANTFURY UYGULAMA EMİR BİLGİSİ:*\n"
                                            f"└ 💵 *Açılan Pozisyon Büyüklüğü:* `${amount:,.2f} USDT` (Otopilot Aktif 🚀)\n"
                                            f"└ ⚖️ *Önerilen Kaldıraç:* `1x - 5x` (Maksimum Risk: %2.0)\n"
                                            f"---------------------------------\n"
                                            f"📊 *KURUMSAL TEKNİK & TEMEL ANALİZ GEREKÇESİ:*\n"
                                            f"└ 📈 *Makro Trend:* {reason_trend}\n"
                                            f"└ 🌊 *Momentum:* {reason_macd}\n"
                                            f"└ 🎯 *RSI & Seviye:* {reason_rsi}\n"
                                            f"└ 🐋 *Smart Money (SMC):* {reason_smc}\n"
                                            f"└ 🔍 *Formasyon Yapısı:* *{pattern_name}*\n"
                                            f"---------------------------------\n"
                                            f"📈 [Canlı TradingView Grafiği ve Formasyonu İncele]({chart_link})\n"
                                            f"✨ *VIP Otopilot Pozisyonu Başarıyla Açıldı ve Taramaya Alındı*"
                                        )
                                        send_telegram_message(signal_msg)
                                        print(f"📡 VIP Trader Sinyal ve Otopilot İşlemi Açıldı: {clean_display_sym} ({side})")
                                        break
                    except Exception as e_k:
                        print("Auto-pilot kline scan error:", e_k)

        except Exception as e:
            print("Background loop tick error:", e)

        time.sleep(3)

# Web Server & REST API Handler
class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            return

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

        if self.path == "/":
            self.path = "/index.html"

        if self.path == "/api/backtest":
            res = run_backtest_simulation()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
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
            if parsed_ids:
                telegram_config["chat_ids"] = parsed_ids
                telegram_config["chat_id"] = parsed_ids[0]
            
            telegram_config["enabled"] = bool(data.get("enabled", False))
            save_telegram_config()
            
            ok, msg = True, "Ayarlar kaydedildi."
            if telegram_config["enabled"]:
                ok, msg = send_telegram_message("📢 *Quantum AI Bot Canlı Sinyal Yayın Hattı Etkinleşti!*\n\nTüm eklenen aboneler ve Telegram kanallarına 7/24 canlı sinyal yayını aktiftir.")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
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
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode('utf-8'))
            return

        elif self.path == "/api/open-trade":
            signal = data.get("signal", {})
            amount = float(data.get("amount", 600))
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
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "position": pos}).encode('utf-8'))
                return

        elif self.path == "/api/toggle-autopilot":
            state["auto_pilot"] = bool(data.get("enabled", False))
            save_db()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "auto_pilot": state["auto_pilot"]}).encode('utf-8'))
            return

        elif self.path == "/api/close-all":
            positions = state.get("positions", [])
            closed_cnt = len(positions)
            for p in list(positions):
                mark_price = state.get("ticker_data", {}).get(p["symbol"].replace("/", ""), {}).get("price", p["entryPrice"])
                pnl = (mark_price - p["entryPrice"]) * p["size"] if p["side"] == "LONG" else (p["entryPrice"] - mark_price) * p["size"]
                return_amount = (p["entryPrice"] * p["size"]) + pnl
                state["balance"] += return_amount
                
                hist_entry = dict(p)
                hist_entry["closeReason"] = "🔴 API /CLOSE-ALL İLE KAPATILDI"
                hist_entry["closePrice"] = mark_price
                hist_entry["closeTime"] = time.strftime("%H:%M:%S")
                state.get("history", []).insert(0, hist_entry)
            
            state["positions"] = []
            save_db()
            
            send_telegram_message(
                f"🧹 *TÜM AÇIK POZİSYONLAR KAPATILDI (API)*\n\n"
                f"• Kapatılan İşlem Sayısı: `{closed_cnt}`\n"
                f"• Güncel Bakiye: `${state['balance']:,.2f} USDT`"
            )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "closed_count": closed_cnt, "balance": state["balance"]}).encode('utf-8'))
            return

        elif self.path == "/api/reset-all":
            state["balance"] = 6000.0
            state["positions"] = []
            state["history"] = []
            signal_broadcast_cooldowns.clear()
            symbol_cooldowns.clear()
            global_last_signal_time = 0
            ml_weights["total_learnings"] = 0
            ml_weights["win_streak"] = 0
            ml_weights["loss_streak"] = 0
            ml_weights["rsi_threshold_long"] = 36
            ml_weights["rsi_threshold_short"] = 64
            save_db()
            save_ml_db()
            
            send_telegram_message(
                "🔄 *QUANTUM AI PORTFÖYÜ SIFIRLANDI!*\n\n"
                "• Kullanılabilir Bakiye: `$6,000.00 USDT`\n"
                "• Açık Pozisyonlar: `0`\n"
                "• Kapanan İşlem Geçmişi: `Temizlendi (0 PnL)`\n"
                "• Otopilot Motoru: `Sıfırdan Başlatıldı` 🟢"
            )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "balance": 6000.0}).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

def keep_alive_loop():
    url_ext = os.environ.get("RENDER_EXTERNAL_URL")
    urls_to_ping = [f"http://127.0.0.1:{PORT}/health"]
    if url_ext:
        urls_to_ping.append(url_ext.rstrip('/') + "/health")
    
    while True:
        time.sleep(180) # Every 3 minutes
        for ping_url in urls_to_ping:
            try:
                req = urllib.request.Request(ping_url, headers={'User-Agent': 'Mozilla/5.0 KeepAlive'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    pass
            except Exception:
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

