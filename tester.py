#!/usr/bin/env python3

import asyncio
import base64
import json
import logging
import os
import socket
import sys
import tempfile
import time
import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlparse, unquote, parse_qsl

import aiohttp
from aiohttp_socks import ProxyConnector


CONCURRENT_TESTS = 20
TEST_TIMEOUT = 10
STARTUP_TIMEOUT = 8
PER_PROXY_TIMEOUT = 25
READINESS_CHECK_INTERVAL = 0.25
PROGRESS_INTERVAL = 5
LOCAL_HOST = "127.0.0.1"

TEST_URLS = [
    "https://api.ipify.org?format=json",
    "https://httpbin.org/ip",
    "http://httpbin.org/ip",
]

EXPECTED_KEYS = {"ip", "origin"}

LOG_LEVEL = os.environ.get("PROXY_TEST_LOGLEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("proxy-tester")


@dataclass
class TestResult:
    proxy: str
    ok: bool
    reason: str
    proxy_type: Optional[str] = None
    local_port: Optional[int] = None
    elapsed: float = 0.0
    log_file: Optional[str] = None


def pad_b64(s: str) -> str:
    s = s.strip()
    return s + "=" * ((4 - len(s) % 4) % 4)


def b64_decode_urlsafe(s: str) -> bytes:
    return base64.urlsafe_b64decode(pad_b64(s))


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOCAL_HOST, 0))
        return int(s.getsockname()[1])


def parse_bool_like(v: Optional[str]) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on", "tls", "reality"}


def normalize_v2_network(v: Optional[str]) -> str:
    if not v:
        return "tcp"
    v = v.strip().lower()
    mapping = {
        "tcp": "tcp",
        "ws": "ws",
        "websocket": "ws",
        "grpc": "grpc",
        "gun": "grpc",
        "http": "httpupgrade",
        "httpupgrade": "httpupgrade",
        "xhttp": "xhttp",
        "splithttp": "splithttp",
        "h2": "h2",
        "http2": "h2",
        "kcp": "kcp",
        "mkcp": "kcp",
        "quic": "quic",
    }
    return mapping.get(v, v)


def parse_host_port(host_port: str, default_port: int = 443) -> Tuple[str, int]:
    host_port = host_port.strip()

    if host_port.startswith("["):
        end = host_port.find("]")
        if end == -1:
            raise ValueError("invalid IPv6 host")
        host = host_port[1:end]
        rest = host_port[end + 1 :]
        if rest.startswith(":"):
            return host, int(rest[1:])
        return host, default_port

    if host_port.count(":") == 1:
        host, port_str = host_port.rsplit(":", 1)
        return host, int(port_str)

    if host_port.count(":") > 1:
        return host_port, default_port

    return host_port, default_port


def parse_ss_url(proxy_url: str) -> Optional[Dict[str, Any]]:
    try:
        raw = proxy_url.strip()
        rest = raw[5:]

        if "#" in rest:
            rest, frag = rest.split("#", 1)
            tag = unquote(frag)
        else:
            tag = ""

        if "@" in rest:
            left, right = rest.rsplit("@", 1)
            host, port = parse_host_port(right)
            try:
                decoded = b64_decode_urlsafe(left).decode("utf-8")
            except Exception:
                decoded = left
            if ":" not in decoded:
                return None
            method, password = decoded.split(":", 1)
        else:
            decoded = b64_decode_urlsafe(rest).decode("utf-8")
            if "@" not in decoded:
                return None
            creds, host_port = decoded.rsplit("@", 1)
            if ":" not in creds:
                return None
            method, password = creds.split(":", 1)
            host, port = parse_host_port(host_port)

        return {
            "type": "ss",
            "raw": raw,
            "host": host,
            "port": port,
            "method": method,
            "password": password,
            "tag": tag,
        }
    except Exception:
        return None


def parse_vmess_url(proxy_url: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = urlparse(proxy_url.strip())
        b64_part = parsed.netloc or parsed.path.lstrip("/")
        decoded = b64_decode_urlsafe(b64_part).decode("utf-8")
        data = json.loads(decoded)

        network = normalize_v2_network(data.get("net") or data.get("type") or "tcp")
        port = int(data.get("port", 0))

        result = {
            "type": "vmess",
            "raw": proxy_url.strip(),
            "host": data.get("add") or data.get("host"),
            "port": port,
            "id": data.get("id"),
            "aid": int(data.get("aid", 0) or 0),
            "user_security": data.get("scy") or data.get("security") or "auto",
            "network": network,
            "path": data.get("path", ""),
            "host_header": data.get("host", ""),
            "sni": data.get("sni", ""),
            "alpn": data.get("alpn", ""),
            "service_name": data.get("serviceName", ""),
            "authority": data.get("authority", ""),
            "fp": data.get("fp", ""),
            "pbk": data.get("pbk", ""),
            "sid": data.get("sid", ""),
            "spx": data.get("spx", ""),
            "flow": data.get("flow", ""),
        }

        tls_field = str(data.get("tls", "")).strip().lower()
        if tls_field in {"tls", "1", "true"}:
            result["security"] = "tls"
        elif tls_field == "reality":
            result["security"] = "reality"
        else:
            result["security"] = "none"

        if not result["host"] or not result["port"] or not result["id"]:
            return None

        return result
    except Exception:
        return None


def parse_vless_or_trojan_url(proxy_url: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = urlparse(proxy_url.strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"vless", "trojan"}:
            return None

        netloc = parsed.netloc
        if "@" in netloc:
            userinfo, host_port = netloc.split("@", 1)
        else:
            userinfo, host_port = "", netloc

        host, port = parse_host_port(host_port)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        network = normalize_v2_network(params.get("type") or params.get("network") or "tcp")
        security = (params.get("security") or "").strip().lower()
        if not security:
            security = "tls" if parse_bool_like(params.get("tls")) else "none"

        result = {
            "type": scheme,
            "raw": proxy_url.strip(),
            "host": host,
            "port": port,
            "network": network,
            "security": security,
            "params": params,
            "tag": unquote(parsed.fragment) if parsed.fragment else "",
            "sni": params.get("sni") or params.get("serverName") or "",
            "alpn": params.get("alpn", ""),
            "fp": params.get("fp", ""),
            "pbk": params.get("pbk", ""),
            "sid": params.get("sid", ""),
            "spx": params.get("spx", ""),
            "flow": params.get("flow", ""),
            "service_name": params.get("serviceName", ""),
            "authority": params.get("authority", ""),
            "path": unquote(params.get("path", "")),
            "host_header": params.get("host") or params.get("Host") or "",
            "mode": params.get("mode", ""),
            "header_type": params.get("headerType", ""),
            "seed": params.get("seed", ""),
            "quic_security": params.get("quicSecurity", ""),
            "key": params.get("key", ""),
        }

        if scheme == "vless":
            result["id"] = userinfo
            if not result["id"]:
                return None
        else:
            result["password"] = userinfo
            if not result["password"]:
                return None

        return result
    except Exception:
        return None


def parse_proxy_url(proxy_url: str) -> Optional[Dict[str, Any]]:
    proxy_url = proxy_url.strip()
    if not proxy_url:
        return None

    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()

    if scheme == "ss":
        return parse_ss_url(proxy_url)
    if scheme == "vmess":
        return parse_vmess_url(proxy_url)
    if scheme in {"vless", "trojan"}:
        return parse_vless_or_trojan_url(proxy_url)

    return None


def build_tls_or_reality_settings(parsed: Dict[str, Any]) -> Dict[str, Any]:
    security = (parsed.get("security") or "none").lower()
    stream_settings: Dict[str, Any] = {
        "network": parsed.get("network", "tcp"),
        "security": security if security in {"tls", "reality"} else "none",
    }

    if security == "tls":
        tls_settings: Dict[str, Any] = {"allowInsecure": True}
        server_name = parsed.get("sni") or parsed.get("host")
        if server_name:
            tls_settings["serverName"] = server_name
        alpn = parsed.get("alpn")
        if alpn:
            tls_settings["alpn"] = [x.strip() for x in alpn.split(",") if x.strip()]
        fp = parsed.get("fp")
        if fp:
            tls_settings["fingerprint"] = fp
        stream_settings["tlsSettings"] = tls_settings

    elif security == "reality":
        reality_settings: Dict[str, Any] = {}
        server_name = parsed.get("sni") or parsed.get("host")
        if server_name:
            reality_settings["serverName"] = server_name
        if parsed.get("fp"):
            reality_settings["fingerprint"] = parsed["fp"]
        if parsed.get("pbk"):
            reality_settings["publicKey"] = parsed["pbk"]
        if parsed.get("sid"):
            reality_settings["shortId"] = parsed["sid"]
        if parsed.get("spx"):
            reality_settings["spiderX"] = parsed["spx"]
        stream_settings["realitySettings"] = reality_settings

    return stream_settings


def attach_transport_settings(stream_settings: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    network = parsed.get("network", "tcp")

    if network == "ws":
        headers = {}
        if parsed.get("host_header"):
            headers["Host"] = parsed["host_header"]
        stream_settings["wsSettings"] = {
            "path": parsed.get("path", "") or "/",
            "headers": headers,
        }

    elif network == "grpc":
        grpc_settings: Dict[str, Any] = {}
        if parsed.get("service_name"):
            grpc_settings["serviceName"] = parsed["service_name"]
        if parsed.get("authority"):
            grpc_settings["authority"] = parsed["authority"]
        if parsed.get("mode"):
            grpc_settings["multiMode"] = parsed["mode"].lower() == "multi"
        stream_settings["grpcSettings"] = grpc_settings

    elif network == "httpupgrade":
        headers = {}
        if parsed.get("host_header"):
            headers["Host"] = parsed["host_header"]
        stream_settings["httpupgradeSettings"] = {
            "path": parsed.get("path", "") or "/",
            "host": parsed.get("host_header", ""),
            "headers": headers,
        }

    elif network == "xhttp":
        stream_settings["xhttpSettings"] = {
            "path": parsed.get("path", "") or "/",
            "host": parsed.get("host_header", ""),
            "mode": parsed.get("mode", "") or "auto",
        }

    elif network == "splithttp":
        stream_settings["splithttpSettings"] = {
            "path": parsed.get("path", "") or "/",
            "host": parsed.get("host_header", ""),
        }

    elif network == "h2":
        hosts = []
        if parsed.get("host_header"):
            hosts = [x.strip() for x in parsed["host_header"].split(",") if x.strip()]
        stream_settings["httpSettings"] = {
            "path": parsed.get("path", "") or "/",
            "host": hosts,
        }

    elif network == "kcp":
        kcp_settings: Dict[str, Any] = {}
        if parsed.get("header_type"):
            kcp_settings["header"] = {"type": parsed["header_type"]}
        if parsed.get("seed"):
            kcp_settings["seed"] = parsed["seed"]
        stream_settings["kcpSettings"] = kcp_settings

    elif network == "quic":
        quic_settings: Dict[str, Any] = {}
        if parsed.get("quic_security"):
            quic_settings["security"] = parsed["quic_security"]
        if parsed.get("key"):
            quic_settings["key"] = parsed["key"]
        if parsed.get("header_type"):
            quic_settings["header"] = {"type": parsed["header_type"]}
        stream_settings["quicSettings"] = quic_settings


def generate_xray_config(parsed: Dict[str, Any], local_port: int) -> Dict[str, Any]:
    proxy_type = parsed["type"]

    if proxy_type == "vless":
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": parsed["host"],
                        "port": parsed["port"],
                        "users": [
                            {
                                "id": parsed["id"],
                                "encryption": "none",
                                **({"flow": parsed["flow"]} if parsed.get("flow") else {}),
                            }
                        ],
                    }
                ]
            },
        }

    elif proxy_type == "vmess":
        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": parsed["host"],
                        "port": parsed["port"],
                        "users": [
                            {
                                "id": parsed["id"],
                                "alterId": parsed.get("aid", 0),
                                "security": parsed.get("user_security", "auto"),
                            }
                        ],
                    }
                ]
            },
        }

    elif proxy_type == "trojan":
        outbound = {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": parsed["host"],
                        "port": parsed["port"],
                        "password": parsed["password"],
                        **({"flow": parsed["flow"]} if parsed.get("flow") else {}),
                    }
                ]
            },
        }

    else:
        raise ValueError(f"unsupported xray protocol: {proxy_type}")

    stream_settings = build_tls_or_reality_settings(parsed)
    attach_transport_settings(stream_settings, parsed)
    outbound["streamSettings"] = stream_settings

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "protocol": "socks",
                "listen": LOCAL_HOST,
                "port": local_port,
                "settings": {"auth": "noauth", "udp": False},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        ],
        "outbounds": [
            outbound,
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "blocked"},
        ],
    }


def generate_ss_config(parsed: Dict[str, Any], local_port: int) -> Dict[str, Any]:
    return {
        "server": parsed["host"],
        "server_port": parsed["port"],
        "password": parsed["password"],
        "method": parsed["method"],
        "local_address": LOCAL_HOST,
        "local_port": local_port,
        "timeout": 10,
        "fast_open": False,
        "mode": "tcp_only",
    }


def short_proxy_id(proxy_url: str) -> str:
    return hashlib.sha1(proxy_url.encode("utf-8")).hexdigest()[:12]


async def wait_for_local_socks_ready(
    process: asyncio.subprocess.Process,
    host: str,
    port: int,
    timeout: float,
) -> Tuple[bool, str]:
    deadline = asyncio.get_running_loop().time() + timeout

    while asyncio.get_running_loop().time() < deadline:
        if process.returncode is not None:
            return False, f"client exited early with code {process.returncode}"

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=0.75,
            )
            writer.close()
            await writer.wait_closed()
            return True, ""
        except Exception:
            await asyncio.sleep(READINESS_CHECK_INTERVAL)

    return False, "local socks not ready in time"


async def run_http_test_through_socks(local_port: int, timeout: int) -> Tuple[bool, str]:
    connector = ProxyConnector.from_url(f"socks5://{LOCAL_HOST}:{local_port}")
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
        last_error = ""
        for url in TEST_URLS:
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    text = await resp.text()

                    if resp.status != 200:
                        last_error = f"{url} returned status {resp.status}"
                        continue

                    try:
                        data = json.loads(text)
                    except Exception:
                        data = None

                    if isinstance(data, dict) and any(k in data for k in EXPECTED_KEYS):
                        return True, f"ok via {url}"

                    if text.strip():
                        return True, f"ok via {url} (non-empty response)"

                    last_error = f"{url} empty response"
            except Exception as e:
                last_error = f"{url} error: {type(e).__name__}: {e}"

        return False, last_error or "all test urls failed"


async def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return

    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=2)
    except Exception:
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=2)
        except Exception:
            pass


def build_client(parsed: Dict[str, Any], local_port: int) -> Tuple[List[str], str]:
    proxy_type = parsed["type"]

    if proxy_type in {"vless", "vmess", "trojan"}:
        config = generate_xray_config(parsed, local_port)
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return ["xray", "run", "-c", f.name], f.name

    if proxy_type == "ss":
        config = generate_ss_config(parsed, local_port)
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return ["ss-local", "-c", f.name], f.name

    raise ValueError(f"unsupported proxy type: {proxy_type}")


async def run_client_and_test(
    client_cmd: List[str],
    local_port: int,
    timeout: int,
    log_file_path: str,
) -> Tuple[bool, str]:
    log_fh = open(log_file_path, "ab")

    try:
        process = await asyncio.create_subprocess_exec(
            *client_cmd,
            stdout=log_fh,
            stderr=log_fh,
        )
    except FileNotFoundError:
        log_fh.close()
        return False, f"binary not found: {client_cmd[0]}"
    except Exception as e:
        log_fh.close()
        return False, f"failed to start client: {type(e).__name__}: {e}"

    try:
        ready, reason = await wait_for_local_socks_ready(
            process,
            LOCAL_HOST,
            local_port,
            STARTUP_TIMEOUT,
        )
        if not ready:
            return False, reason

        ok, reason = await run_http_test_through_socks(local_port, timeout)
        return ok, reason
    finally:
        await terminate_process(process)
        log_fh.close()


async def test_proxy(
    idx: int,
    total: int,
    proxy_url: str,
    semaphore: asyncio.Semaphore,
    log_dir: str,
) -> TestResult:
    started = time.monotonic()

    async with semaphore:
        parsed = parse_proxy_url(proxy_url)
        if not parsed:
            return TestResult(
                proxy=proxy_url,
                ok=False,
                reason="parse_failed",
                elapsed=time.monotonic() - started,
            )

        proxy_type = parsed["type"]
        local_port = get_free_port()
        proxy_id = short_proxy_id(proxy_url)
        log_file = os.path.join(log_dir, f"{idx:05d}_{proxy_type}_{proxy_id}.log")

        logger.info(
            "[%d/%d] START type=%s port=%s proxy=%s",
            idx,
            total,
            proxy_type,
            local_port,
            proxy_url[:180],
        )

        try:
            client_cmd, config_file = build_client(parsed, local_port)
        except Exception as e:
            return TestResult(
                proxy=proxy_url,
                ok=False,
                reason=f"build_failed: {type(e).__name__}: {e}",
                proxy_type=proxy_type,
                local_port=local_port,
                elapsed=time.monotonic() - started,
                log_file=log_file,
            )

        try:
            try:
                ok, reason = await asyncio.wait_for(
                    run_client_and_test(client_cmd, local_port, TEST_TIMEOUT, log_file),
                    timeout=PER_PROXY_TIMEOUT,
                )
            except asyncio.TimeoutError:
                ok, reason = False, f"per_proxy_timeout>{PER_PROXY_TIMEOUT}s"

            elapsed = time.monotonic() - started

            logger.info(
                "[%d/%d] %s type=%s elapsed=%.2fs reason=%s",
                idx,
                total,
                "OK" if ok else "FAIL",
                proxy_type,
                elapsed,
                reason,
            )

            return TestResult(
                proxy=proxy_url,
                ok=ok,
                reason=reason,
                proxy_type=proxy_type,
                local_port=local_port,
                elapsed=elapsed,
                log_file=log_file,
            )
        finally:
            try:
                os.unlink(config_file)
            except Exception:
                pass


async def progress_reporter(
    total: int,
    stats: Dict[str, int],
    stop_event: asyncio.Event,
) -> None:
    last_done = -1

    while not stop_event.is_set():
        done = stats["done"]
        if done != last_done:
            logger.info(
                "PROGRESS done=%d/%d ok=%d fail=%d in_flight=%d",
                done,
                total,
                stats["ok"],
                stats["fail"],
                total - done,
            )
            last_done = done
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PROGRESS_INTERVAL)
        except asyncio.TimeoutError:
            continue


async def main(proxy_list: List[str], log_dir: str) -> List[TestResult]:
    os.makedirs(log_dir, exist_ok=True)

    semaphore = asyncio.Semaphore(CONCURRENT_TESTS)
    total = len(proxy_list)
    stats = {"done": 0, "ok": 0, "fail": 0}
    stop_event = asyncio.Event()

    progress_task = asyncio.create_task(progress_reporter(total, stats, stop_event))

    tasks = [
        asyncio.create_task(test_proxy(i + 1, total, proxy, semaphore, log_dir))
        for i, proxy in enumerate(proxy_list)
    ]

    results: List[TestResult] = []

    try:
        for fut in asyncio.as_completed(tasks):
            result = await fut
            results.append(result)
            stats["done"] += 1
            if result.ok:
                stats["ok"] += 1
            else:
                stats["fail"] += 1
    finally:
        stop_event.set()
        await progress_task

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test proxy functionality using local clients and HTTP requests through SOCKS."
    )
    parser.add_argument("-f", "--file", help="File containing proxy URLs, one per line.")
    parser.add_argument("--all", action="store_true", help="Print all results.")
    parser.add_argument("--log-dir", default="proxy_logs", help="Directory for per-proxy logs.")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            proxy_urls = [line.strip() for line in f if line.strip()]
    else:
        print("Enter proxy URLs (one per line, Ctrl+D to finish):", file=sys.stderr)
        proxy_urls = [line.strip() for line in sys.stdin if line.strip()]

    if not proxy_urls:
        print("No proxy URLs provided.", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "Testing %d proxies with concurrency=%d startup_timeout=%ss test_timeout=%ss per_proxy_timeout=%ss",
        len(proxy_urls),
        CONCURRENT_TESTS,
        STARTUP_TIMEOUT,
        TEST_TIMEOUT,
        PER_PROXY_TIMEOUT,
    )

    started = time.monotonic()
    results = asyncio.run(main(proxy_urls, args.log_dir))
    total_elapsed = time.monotonic() - started

    working = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    logger.info("FINISHED total=%d ok=%d fail=%d elapsed=%.2fs", len(results), len(working), len(failed), total_elapsed)

    fail_reasons = Counter(r.reason for r in failed)
    if fail_reasons:
        logger.info("Top failure reasons:")
        for reason, count in fail_reasons.most_common(15):
            logger.info("  %5d  %s", count, reason)

    if args.all:
        for r in results:
            status = "OK" if r.ok else "FAIL"
            print(f"[{status}] [{r.proxy_type}] {r.proxy}")
            print(f"  reason: {r.reason}")
            print(f"  elapsed: {r.elapsed:.2f}s")
            if r.log_file:
                print(f"  log_file: {r.log_file}")
    else:
        for r in working:
            print(r.proxy)
