import json
import urllib.request
import sys

sys.stdout.reconfigure(encoding='utf-8')

TELEGRAM_CFG = r"c:\Users\User\.gemini\antigravity-ide\scratch\ai-crypto-bot\telegram_config.json"

def send_demo_signal():
    try:
        with open(TELEGRAM_CFG, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        token = cfg.get("bot_token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()

        if not token or not chat_id:
            print("❌ Telegram Bot Token veya Chat ID eksik.")
            return

        signal_msg = (
            "💎 *VIP TRADER ÖZEL YZ SİNYALİ & YAPISAL ANALİZ* (%94 Başarı Olasılığı)\n"
            "---------------------------------\n"
            "🎯 *Varlık:* *BTC/USDT* (LONG 📈)\n"
            "📍 *Giriş Seviyesi:* `$64,250.00`\n"
            "🎯 *Kar Al (TP1):* `$65,420.00` (Teknik Direnç Öncesi)\n"
            "🎯 *Kar Al (TP2):* `$66,100.00` (Fibo 1.8 Genişlemesi)\n"
            "🛑 *Stop Loss (SL):* `$63,810.00` (Boğa Order Block Tamponlu)\n"
            "---------------------------------\n"
            "📊 *KURUMSAL TEKNİK & TEMEL ANALİZ GEREKÇESİ:*\n"
            "└ 📈 *Makro Trend:* EMA200 (`$64,100.00`) üzerinde Güçlü Yükselen Boğa Trendi\n"
            "└ 🌊 *Momentum:* MACD Histogramı pozitif ivmeyle boğa kesişimi verdi\n"
            "└ 🎯 *RSI & Seviye:* RSI (`36.4`) aşırı satım dip bölgesinden tepki alımı\n"
            "└ 🐋 *Smart Money (SMC):* Boğa Order Block (`$63,900.00`) Kurumsal Alım Bölgesi\n"
            "└ 🔍 *Formasyon Yapısı:* *İkili Dip (W-Formasyonu)*\n"
            "---------------------------------\n"
            "🛡️ *Risk Yönetimi:* %0.5 Kar görünce Başabaş Stop (Risk 0) aktifleşecektir.\n"
            "📈 [TradingView Canlı Grafik İncele](https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT)\n"
            "✨ *Quantum AI VIP Canlı Sinyal Yayın Hattı*"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": signal_msg,
            "parse_mode": "Markdown"
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("ok"):
                print("✅ SANAL İŞLEM BİLDİRİMİ TELEGRAM'A BAŞARIYLA GÖNDERİLDİ!")
            else:
                print("⚠️ Telegram Yanıtı:", data)

    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("❌ TELEGRAM HATASI (401 Unauthorized): Bot Token'ınız geçersiz veya henüz aktif edilmemiş.")
            print("Lütfen Telegram'da @BotFather'dan aldığınız geçerli Bot Token'ı kaydedin.")
        else:
            print(f"❌ Telegram HTTP Hatası ({e.code}):", e.reason)
    except Exception as e:
        print("❌ Hata:", e)

if __name__ == "__main__":
    send_demo_signal()
