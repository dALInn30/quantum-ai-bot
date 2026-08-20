import math
import time

"""
PRECISION INTRADAY BOT ENGINE
Implements strict setup detection, 7-part quality scoring, dampened futures/orderbook modifiers,
advanced execution filters, effective RR calculation, and evidence confluence verification.
"""

# Config Parameters
PRECISION_MODE = True
ENABLE_TREND_PULLBACK = True
ENABLE_BREAKOUT_RETEST = True
ENABLE_LIQUIDITY_SWEEP_REVERSAL = True

MIN_SCORE_NORMAL = 82
MIN_SCORE_DOUBLE_RANGE = 88
MIN_SCORE_COUNTER_TREND = 90
MIN_DIRECTION_DIFF = 12
MIN_EFFECTIVE_RR = 1.7
MIN_INDEPENDENT_CONFLUENCES = 4


def calculate_ema_series(values, period):
    if len(values) < period:
        return [values[-1]] * len(values)
    k = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for val in values[period:]:
        ema.append(val * k + ema[-1] * (1 - k))
    return ema


def detect_market_regime(k_data_4h, k_data_15m):
    if not k_data_15m or len(k_data_15m) < 30:
        return {"htf": "UNKNOWN", "ltf": "UNKNOWN", "double_range": False}

    closes_15m = [float(c[4]) for c in k_data_15m]
    ema20_15m = calculate_ema_series(closes_15m, 20)[-1]
    ema50_15m = calculate_ema_series(closes_15m, 50)[-1]
    ema200_15m = calculate_ema_series(closes_15m, 200)[-1] if len(closes_15m) >= 200 else ema50_15m

    c_price = closes_15m[-1]

    if c_price >= ema200_15m and ema20_15m >= ema50_15m:
        ltf_regime = "BULLISH"
    elif c_price <= ema200_15m and ema20_15m <= ema50_15m:
        ltf_regime = "BEARISH"
    else:
        ltf_regime = "RANGE_BOUND"

    htf_regime = "RANGE_BOUND"
    if k_data_4h and len(k_data_4h) >= 30:
        closes_4h = [float(c[4]) for c in k_data_4h]
        ema20_4h = calculate_ema_series(closes_4h, 20)[-1]
        ema50_4h = calculate_ema_series(closes_4h, 50)[-1]
        c_4h = closes_4h[-1]

        if c_4h >= ema50_4h and ema20_4h >= ema50_4h:
            htf_regime = "STRONG_BULL" if c_4h >= ema20_4h else "BULLISH"
        elif c_4h <= ema50_4h and ema20_4h <= ema50_4h:
            htf_regime = "STRONG_BEAR" if c_4h <= ema20_4h else "BEARISH"

    double_range = (htf_regime == "RANGE_BOUND" and ltf_regime == "RANGE_BOUND")

    return {
        "htf": htf_regime,
        "ltf": ltf_regime,
        "double_range": double_range
    }


def detect_precision_setup(symbol, k_data_15m, k_data_4h, indicators, btc_context):
    if not k_data_15m or not indicators:
        return {"setup_type": "NONE", "side": "NONE", "reason": "NO_DATA"}

    regime_info = detect_market_regime(k_data_4h, k_data_15m)
    htf_regime = regime_info["htf"]
    double_range = regime_info["double_range"]

    c_price = indicators["currentPrice"]
    rsi = indicators["rsi"]
    ema20 = indicators["ema20"]
    ema50 = indicators["ema50"]
    ema200 = indicators["ema200"]
    supp = indicators["support"]
    resis = indicators["resistance"]
    vol_ratio = indicators.get("volRatio", 1.0)
    candle_green = indicators.get("candleGreen", True)

    closes = [float(c[4]) for c in k_data_15m]
    highs = [float(c[2]) for c in k_data_15m]
    lows = [float(c[3]) for c in k_data_15m]

    # --- 1. SETUP A: TREND_PULLBACK ---
    if ENABLE_TREND_PULLBACK and not double_range:
        # LONG TREND_PULLBACK
        if htf_regime in ["BULLISH", "STRONG_BULL"] and c_price >= ema200 * 0.995:
            pulled_back = (c_price <= supp * 1.025 or c_price <= ema20 * 1.012 or c_price <= ema50 * 1.012)
            not_chasing = (rsi <= 68)
            vol_alive = (vol_ratio >= 0.75)
            tp1_clear = ((resis - c_price) / c_price >= 0.008)

            if pulled_back and not_chasing and vol_alive and tp1_clear and candle_green:
                return {
                    "setup_type": "TREND_PULLBACK",
                    "side": "LONG",
                    "reason": "4H Bullish trend + 15M pullback to support zone with green confirmation candle"
                }

        # SHORT TREND_PULLBACK
        if htf_regime in ["BEARISH", "STRONG_BEAR"] and c_price <= ema200 * 1.005:
            pulled_back = (c_price >= resis * 0.975 or c_price >= ema20 * 0.988 or c_price >= ema50 * 0.988)
            not_chasing = (rsi >= 32)
            vol_alive = (vol_ratio >= 0.75)
            tp1_clear = ((c_price - supp) / c_price >= 0.008)

            if pulled_back and not_chasing and vol_alive and tp1_clear and not candle_green:
                return {
                    "setup_type": "TREND_PULLBACK",
                    "side": "SHORT",
                    "reason": "4H Bearish trend + 15M pullback to resistance zone with red confirmation candle"
                }

    # --- 2. SETUP B: BREAKOUT_RETEST ---
    if ENABLE_BREAKOUT_RETEST:
        recent_closes = closes[-6:-1]
        # LONG BREAKOUT_RETEST
        broke_above = any(c > resis * 0.995 for c in recent_closes)
        retested_supp = (c_price <= resis * 1.010 and c_price >= resis * 0.988)
        vol_confirmed = (vol_ratio >= 1.15)

        if broke_above and retested_supp and vol_confirmed and candle_green:
            return {
                "setup_type": "BREAKOUT_RETEST",
                "side": "LONG",
                "reason": "Confirmed 15M candle close above resistance + high volume breakout + retest"
            }

        # SHORT BREAKOUT_RETEST
        broke_below = any(c < supp * 1.005 for c in recent_closes)
        retested_resis = (c_price >= supp * 0.990 and c_price <= supp * 1.012)

        if broke_below and retested_resis and vol_confirmed and not candle_green:
            return {
                "setup_type": "BREAKOUT_RETEST",
                "side": "SHORT",
                "reason": "Confirmed 15M candle close below support + high volume breakdown + retest"
            }

    # --- 3. SETUP C: LIQUIDITY_SWEEP_REVERSAL ---
    if ENABLE_LIQUIDITY_SWEEP_REVERSAL:
        swept_below = (min(lows[-4:]) < supp * 0.997)
        closed_above = (c_price >= supp * 0.998)
        tp1_clear = ((resis - c_price) / c_price >= 0.008)

        if swept_below and closed_above and tp1_clear and candle_green:
            return {
                "setup_type": "LIQUIDITY_SWEEP_REVERSAL",
                "side": "LONG",
                "reason": "Support liquidity sweep wick below zone + candle close inside zone"
            }

        swept_above = (max(highs[-4:]) > resis * 1.003)
        closed_below = (c_price <= resis * 1.002)
        tp1_clear = ((c_price - supp) / c_price >= 0.008)

        if swept_above and closed_below and tp1_clear and not candle_green:
            return {
                "setup_type": "LIQUIDITY_SWEEP_REVERSAL",
                "side": "SHORT",
                "reason": "Resistance liquidity sweep wick above zone + candle close inside zone"
            }

    if double_range:
        return {"setup_type": "NONE", "side": "NONE", "reason": "RANGE_NO_EDGE"}

    return {"setup_type": "NONE", "side": "NONE", "reason": "NO_VALID_SETUP"}


def calculate_precision_quality_score(setup_info, indicators, k_data_15m, k_data_4h, fut_info, ob_info):
    setup_type = setup_info.get("setup_type", "NONE")
    side = setup_info.get("side", "NONE")

    if setup_type == "NONE" or side == "NONE":
        return 0, {}

    c_price = indicators["currentPrice"]
    rsi = indicators["rsi"]
    ema20 = indicators["ema20"]
    ema50 = indicators["ema50"]
    ema200 = indicators["ema200"]
    macd_hist = indicators["macdHist"]
    macd_line = indicators["macdLine"]
    signal_line = indicators["signalLine"]
    supp = indicators["support"]
    resis = indicators["resistance"]
    vol_ratio = indicators.get("volRatio", 1.0)
    candle_green = indicators.get("candleGreen", True)

    regime_info = detect_market_regime(k_data_4h, k_data_15m)
    htf_regime = regime_info["htf"]

    # 1. SETUP QUALITY (25 pts)
    setup_q = 0
    if setup_type == "TREND_PULLBACK":
        setup_q = 25
    elif setup_type == "BREAKOUT_RETEST":
        setup_q = 22 if vol_ratio >= 1.25 else 18
    elif setup_type == "LIQUIDITY_SWEEP_REVERSAL":
        setup_q = 20

    # 2. HTF ALIGNMENT (20 pts)
    htf_align = 0
    if side == "LONG":
        if htf_regime == "STRONG_BULL":
            htf_align = 20
        elif htf_regime == "BULLISH":
            htf_align = 15
        elif htf_regime == "RANGE_BOUND":
            htf_align = 10
        else:
            htf_align = 2
    else:
        if htf_regime == "STRONG_BEAR":
            htf_align = 20
        elif htf_regime == "BEARISH":
            htf_align = 15
        elif htf_regime == "RANGE_BOUND":
            htf_align = 10
        else:
            htf_align = 2

    # 3. MARKET STRUCTURE (15 pts)
    mkt_struct = 0
    if side == "LONG":
        if c_price >= ema200 and ema20 >= ema50:
            mkt_struct = 15
        elif c_price >= ema200:
            mkt_struct = 10
        elif ema20 >= ema50:
            mkt_struct = 7
    else:
        if c_price <= ema200 and ema20 <= ema50:
            mkt_struct = 15
        elif c_price <= ema200:
            mkt_struct = 10
        elif ema20 <= ema50:
            mkt_struct = 7

    # 4. ENTRY LOCATION (15 pts)
    entry_loc = 0
    if side == "LONG":
        dist_from_supp = (c_price - supp) / c_price
        if dist_from_supp <= 0.010:
            entry_loc = 15
        elif dist_from_supp <= 0.020:
            entry_loc = 10
        else:
            entry_loc = 5
    else:
        dist_from_resis = (resis - c_price) / c_price
        if dist_from_resis <= 0.010:
            entry_loc = 15
        elif dist_from_resis <= 0.020:
            entry_loc = 10
        else:
            entry_loc = 5

    # 5. VOLUME / MOMENTUM (10 pts)
    vol_mom = 0
    if side == "LONG":
        if macd_hist > 0 and macd_line > signal_line:
            vol_mom += 5
        if vol_ratio >= 1.05:
            vol_mom += 3
        if candle_green:
            vol_mom += 2
    else:
        if macd_hist < 0 and macd_line < signal_line:
            vol_mom += 5
        if vol_ratio >= 1.05:
            vol_mom += 3
        if not candle_green:
            vol_mom += 2

    # 6. TARGET CLEARANCE (10 pts)
    target_clear = 0
    if side == "LONG":
        dist_to_tp1 = (resis - c_price) / c_price
        if dist_to_tp1 >= 0.020:
            target_clear = 10
        elif dist_to_tp1 >= 0.010:
            target_clear = 7
        else:
            target_clear = 2
    else:
        dist_to_tp1 = (c_price - supp) / c_price
        if dist_to_tp1 >= 0.020:
            target_clear = 10
        elif dist_to_tp1 >= 0.010:
            target_clear = 7
        else:
            target_clear = 2

    # 7. EXECUTION QUALITY (5 pts)
    exec_q = 5

    raw_score = setup_q + htf_align + mkt_struct + entry_loc + vol_mom + target_clear + exec_q

    # DAMPENED MODIFIERS
    fut_confidence = fut_info.get("confidence", "LOW")
    oi_low = fut_info.get("oi_activity_low", True)
    raw_fut_mod = fut_info.get("futModifier", 0)

    if fut_confidence == "HIGH":
        fut_mod = max(-5, min(5, raw_fut_mod))
    elif oi_low:
        fut_mod = max(-1, min(1, raw_fut_mod))
    else:
        fut_mod = max(-2, min(2, raw_fut_mod))

    ob_confidence = ob_info.get("confidence", "LOW")
    raw_ob_mod = ob_info.get("obModifier", 0)

    if ob_confidence == "HIGH":
        ob_mod = max(-2, min(2, raw_ob_mod))
    elif ob_confidence == "MEDIUM":
        ob_mod = max(-1, min(1, raw_ob_mod))
    else:
        ob_mod = 0

    final_score = min(99, max(0, int(raw_score + fut_mod + ob_mod)))

    score_components = {
        "setup_quality": setup_q,
        "htf_alignment": htf_align,
        "market_structure": mkt_struct,
        "entry_location": entry_loc,
        "volume_momentum": vol_mom,
        "target_clearance": target_clear,
        "execution_quality": exec_q,
        "raw_score": raw_score,
        "futures_modifier": fut_mod,
        "orderbook_modifier": ob_mod,
        "final_score": final_score
    }

    return final_score, score_components


def evaluate_precision_filters(setup_info, score_components, indicators, k_data_15m, k_data_4h):
    setup_type = setup_info.get("setup_type", "NONE")
    side = setup_info.get("side", "NONE")
    final_score = score_components.get("final_score", 0)

    if setup_type == "NONE" or side == "NONE":
        return False, "NO_VALID_SETUP"

    c_price = indicators["currentPrice"]
    atr = indicators["atr"]
    supp = indicators["support"]
    resis = indicators["resistance"]

    regime_info = detect_market_regime(k_data_4h, k_data_15m)
    htf_regime = regime_info["htf"]
    double_range = regime_info["double_range"]

    # 1. ENTRY EXTENDED FILTER
    if setup_type == "TREND_PULLBACK":
        if side == "LONG":
            dist_from_supp = (c_price - supp)
            if dist_from_supp > 1.5 * atr:
                return False, "ENTRY_EXTENDED"
        elif side == "SHORT":
            dist_from_resis = (resis - c_price)
            if dist_from_resis > 1.5 * atr:
                return False, "ENTRY_EXTENDED"

    # 2. CANDLE EXTENSION FILTER
    if k_data_15m and len(k_data_15m) >= 2:
        last_c = k_data_15m[-1]
        c_open = float(last_c[1])
        c_close = float(last_c[4])
        body = abs(c_close - c_open)
        if body > 1.8 * atr and setup_type != "BREAKOUT_RETEST":
            return False, "EXTENDED_ENTRY"

    # 3. TARGET BLOCKED FILTER
    if side == "LONG":
        dist_to_resis = (resis - c_price)
        if dist_to_resis < 0.6 * atr:
            return False, "TARGET_BLOCKED"
    else:
        dist_to_supp = (c_price - supp)
        if dist_to_supp < 0.6 * atr:
            return False, "TARGET_BLOCKED"

    # 4. EFFECTIVE RR FILTER
    tp1 = resis if side == "LONG" else supp
    sl = supp * 0.985 if side == "LONG" else resis * 1.015
    risk_amt = abs(c_price - sl)
    reward_amt = abs(tp1 - c_price)

    fee_slippage = c_price * 0.0012
    effective_reward = max(0, reward_amt - fee_slippage)
    effective_risk = risk_amt + fee_slippage

    effective_rr = (effective_reward / effective_risk) if effective_risk > 0 else 0
    if effective_rr < MIN_EFFECTIVE_RR:
        return False, "INSUFFICIENT_EFFECTIVE_RR"

    # 5. PRECISION SCORE THRESHOLD
    is_counter_trend = (side == "LONG" and htf_regime in ["BEARISH", "STRONG_BEAR"]) or \
                       (side == "SHORT" and htf_regime in ["BULLISH", "STRONG_BULL"])

    required_score = MIN_SCORE_COUNTER_TREND if is_counter_trend else (MIN_SCORE_DOUBLE_RANGE if double_range else MIN_SCORE_NORMAL)

    if final_score < required_score:
        return False, "PRECISION_SCORE_TOO_LOW"

    # 6. MINIMUM CONFLUENCE COUNT
    confluence_families = set()
    if score_components.get("htf_alignment", 0) >= 15:
        confluence_families.add("TREND")
    if score_components.get("market_structure", 0) >= 10:
        confluence_families.add("STRUCTURE")
    if score_components.get("entry_location", 0) >= 10:
        confluence_families.add("LOCATION")
    if score_components.get("volume_momentum", 0) >= 5:
        confluence_families.add("MOMENTUM")
    if score_components.get("target_clearance", 0) >= 7:
        confluence_families.add("LOCATION_CLEARANCE")
    if score_components.get("futures_modifier", 0) > 0:
        confluence_families.add("DERIVATIVES")
    if score_components.get("orderbook_modifier", 0) > 0:
        confluence_families.add("MICROSTRUCTURE")
    if setup_type in ["TREND_PULLBACK", "BREAKOUT_RETEST", "LIQUIDITY_SWEEP_REVERSAL"]:
        confluence_families.add("PRICE_ACTION")

    if len(confluence_families) < MIN_INDEPENDENT_CONFLUENCES:
        return False, "INSUFFICIENT_CONFLUENCE"

    return True, "QUALIFIED"
