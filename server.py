import os
import sys

# Change working directory to ai-crypto-bot directory
bot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai-crypto-bot")
if os.path.exists(bot_dir):
    os.chdir(bot_dir)
    sys.path.insert(0, bot_dir)

# Import and launch main server module
import server
