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

