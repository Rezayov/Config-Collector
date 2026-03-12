# Telegram Config Collector with Built-in Proxy Tester

A fully asynchronous Telegram scraper built with **Telethon** that:

* Scans all your Telegram dialogs (channels, groups, optionally private chats)
* Collects messages from the last 24 hours (UTC)
* Extracts VPN configuration links (`vless://`, `trojan://`, `ss://`)
* Deduplicates them
* **Optionally tests each proxy** using real clients (Xray, shadowsocks, trojan) and saves only working ones

Designed for high-volume scanning with no hidden limits.

---

## 🚀 Features

* ✅ Scans **ALL dialogs** using `iter_dialogs()` (no built-in limits)
* ✅ Collects **ALL messages in last 24h** using `iter_messages(limit=None)`
* ✅ Keyword-based chat filtering (vpn, proxy, config, v2ray, etc.)
* ✅ Optional cache system for selected chats
* ✅ FloodWait handling
* ✅ Clean logging system (file + console)
* ✅ Duplicate config removal
* ✅ Dry-run mode for safe testing
* ✅ Debug mode for deep inspection
* ✅ **Proxy testing** (optional) – runs each config through real clients and verifies connectivity via HTTP request
* ✅ Outputs a clean list of **working proxies** only

---

# 📦 Project Structure

```
.
├── Main.py
├── Checker.py
├── tester.py                # new proxy testing module
├── configuration.json
├── selected_chats.json      (optional cache)
├── RawText.txt
├── Final_Configs.txt
├── Configs.txt
├── Working_Configs.txt       # new – only proxies that passed the test
└── telegram_bot.log
```

---

# ⚙️ Requirements

* Python 3.9+
* Telegram API credentials
* Telethon
* **For proxy testing only**: 
  * Python libraries: `aiohttp`, `aiohttp-socks`
  * External clients: `xray` (or `v2ray`), `shadowsocks-libev`, `trojan`

Install Python dependencies:

```bash
pip install telethon aiohttp aiohttp-socks
```

---

# 🔧 Installing External Clients (for Proxy Testing)

The tester uses real proxy clients to verify connectivity. Install them according to your OS.

## macOS (Homebrew)

```bash
brew install xray shadowsocks-libev trojan
```

## Ubuntu/Debian

```bash
# Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# Shadowsocks-libev
sudo apt update && sudo apt install shadowsocks-libev

# Trojan (optional, can use Xray instead)
sudo apt install trojan
```

## Windows

Recommend using **WSL2** with Ubuntu. Alternatively, download binaries manually and place them in your PATH.

After installation, verify each command is available:

```bash
xray version
ss-local --help
trojan --version
```

---

# 🔑 Telegram API Setup

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Login
3. Open **API Development Tools**
4. Create an app
5. Copy:

* `API_ID`
* `API_HASH`

---

# 📝 configuration.json

Create a file named:

```
configuration.json
```

Example:

```json
{
  "API_ID": 123456,
  "API_HASH": "your_api_hash_here",
  "SESSION_NAME": "tg_session"
}
```

* `SESSION_NAME` is the name of your local login session file.

---

# 🧠 How It Works

## 1️⃣ Chat Selection

The script:

* Iterates through ALL dialogs using `iter_dialogs()`
* Filters by keywords in chat titles:

  * v2ray
  * proxy
  * config
  * vpn
  * server
  * vmess
  * vless
  * trojan
  * shadowsocks
  * mtproto
  * outline
  * network

You can:

* Disable keyword filtering
* Include private chats
* Limit number of chats
* Cache selected chats

---

## 2️⃣ Message Collection

For each selected chat:

* Iterates with `iter_messages(limit=None)`
* Stops when message date < 24h ago
* Extracts:

  * Message text
  * Embedded URLs
  * Text URLs

All timestamps handled in **UTC**.

---

## 3️⃣ Raw Output

Messages are written to:

### `RawText.txt`

Only message text content.

### `Telegram_output.txt`

Full report including:

* Chat name
* Chat ID
* Message ID
* Date (UTC)
* Content

---

## 4️⃣ Config Extraction

In `Checker.py`, this regex is used:

```python
pattern = r"(?:vless|trojan|ss)://[^\s#]+"
```

Extracts:

* `vless://`
* `trojan://`
* `ss://`

Then:

* Appends only new unique configs to `Final_Configs.txt`
* Removes duplicates
* Saves clean result to `Configs.txt`

---

## 5️⃣ Proxy Testing (Optional)

If you run with `--test-proxies`, the script will:

* Launch `tester.py` as a subprocess
* `tester.py` parses each config from `Configs.txt`
* For each config, it:
  * Generates a temporary client configuration file (for Xray, ss-local, or trojan)
  * Starts the client locally on a random port
  * Waits for it to be ready
  * Sends an HTTP request through the SOCKS5 proxy to `http://httpbin.org/ip`
  * If the request succeeds and returns a valid IP, the config is marked as working
* All working configs are saved to **`Working_Configs.txt`**

The tester is fully asynchronous, runs multiple tests concurrently (default 5), and respects timeouts.

---

# ▶️ Usage

## Basic Run (Collect Only)

```bash
python Main.py
```

Scans all matched chats, collects last 24h messages, extracts configs, and saves to `Configs.txt`.

## Collect + Test Proxies

```bash
python Main.py --test-proxies
```

After collection, tests all configs and writes only working ones to `Working_Configs.txt`.

## Debug Mode

```bash
python Main.py --debug
```

Enables verbose logging.

## List Dialogs

```bash
python Main.py --list-dialogs
```

Shows first 50 dialogs and exits.

## Check Only One Chat

```bash
python Main.py --chat 123456789
```

Useful for testing.

## Remove Keyword Filtering

```bash
python Main.py --no-keywords
```

Scans ALL channels/groups.

## Include Private Chats

```bash
python Main.py --include-users
```

## Limit Number of Chats

```bash
python Main.py --max-chats 20
```

## Enable Chat Cache

Save selected chats:

```bash
python Main.py --save-cache
```

Use saved chats:

```bash
python Main.py --use-cache
```

Custom cache file:

```bash
python Main.py --cache-file my_chats.json
```

## Add Delay Between Chats

Useful to avoid rate limits:

```bash
python Main.py --delay 2
```

Adds 2 seconds between chat scans.

## Dry Run (Safe Mode)

```bash
python Main.py --dry-run
```

* No files written
* Checker not executed
* Only logs

## Debug Message Sampling

```bash
python Main.py --debug-sample
```

Logs timestamp of every processed message (very verbose).

---

# 📊 Output Files

| File                | Description                          |
|---------------------|--------------------------------------|
| RawText.txt         | Raw collected messages               |
| Telegram_output.txt | Detailed report                      |
| Final_Configs.txt   | Appended unique configs               |
| Configs.txt         | Clean deduplicated configs            |
| Working_Configs.txt | **Only proxies that passed the test** |
| telegram_bot.log    | Log file                             |

---

# 🛡 FloodWait Handling

If Telegram rate-limits:

* Script waits automatically (`asyncio.sleep`)
* Skips problematic chat
* Continues processing

---

# ⚡ Performance Notes

* Uses async/await everywhere
* No message limit
* Stops iteration early by time condition
* Scales well to large dialog lists

If scanning hundreds of chats, consider:

```bash
--delay 1
```

For testing, concurrency is limited to 5 to avoid overloading your system and the remote servers. You can adjust this in `tester.py` (variable `CONCURRENT_TESTS`).

---

# 🔍 Example Flow (with Testing)

```
Scan dialogs → Filter chats → 
Collect last 24h messages → 
Write raw text → 
Extract configs → 
Remove duplicates → 
Save final output → 
Test each proxy → 
Save working configs
```

---

# 📌 Security Notes

* Your session file stores login data locally
* Never share:

  * API_ID
  * API_HASH
  * Session files

* Proxy testing runs local clients – no data leaves your machine except the test HTTP request through the proxy.

---

# 🧩 Extending the Project

You can easily extend it to:

* Add `vmess://` extraction (already supported in tester but not in checker? Checker regex only covers vless, trojan, ss. You can extend regex.)
* Add database storage
* Add automatic scheduler (cron)
* Deploy to VPS
* Add Telegram bot to receive working configs
* Build dashboard UI
* Add more sophisticated proxy testing (speed, latency, region)

---

# 🧪 Testing Strategy

Start safe:

```
python Main.py --chat <some_id> --dry-run --debug
```

Then test with a small set:

```
python Main.py --max-chats 5 --test-proxies
```

Finally run full scan.

---

# 🏁 Final Notes

This script is built for:

* High-volume Telegram scraping
* VPN config aggregation
* Automated collection workflows
* **Reliable proxy validation** using real clients

It uses:

* Async architecture
* Full dialog traversal
* Full message traversal
* Time-based stopping condition
* Real proxy testing with industry-standard tools

If you scale it seriously, consider:

* Proxy rotation for Telegram API
* Multi-account sharding
* Persistent database storage
* Distributed testing (multiple machines)
