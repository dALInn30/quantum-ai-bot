import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def normalize_tok(s):
    if not s:
        return ""
    s = s.upper()
    s = s.replace("Ğ", "G").replace("İ", "I").replace("İ", "I").replace("Ö", "O").replace("Ü", "U").replace("Ş", "S").replace("Ç", "C")
    return s

def extract_target_symbol_from_cmd(cmd_text, state):
    ignore_tokens = {
        "📈", "📊", "📷", "🚀", "🌐", "🤖", "🧹", "📜", "💰", "⚡",
        "GRAFIK", "/GRAFIK", "GRAFIGI", "GRAFIGINI",
        "CHART", "/CHART", "ANALIZ", "/ANALIZ", "ANALIZI",
        "CMD_CHART", "CMD_ANALIZ", "HD", "CANLI", "TEKNIK", "RESIM",
        "FOTO", "GORSEL", "GOSTER", "VERI"
    }
    
    parts = cmd_text.strip().split()
    candidate_sym = None

    for p in parts:
        p_clean = normalize_tok(p.replace("/", "").replace("-", "").strip())
        if not p_clean or p_clean in ignore_tokens:
            continue
            
        p_alpha = "".join(c for c in p_clean if c.isalnum() and c.isascii())
        if not p_alpha or p_alpha in ignore_tokens:
            continue
            
        sym_cand = p_alpha
        if not sym_cand.endswith("USDT") and not sym_cand.endswith("BUSD"):
            sym_cand += "USDT"
            
        if len(p_alpha) >= 2 and len(p_alpha) <= 12:
            candidate_sym = sym_cand
            break

    if candidate_sym:
        return candidate_sym

    if state.get("positions"):
        return state["positions"][0].get("symbol", "BTCUSDT")
    elif state.get("grid_bots"):
        return state["grid_bots"][0].get("symbol", "BTCUSDT")
    else:
        return "BTCUSDT"

state_dummy = {"positions": []}
test_cases = [
    "📷 Analiz Grafiği",
    "📷 Analiz Grafiği SOL",
    "📈 Grafik ETH",
    "grafik solusdt",
    "/grafik btc",
    "📷 HD Analiz Grafiği AVAX",
    "📷 Analiz Grafiğini Göster"
]

for tc in test_cases:
    res = extract_target_symbol_from_cmd(tc, state_dummy)
    clean_tc = tc.replace("📷", "[CAMERA]").replace("📈", "[CHART]")
    print(f"Test case: '{clean_tc}' -> Extracted target_sym: '{res}'")
