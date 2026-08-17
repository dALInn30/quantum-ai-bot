import json
import urllib.request
import sys

sys.stdout.reconfigure(encoding='utf-8')

TELEGRAM_CFG = r"c:\Users\User\.gemini\antigravity-ide\scratch\ai-crypto-bot\telegram_config.json"

with open(TELEGRAM_CFG, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

token = cfg.get("bot_token", "").strip()
chat_id = cfg.get("chat_id", "").strip()

print(f"Testing Telegram Config: Token starts with '{token[:10]}...', Chat ID: '{chat_id}'")

# 1. Test Bot Token validity (getMe)
try:
    url_me = f"https://api.telegram.org/bot{token}/getMe"
    req_me = urllib.request.Request(url_me, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_me, timeout=8) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print("Bot Token Test (getMe): SUCCESS! Bot Name:", res.get("result", {}).get("username"))
except Exception as e:
    print("Bot Token Test (getMe): FAILED!", e)

# 2. Test Sending Message
try:
    url_send = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": "🤖 Quantum AI Telegram Bağlantı Test Bildirimi!"
    }).encode('utf-8')
    req_send = urllib.request.Request(url_send, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req_send, timeout=8) as resp:
        res_send = json.loads(resp.read().decode('utf-8'))
        print("Send Message Test: SUCCESS!", res_send)
except Exception as e:
    print("Send Message Test: FAILED!", e)
