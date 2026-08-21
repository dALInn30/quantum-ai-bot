import json
import urllib.request
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

def send_demo_signal():
    server.load_db()
    
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

    _, klines = server.fetch_klines_for_symbol("BTCUSDT", interval="15m", limit=50)
    ind = {'support': 63810.0, 'resistance': 65420.0, 'patterns': {'name': 'İkili Dip (W-Formasyonu)'}}
    sig = {'entryPrice': 64250.0, 'sl': 63810.0, 'tp1': 65420.0, 'tp2': 66100.0}

    photo = server.generate_analysis_chart_image("BTCUSDT", klines, ind, sig)

    if photo:
        ok, msg = server.send_telegram_photo(photo, caption=signal_msg)
    else:
        ok, msg = server.send_telegram_message(signal_msg)

    if ok:
        print("✅ DEMO SİNYAL VE CANLI GERÇEK MUM GRAFİĞİ TELEGRAM'A BAŞARIYLA GÖNDERİLDİ!")
    else:
        print("❌ Sinyal Gönderim Hatası:", msg)

if __name__ == "__main__":
    send_demo_signal()
