# Telegram V2Ray Config Collector

A small, debug-friendly Python tool that scans your Telegram dialogs for the **last 24 hours (UTC)**, saves the collected text to a raw file, and extracts **unique** proxy configs (e.g., `vless://`, `trojan://`, `ss://`) into a final output file.

> Built with **Telethon** (Telegram API client) + a custom regex-based checker (`checker.py`).

---

## Features

- Collects messages from selected chats within the **last 24 hours (UTC)**
- Supports Telegram message entities:
  - embedded URLs (`MessageEntityTextUrl`)
  - plain URL entities (`MessageEntityUrl`)
- Auto-selects “relevant” chats by keywords (config/vpn/proxy related)
- Caches selected chats to speed up future runs (`selected_chats.json`)
- Outputs:
  - `RawText.txt` (raw combined text, used as checker input)
  - `Telegram_output.txt` (human-readable debug report)
  - `Final_Configs.txt` (unique extracted configs)

---

## Requirements

- Python **3.9+** (recommended)
- A Telegram API app:
  - `API_ID`
  - `API_HASH`
- Telethon library

---

## Installation

### 1) Clone & create a virtual environment

```bash
git clone <YOUR_REPO_URL>
cd <YOUR_PROJECT_FOLDER>

python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

2) Install dependencies
pip install telethon


If you have a requirements.txt, use:

pip install -r requirements.txt

Configuration

Create a file named configuration.json in the project root:

{
  "API_ID": 123456,
  "API_HASH": "YOUR_API_HASH",
  "SESSION_NAME": "my_session"
}


SESSION_NAME is the local session file name Telethon creates (e.g., my_session.session).

Keep configuration.json private. Do not commit it.

Project Files

Typical structure:

.
├── main.py
├── checker.py
├── configuration.json          # private (do not commit)
├── selected_chats.json         # auto-generated cache
├── RawText.txt                 # generated
├── Telegram_output.txt         # generated
├── Final_Configs.txt           # generated
└── telegram_bot.log            # generated

Usage
Basic run
python main.py


On first run, it will ask for:

your phone number (with country code)

the login code

(optional) 2FA password if enabled

CLI Options
Enable verbose logging
python main.py --debug

List dialogs (to find chat IDs)
python main.py --list-dialogs

Scan only a specific chat (by dialog.id)
python main.py --chat 123456789

Ignore cached chat selection and re-select chats
python main.py --no-cache

Dry run (no file output, no checker)
python main.py --dry-run

Tuning collection parameters
python main.py --max-chats 15 --per-chat-limit 300 --delay 2.0

Extremely verbose per-message timestamp logs
python main.py --debug --debug-sample

How Chat Selection Works

The script fetches your dialogs.

It filters group/channel titles by keywords like:
v2ray, proxy, config, vpn, vmess, vless, trojan, shadowsocks, etc.

It selects up to --max-chats matches.

It saves selected dialog.id values to selected_chats.json.

If no keyword matches exist, it falls back to the first N dialogs.

Output Details

RawText.txt

concatenation of message text + extracted entity URLs

input for checker.py

Telegram_output.txt

readable report including chat name, message id, UTC date, and content

useful for debugging extraction issues

Final_Configs.txt

unique extracted configs appended over time

produced by checker.extract_and_append_unique_configs(...)

telegram_bot.log

logs for debugging and auditing

Notes About Time Window (Important)

This tool collects messages from the last 24 hours in UTC.

Telegram message timestamps from Telethon are typically timezone-aware and align well with UTC comparisons.

The collection stops early per chat when reaching messages older than the start window.

Security & Privacy

Do not commit:

configuration.json

session files (*.session)

output logs/files containing sensitive data

Add these to .gitignore:

configuration.json
*.session
selected_chats.json
RawText.txt
Telegram_output.txt
Final_Configs.txt
telegram_bot.log
__pycache__/
.venv/

Troubleshooting
FloodWait / Rate limits

Telegram may rate-limit you. The script catches FloodWaitError, sleeps for the required duration, and continues.

Login issues / 2FA enabled

If you have two-step verification, you will be prompted for your password.

Nothing extracted

Check Telegram_output.txt to see if messages were collected.

Ensure checker.py pattern supports the formats you expect.

Increase --per-chat-limit if chats are very active.