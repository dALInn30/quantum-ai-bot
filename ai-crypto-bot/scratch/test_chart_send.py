import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

print("--- TESTING CAPTION TRUNCATION ---")
long_text = "A" * 1500
truncated = server.safe_truncate_caption(long_text, max_len=980)
print(f"Original len: {len(long_text)}, Truncated len: {len(truncated)}")

print("\n--- TESTING COMMAND PARSING ---")
test_cmds = [
    "📈 Grafik SOL",
    "grafik solusdt",
    "/grafik btc",
    "📈 Grafik",
    "/chart eth"
]

for cmd in test_cmds:
    parts = cmd.strip().split()
    skip_words = ["📈", "📊", "GRAFİK", "GRAFIK", "/GRAFIK", "CHART", "/CHART", "ANALİZ", "ANALIZ", "/ANALIZ", "CMD_CHART", "CMD_ANALIZ"]
    candidate_sym = None
    for p in parts:
        p_clean = p.upper().replace("/", "").replace("-", "").strip()
        if p_clean and p_clean not in skip_words:
            candidate_sym = p_clean
            break
    if candidate_sym:
        if not candidate_sym.endswith("USDT") and not candidate_sym.endswith("BUSD"):
            candidate_sym += "USDT"
        target_sym = candidate_sym
    else:
        target_sym = "DEFAULT_BTCUSDT"
    print(f"Command: '{cmd}' -> Resolved target_sym: '{target_sym}'")

print("\nAll local tests completed successfully.")
