Telegram Config Collector

A fully asynchronous Telegram scraper built with Telethon that:

Scans all your Telegram dialogs (channels, groups, optionally private chats)

Collects messages from the last 24 hours (UTC)

Extracts VPN configuration links (vless://, trojan://, ss://)

Deduplicates them

Saves clean, unique configs to a final output file

Designed for high-volume scanning with no hidden limits.

🚀 Features

✅ Scans ALL dialogs using iter_dialogs() (no built-in limits)

✅ Collects ALL messages in last 24h using iter_messages(limit=None)

✅ Keyword-based chat filtering (vpn, proxy, config, v2ray, etc.)

✅ Optional cache system for selected chats

✅ FloodWait handling

✅ Clean logging system (file + console)

✅ Duplicate config removal

✅ Dry-run mode for safe testing

✅ Debug mode for deep inspection

📦 Project Structure
.
├── Main.py
├── Checker.py
├── configuration.json
├── selected_chats.json (optional cache)
├── RawText.txt
├── Final_Configs.txt
├── Configs.txt
└── telegram_bot.log
⚙️ Requirements

Python 3.9+

Telegram API credentials

Telethon

Install dependencies:

pip install telethon
🔑 Telegram API Setup

Go to https://my.telegram.org

Login

Open API Development Tools

Create an app

Copy:

API_ID

API_HASH

📝 configuration.json

Create a file named:

configuration.json

Example:

{
  "API_ID": 123456,
  "API_HASH": "your_api_hash_here",
  "SESSION_NAME": "tg_session"
}

SESSION_NAME is the name of your local login session file.

🧠 How It Works
1️⃣ Chat Selection

The script:

Iterates through ALL dialogs using iter_dialogs()

Filters by keywords in chat titles:

v2ray

proxy

config

vpn

server

vmess

vless

trojan

shadowsocks

mtproto

outline

network

You can:

Disable keyword filtering

Include private chats

Limit number of chats

Cache selected chats

2️⃣ Message Collection

For each selected chat:

Iterates with iter_messages(limit=None)

Stops when message date < 24h ago

Extracts:

Message text

Embedded URLs

Text URLs

All timestamps handled in UTC.

3️⃣ Raw Output

Messages are written to:

RawText.txt

Only message text content.

Telegram_output.txt

Full report including:

Chat name

Chat ID

Message ID

Date (UTC)

Content

4️⃣ Config Extraction

In Checker.py, this regex is used:

pattern = r"(?:vless|trojan|ss)://[^\s#]+"

Extracts:

vless://

trojan://

ss://

Then:

Appends only new unique configs to Final_Configs.txt

Removes duplicates

Saves clean result to Configs.txt

▶️ Usage
Basic Run
python Main.py

Scans all matched chats, collects last 24h messages, extracts configs.

Debug Mode
python Main.py --debug

Enables verbose logging.

List Dialogs
python Main.py --list-dialogs

Shows first 50 dialogs and exits.

Check Only One Chat
python Main.py --chat 123456789

Useful for testing.

Remove Keyword Filtering
python Main.py --no-keywords

Scans ALL channels/groups.

Include Private Chats
python Main.py --include-users
Limit Number of Chats
python Main.py --max-chats 20
Enable Chat Cache

Save selected chats:

python Main.py --save-cache

Use saved chats:

python Main.py --use-cache

Custom cache file:

python Main.py --cache-file my_chats.json
Add Delay Between Chats

Useful to avoid rate limits:

python Main.py --delay 2

Adds 2 seconds between chat scans.

Dry Run (Safe Mode)
python Main.py --dry-run

No files written

Checker not executed

Only logs

Debug Message Sampling
python Main.py --debug-sample

Logs timestamp of every processed message (very verbose).

📊 Output Files
File	Description
RawText.txt	Raw collected messages
Telegram_output.txt	Detailed report
Final_Configs.txt	Appended unique configs
Configs.txt	Clean deduplicated configs
telegram_bot.log	Log file
🛡 FloodWait Handling

If Telegram rate-limits:

Script waits automatically (asyncio.sleep)

Skips problematic chat

Continues processing

⚡ Performance Notes

Uses async/await everywhere

No message limit

Stops iteration early by time condition

Scales well to large dialog lists

If scanning hundreds of chats, consider:

--delay 1
🔍 Example Flow
Scan dialogs → Filter chats → 
Collect last 24h messages → 
Write raw text → 
Extract configs → 
Remove duplicates → 
Save final output
📌 Security Notes

Your session file stores login data locally

Never share:

API_ID

API_HASH

Session files

🧩 Extending the Project

You can easily extend it to:

Add vmess:// extraction

Add database storage

Add automatic scheduler (cron)

Deploy to VPS

Integrate proxy checker

Add Telegram bot output channel

Build dashboard UI

🧪 Testing Strategy

Start safe:

python Main.py --chat <some_id> --dry-run --debug

Then scale gradually.

🏁 Final Notes

This script is built for:

High-volume Telegram scraping

VPN config aggregation

Automated collection workflows

It uses:

Async architecture

Full dialog traversal

Full message traversal

Time-based stopping condition

If you scale it seriously, consider:

Proxy rotation

Multi-account sharding

Persistent database storage
