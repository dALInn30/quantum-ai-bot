import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import json
import urllib.request

def test_candlesticks():
    # Fetch real 50 klines from Binance
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        klines = json.loads(resp.read().decode('utf-8'))

    print(f"Fetched {len(klines)} real klines for BTCUSDT.")

    # Create figure with 2 subplots (Price Candles + Volume)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), dpi=120, gridspec_kw={'height_ratios': [3.5, 1]})
    fig.patch.set_facecolor('#0b0e14')
    ax1.set_facecolor('#131722')
    ax2.set_facecolor('#131722')

    n = len(klines)
    x_indices = list(range(n))

    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    # Draw Candlesticks
    width = 0.55
    for i in range(n):
        o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], volumes[i]
        is_bull = c >= o
        color = '#00e676' if is_bull else '#ff1744'
        edge_color = '#00c853' if is_bull else '#d50000'

        # Wick line
        ax1.vlines(i, l, h, color=color, linewidth=1.1, alpha=0.9, zorder=3)

        # Body rectangle
        body_bottom = o if is_bull else c
        body_height = max(abs(c - o), (h - l) * 0.02 or 0.1)
        rect = patches.Rectangle((i - width/2, body_bottom), width, body_height,
                                 facecolor=color, edgecolor=edge_color, linewidth=0.8, zorder=4)
        ax1.add_patch(rect)

        # Volume Bar
        ax2.bar(i, v, color=color, width=0.6, alpha=0.75)

    # EMA 20 Calculation & Line
    ema20 = []
    k_mult = 2 / (20 + 1)
    for i, c in enumerate(closes):
        if i == 0:
            ema20.append(c)
        else:
            ema20.append(c * k_mult + ema20[-1] * (1 - k_mult))
    
    ax1.plot(x_indices, ema20, color='#ffd700', linewidth=1.5, label='EMA 20', zorder=5)

    # TP/SL lines
    curr_p = closes[-1]
    tp1 = round(curr_p * 1.02, 2)
    sl = round(curr_p * 0.98, 2)
    ax1.axhline(tp1, color='#00e676', linestyle='--', linewidth=1.5, zorder=6)
    ax1.text(n - 1, tp1, f' [TP1]: ${tp1}', color='#00e676', fontsize=8, fontweight='bold', va='bottom')

    ax1.axhline(sl, color='#ff1744', linestyle='--', linewidth=1.5, zorder=6)
    ax1.text(n - 1, sl, f' [SL]: ${sl}', color='#ff1744', fontsize=8, fontweight='bold', va='top')

    # Formatting
    ax1.set_title(f'QUANTUM AI MUM GRAFİĞİ: BTCUSDT (${curr_p:,.2f})', color='#ffffff', fontsize=12, fontweight='bold', pad=12)
    ax1.grid(True, color='#ffffff', alpha=0.07, linestyle='-')
    ax2.grid(True, color='#ffffff', alpha=0.07, linestyle='-')
    ax1.tick_params(colors='#888888', labelsize=8)
    ax2.tick_params(colors='#888888', labelsize=8)
    ax2.set_ylabel('Hacim', color='#888888', fontsize=8)

    for spine in ax1.spines.values():
        spine.set_color('#222836')
    for spine in ax2.spines.values():
        spine.set_color('#222836')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    
    img_bytes = buf.getvalue()
    print("Generated Candlestick Chart PNG Bytes:", len(img_bytes))

if __name__ == '__main__':
    test_candlesticks()
