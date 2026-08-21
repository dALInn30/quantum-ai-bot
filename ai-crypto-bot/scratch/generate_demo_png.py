import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

print("Generating live BTCUSDT candlestick chart...")
clean_sym, klines = server.fetch_klines_for_symbol("BTCUSDT", interval="15m", limit=50)

curr_p = float(klines[-1][4]) if klines else 64000.0
ind = server.calculate_python_indicators(klines) if klines else {'support': curr_p*0.98, 'resistance': curr_p*1.02}
sig = {'entryPrice': curr_p, 'sl': round(curr_p*0.98, 2), 'tp1': round(curr_p*1.02, 2), 'tp2': round(curr_p*1.04, 2)}
btc_ctx = server.analyze_btc_market_context()

photo_bytes = server.generate_analysis_chart_image(clean_sym, klines, ind, sig, btc_context=btc_ctx)

output_dir = r"C:\Users\User\.gemini\antigravity-ide\brain\60fd094a-e6ff-40b1-843b-d8e79aaf0f40"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "test_chart.png")

if photo_bytes:
    with open(output_path, "wb") as f:
        f.write(photo_bytes)
    print(f"✅ Success! HD Chart image saved to {output_path} ({len(photo_bytes)} bytes)")
    
    # Try sending to Telegram if token exists
    if server.telegram_config.get("bot_token"):
        ok, msg = server.send_telegram_photo(photo_bytes, caption=f"📷 Test Grafiği: {clean_sym}")
        print("Telegram Send Status:", ok, msg)
    else:
        print("Telegram Bot Token is empty in telegram_config.json (User enters token via UI).")
else:
    print("❌ Failed to generate chart bytes.")
