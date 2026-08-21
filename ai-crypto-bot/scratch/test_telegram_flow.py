import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

print("HAS_MATPLOTLIB:", server.HAS_MATPLOTLIB)

clean_sym, klines_raw = server.fetch_klines_for_symbol("BTCUSDT", interval="15m", limit=50)
print(f"fetch_klines_for_symbol result: clean_sym={clean_sym}, klines_raw type={type(klines_raw)}, len={len(klines_raw) if klines_raw else 0}")

ind = server.calculate_python_indicators(klines_raw) if klines_raw else None
print("Indicators calculated:", bool(ind))

curr_p = float(klines_raw[-1][4]) if klines_raw else 50000.0
sig = {
    'entryPrice': curr_p,
    'sl': round(curr_p * 0.978, 2),
    'tp1': round(curr_p * 1.022, 2),
    'tp2': round(curr_p * 1.045, 2)
}
btc_ctx = server.analyze_btc_market_context()

try:
    photo = server.generate_analysis_chart_image(clean_sym, klines_raw, ind, sig, None, btc_context=btc_ctx)
    print("generate_analysis_chart_image result:", len(photo) if photo else "None")
except Exception as e:
    print("Error in generate_analysis_chart_image:")
    traceback.print_exc()
