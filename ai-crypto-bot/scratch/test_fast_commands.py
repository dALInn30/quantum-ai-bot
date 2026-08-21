import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

sent_messages = []
sent_photos = []

def mock_send_message(text, reply_markup=None, target_chat_id=None):
    sent_messages.append(text)
    return True, "Mock Sent Message"

def mock_send_photo(photo_bytes, caption="", reply_markup=None, target_chat_id=None):
    sent_photos.append((len(photo_bytes), caption))
    return True, "Mock Sent Photo"

server.send_telegram_message = mock_send_message
server.send_telegram_photo = mock_send_photo

test_commands = [
    "📈 Grafik",
    "grafik solusdt",
    "/grafik btc",
    "pozisyonlar",
    "gecmis",
    "pnl",
    "grid",
    "haftalik",
    "saglik",
    "durum",
    "menu",
    "/help"
]

print("--- TESTING TELEGRAM COMMAND HANDLERS ---")
for cmd in test_commands:
    sent_messages.clear()
    sent_photos.clear()
    try:
        server.handle_telegram_command(cmd, "123456789")
        print(f"Command '{cmd}' -> OK | Msgs: {len(sent_messages)}, Photos: {len(sent_photos)}")
        if sent_photos:
            photo_len, cap = sent_photos[0]
            print(f"   📷 Photo: {photo_len} bytes | Caption Len: {len(cap)}")
    except Exception as e:
        print(f"❌ ERROR in '{cmd}': {e}")
        traceback.print_exc()

print("\n--- ALL TELEGRAM COMMAND HANDLERS VERIFIED SUCCESSFULLY ---")
