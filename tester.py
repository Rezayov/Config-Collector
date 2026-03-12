# Telegram Config Collector with Advanced Proxy Tester

A fully asynchronous Telegram scraper built with **Telethon** that:

* Scans all your Telegram dialogs (channels, groups, optionally private chats)
* Collects messages from the last 24 hours (UTC)
* Extracts VPN configuration links (`vless://`, `trojan://`, `ss://`, `vmess://`)
* Deduplicates them
* **Optionally tests each proxy** using real clients (Xray, shadowsocks-libev) and saves only working ones

Designed for high-volume scanning with no hidden limits, and an **optimized proxy tester** that handles all modern protocols (VLESS, VMESS, Trojan, Shadowsocks) with advanced features like multiple test URLs, realistic TLS/REALITY settings, and detailed diagnostics.

---

## 🚀 Features

### Telegram Collector
* ✅ Scans **ALL dialogs** using `iter_dialogs()` (no built-in limits)
* ✅ Collects **ALL messages in last 24h** using `iter_messages(limit=None)`
* ✅ Keyword-based chat filtering (vpn, proxy, config, v2ray, etc.)
* ✅ Optional cache system for selected chats
* ✅ FloodWait handling
* ✅ Clean logging system (file + console)
* ✅ Duplicate config removal
* ✅ Dry-run mode for safe testing
* ✅ Debug mode for deep inspection

### Advanced Proxy Tester
* ✅ **Supports all major protocols**: VLESS, VMESS, Trojan, Shadowsocks
* ✅ **Full URL parsing** with support for SIP002, VMess JSON, and standard link formats
* ✅ **Network transport handling**: TCP, WebSocket, gRPC, HTTPUpgrade, XHTTP, SplitHTTP, H2, KCP, QUIC
* ✅ **Security profiles**: TLS, REALITY, and none
* ✅ **Multiple test URLs** with fallback (https/http endpoints)
* ✅ **SOCKS5 readiness check** before sending requests
* ✅ **Configurable concurrency and timeouts**
* ✅ **Detailed JSON output** with success/failure reasons
* ✅ **`--all` flag** to print full test results (including failures)

---

# 📦 Project Structure

```
.
├── Main.py
├── Checker.py
├── tester.py                # advanced proxy tester
├── configuration.json
├── selected_chats.json      (optional cache)
├── RawText.txt
├── Final_Configs.txt
├── Configs.txt
├── Working_Configs.txt      # new – only proxies that passed the test
└── telegram_bot.log
```

---

# ⚙️ Requirements

* Python 3.9+
* Telegram API credentials
* Telethon
* **For proxy testing only**: 
  * Python libraries: `aiohttp`, `aiohttp-socks`
  * External clients: `xray` (or `v2ray`), `shadowsocks-libev`

Install Python dependencies:

```bash
pip install telethon aiohttp aiohttp-socks
```

---

# 🔧 Installing External Clients (for Proxy Testing)

The tester uses **Xray** for VLESS/VMESS/Trojan and **ss-local** (from shadowsocks-libev) for Shadowsocks. Install them according to your OS.

## macOS (Homebrew)

```bash
brew install xray shadowsocks-libev
```

## Ubuntu/Debian

```bash
# Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# Shadowsocks-libev
sudo apt update && sudo apt install shadowsocks-libev
```

## Windows

Recommend using **WSL2** with Ubuntu. Alternatively, download binaries manually and place them in your PATH.

After installation, verify each command is available:

```bash
xray version
ss-local --help
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

## 1️⃣ Chat Selection (Main.py)

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

## 2️⃣ Message Collection (Main.py)

For each selected chat:

* Iterates with `iter_messages(limit=None)`
* Stops when message date < 24h ago
* Extracts:

  * Message text
  * Embedded URLs
  * Text URLs

All timestamps handled in **UTC**.

---

## 3️⃣ Raw Output (Main.py)

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

## 4️⃣ Config Extraction (Checker.py)

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

> **Note**: VMESS links are also extracted because they appear as `vmess://` in messages, but the regex can be extended if needed. The tester itself fully supports VMESS.

---

## 5️⃣ Proxy Testing (tester.py)

If you run `Main.py` with `--test-proxies`, or run `tester.py` directly, the following happens:

* **Parsing**: Each config is parsed according to its protocol using robust, protocol‑specific parsers (supports SIP002 for Shadowsocks, VMess JSON, and standard URL formats).
* **Configuration Generation**: For VLESS/VMESS/Trojan, an Xray-compatible JSON config is built with correct `streamSettings` (TLS, REALITY, network transport). For Shadowsocks, an `ss-local` JSON config is generated.
* **Local Client Launch**: The appropriate client (`xray` or `ss-local`) is started with the generated config, binding to a random free port on `127.0.0.1`.
* **Readiness Check**: The script repeatedly attempts to open a TCP connection to the SOCKS5 port until it succeeds or times out.
* **HTTP Test**: Once ready, a SOCKS5 connector is used to send a request to multiple test URLs (e.g., `https://api.ipify.org`, `http://httpbin.org/ip`). If any URL returns a successful response containing an expected key (`ip` or `origin`), the proxy is marked as working.
* **Cleanup**: The client is terminated and the temporary config file is deleted.

The tester runs **concurrently** (default 5 tests at once) and provides detailed logs and result summaries.

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

After collection, runs the tester on `Configs.txt` and writes working configs to `Working_Configs.txt`.

## Run Tester Directly

If you already have a file with configs (e.g., `my_configs.txt`), you can test them directly:

```bash
python tester.py -f my_configs.txt
```

By default, only working configs are printed to stdout. Use `--all` to see full results (including failures and reasons):

```bash
python tester.py -f my_configs.txt --all
```

### Tester Environment Variables

Set `PROXY_TEST_LOGLEVEL` to control logging verbosity (e.g., `DEBUG`, `INFO`):

```bash
export PROXY_TEST_LOGLEVEL=DEBUG
python tester.py -f Configs.txt
```

---

# 📊 Output Files

| File                | Description                          |
|---------------------|--------------------------------------|
| RawText.txt         | Raw collected messages               |
| Telegram_output.txt | Detailed report                      |
| Final_Configs.txt   | Appended unique configs               |
| Configs.txt         | Clean deduplicated configs            |
| Working_Configs.txt | **Only proxies that passed the test** |
| telegram_bot.log    | Log file from Main.py                 |

When running `tester.py` directly, no files are created unless you redirect output.

---

# 🔍 Tester Features in Detail

### Supported Protocols & Transports

| Protocol  | Networks Supported                                                                 | Security         |
|-----------|------------------------------------------------------------------------------------|------------------|
| VLESS     | tcp, ws, grpc, httpupgrade, xhttp, splithttp, h2, kcp, quic                       | none, tls, reality |
| VMESS     | tcp, ws, grpc, httpupgrade, xhttp, splithttp, h2, kcp, quic                       | none, tls, reality |
| Trojan    | tcp, ws, grpc, httpupgrade, xhttp, splithttp, h2, kcp, quic                       | tls, reality      |
| Shadowsocks| tcp only (via `ss-local`)                                                        | encryption methods|

### Parsing Capabilities

- **Shadowsocks**: SIP002 format (`ss://base64(method:password)@host:port`) and legacy with `@`.
- **VMess**: Base64-encoded JSON, including all standard fields (`add`, `port`, `id`, `aid`, `net`, `tls`, `sni`, etc.).
- **VLESS/Trojan**: Standard URL format with query parameters; supports all Xray core parameters (flow, security, network, etc.).

### Test URLs & Fallback

The tester tries multiple URLs in order:
1. `https://api.ipify.org?format=json`
2. `https://httpbin.org/ip`
3. `http://httpbin.org/ip`

If any returns a successful JSON containing an `"ip"` or `"origin"` field (or non‑empty plain text), the test passes.

### Concurrency & Timeouts

| Setting               | Default | Description                                      |
|-----------------------|---------|--------------------------------------------------|
| `CONCURRENT_TESTS`    | 5       | Maximum parallel tests                           |
| `TEST_TIMEOUT`        | 12 s    | Timeout for the entire HTTP request (per proxy)  |
| `STARTUP_TIMEOUT`     | 10 s    | How long to wait for the local SOCKS to be ready |
| `READINESS_CHECK_INTERVAL` | 0.25 s | Interval between SOCKS port checks            |

You can adjust these directly in the source.

---

# 🛡 FloodWait Handling (Main.py)

If Telegram rate-limits:

* Script waits automatically (`asyncio.sleep`)
* Skips problematic chat
* Continues processing

---

# ⚡ Performance Notes

* Uses async/await everywhere
* No message limit in collection
* Stops iteration early by time condition
* Scales well to large dialog lists

If scanning hundreds of chats, consider:

```bash
--delay 1
```

For testing, concurrency is limited to 5 to avoid overloading your system and the remote servers.

---

# 🔍 Example Flow (with Testing)

```
Scan dialogs → Filter chats → 
Collect last 24h messages → 
Write raw text → 
Extract configs → 
Remove duplicates → 
Save final output → 
Test each proxy (tester.py) → 
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

* Add database storage
* Add automatic scheduler (cron)
* Deploy to VPS
* Add Telegram bot to receive working configs
* Build dashboard UI
* Add more sophisticated proxy testing (speed, latency, region)

The tester’s modular design allows easy addition of new protocols or custom test logic.

---

# 🧪 Testing Strategy

Start safe:

```bash
python Main.py --chat <some_id> --dry-run --debug
```

Then test with a small set:

```bash
python Main.py --max-chats 5 --test-proxies
```

Finally run full scan:

```bash
python Main.py --test-proxies
```

---

# 🏁 Final Notes

This script is built for:

* High-volume Telegram scraping
* VPN config aggregation
* Automated collection workflows
* **Reliable proxy validation** using real clients and realistic network simulation

It uses:

* Async architecture
* Full dialog traversal
* Full message traversal
* Time-based stopping condition
* Real proxy testing with industry-standard tools
* Advanced protocol support (including REALITY, gRPC, WebSocket, etc.)

If you scale it seriously, consider:

* Proxy rotation for Telegram API
* Multi-account sharding
* Persistent database storage
* Distributed testing (multiple machines)

---

**Happy collecting and testing!** 🚀
