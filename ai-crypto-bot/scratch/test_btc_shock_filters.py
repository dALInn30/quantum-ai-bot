import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
import precision_engine

print("--- TESTING BTC SHOCK FILTER RELAXATION ---")

# 1. Test Live BTC Market Context
btc_ctx = server.analyze_btc_market_context()
print("Live BTC Market Context:", btc_ctx)

# 2. Test Filters with Mock Contexts
dummy_setup_long = {"setup_type": "TREND_PULLBACK", "side": "LONG"}
dummy_setup_short = {"setup_type": "TREND_PULLBACK", "side": "SHORT"}

dummy_score = {
    "final_score": 85,
    "htf_alignment": 15,
    "market_structure": 10,
    "entry_location": 10,
    "volume_momentum": 5,
    "target_clearance": 7,
    "futures_modifier": 1,
    "orderbook_modifier": 1
}

dummy_ind_long = {
    "currentPrice": 100.0,
    "atr": 1.0,
    "support": 99.5,
    "resistance": 108.0
}

dummy_ind_short = {
    "currentPrice": 100.0,
    "atr": 1.0,
    "support": 92.0,
    "resistance": 100.5
}

dummy_klines = [[0, 100, 101, 99, 100, 1000] for _ in range(30)]

# Scenario A: Stable Market
ctx_stable = {"status": "STABLE_MARKET", "allow_long": True, "allow_short": True}
long_ok, long_reason = precision_engine.evaluate_precision_filters(dummy_setup_long, dummy_score, dummy_ind_long, dummy_klines, dummy_klines, btc_context=ctx_stable)
short_ok, short_reason = precision_engine.evaluate_precision_filters(dummy_setup_short, dummy_score, dummy_ind_short, dummy_klines, dummy_klines, btc_context=ctx_stable)
print(f"STABLE MARKET -> LONG: {long_ok} ({long_reason}) | SHORT: {short_ok} ({short_reason})")

# Scenario B: Sudden Dump Shock
ctx_dump = {"status": "SUDDEN_DUMP_HAZARD", "allow_long": False, "allow_short": True}
long_ok_dump, long_reason_dump = precision_engine.evaluate_precision_filters(dummy_setup_long, dummy_score, dummy_ind_long, dummy_klines, dummy_klines, btc_context=ctx_dump)
short_ok_dump, short_reason_dump = precision_engine.evaluate_precision_filters(dummy_setup_short, dummy_score, dummy_ind_short, dummy_klines, dummy_klines, btc_context=ctx_dump)
print(f"SUDDEN DUMP SHOCK -> LONG: {long_ok_dump} ({long_reason_dump}) | SHORT: {short_ok_dump} ({short_reason_dump})")

# Scenario C: Sudden Pump Shock
ctx_pump = {"status": "SUDDEN_PUMP_HAZARD", "allow_long": True, "allow_short": False}
long_ok_pump, long_reason_pump = precision_engine.evaluate_precision_filters(dummy_setup_long, dummy_score, dummy_ind_long, dummy_klines, dummy_klines, btc_context=ctx_pump)
short_ok_pump, short_reason_pump = precision_engine.evaluate_precision_filters(dummy_setup_short, dummy_score, dummy_ind_short, dummy_klines, dummy_klines, btc_context=ctx_pump)
print(f"SUDDEN PUMP SHOCK -> LONG: {long_ok_pump} ({long_reason_pump}) | SHORT: {short_ok_pump} ({short_reason_pump})")

print("\n--- ALL TESTS COMPLETED SUCCESSFULLY ---")
