import asyncio
import json
import logging
import sys
import argparse
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
from checker import extract_and_append_unique_configs

logger = logging.getLogger("tg_config_collector")

def setup_logging(debug: bool):
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    fh = logging.FileHandler("telegram_bot.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if debug else logging.INFO)
    sh.setFormatter(fmt)

    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)


def load_config(path="configuration.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        for k in ["API_ID", "API_HASH", "SESSION_NAME"]:
            if k not in cfg:
                raise KeyError(f"Missing {k} in {path}")

        return cfg
    except FileNotFoundError:
        logger.error("configuration.json not found.")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration.json: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return None

def get_last_24h_range_utc():
    """
    Return the last 24 hours window in UTC.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    return start, end


def extract_text_with_urls(msg) -> str:
    """
    Combine message text + embedded urls in entities.
    """
    base = msg.message or ""
    if msg.entities and msg.message:
        for ent in msg.entities:
            if isinstance(ent, MessageEntityTextUrl):
                base += f"\n{ent.url}"
            elif isinstance(ent, MessageEntityUrl):
                url = msg.message[ent.offset : ent.offset + ent.length]
                base += f"\n{url}"
    return base.strip()


async def list_dialogs(client: TelegramClient, limit: int = 50):
    dialogs = await client.get_dialogs(limit=limit)
    logger.info("=" * 80)
    logger.info("Dialogs (showing up to %d):", limit)
    logger.info("=" * 80)

    for i, d in enumerate(dialogs, 1):
        ent = d.entity
        name = getattr(ent, "title", None) or (getattr(ent, "first_name", "") + " " + (getattr(ent, "last_name", "") or "")).strip()
        dtype = "Channel/Group" if getattr(ent, "title", None) else "User"
        logger.info("%3d) %-14s | %-45s | dialog.id=%s | entity.id=%s", i, dtype, name[:45], d.id, getattr(ent, "id", None))


async def select_relevant_chats(client: TelegramClient, max_chats: int = 10, save_path="selected_chats.json"):
    """
    Select chats by keyword in chat title.
    Uses dialog.id (more reliable than entity.id).
    """
    keywords = [
        "v2ray", "proxy", "config", "vpn", "server",
        "vmess", "vless", "trojan", "shadowsocks",
        "mtproto", "outline", "network"
    ]

    dialogs = await client.get_dialogs()
    filtered = []

    for d in dialogs:
        ent = d.entity
        title = getattr(ent, "title", None)
        if title:
            t = title.lower()
            if any(k in t for k in keywords):
                filtered.append(d)

    if filtered:
        chosen = filtered[:max_chats]
        chat_ids = [d.id for d in chosen]
        logger.info("Selected %d keyword-related chats.", len(chat_ids))
    else:
        chosen = dialogs[:max_chats]
        chat_ids = [d.id for d in chosen]
        logger.info("No keyword-related chats found. Selected first %d dialogs.", len(chat_ids))

    try:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(chat_ids, f, ensure_ascii=False, indent=2)
        logger.info("Saved selected chats to %s", save_path)
    except Exception as e:
        logger.warning("Could not save selected chats: %s", e)

    return chat_ids


def load_saved_chats(path="selected_chats.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            chat_ids = json.load(f)
        if not isinstance(chat_ids, list):
            raise ValueError("selected_chats.json must be a list")
        return chat_ids
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("Failed to load saved chats: %s", e)
        return None

async def collect_messages_from_chat(
    client: TelegramClient,
    chat_id,
    start_utc: datetime,
    end_utc: datetime,
    per_chat_limit: int = 200,
    debug_sample: bool = False,
):
    entity = await client.get_entity(chat_id)
    chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")

    collected = []

    try:
        async for msg in client.iter_messages(entity, limit=per_chat_limit):
            if not msg.date:
                continue

            msg_time = msg.date 

            if debug_sample:
                logger.debug("DBG chat=%s msg_id=%s msg_time=%s", chat_name, msg.id, msg_time)

            if msg_time < start_utc:
                break

            if start_utc <= msg_time < end_utc:
                text = extract_text_with_urls(msg)
                if text:
                    collected.append({
                        "chat_id": chat_id,
                        "chat_name": chat_name,
                        "msg_id": msg.id,
                        "date_utc": msg_time.isoformat(),
                        "text": text
                    })

        return collected, chat_name

    except FloodWaitError as e:
        logger.warning("FloodWait %ss on chat=%s", e.seconds, chat_name)
        await asyncio.sleep(e.seconds)
        return [], chat_name


async def collect_messages(
    client: TelegramClient,
    chat_ids,
    start_utc: datetime,
    end_utc: datetime,
    per_chat_limit: int = 200,
    delay_between_chats: float = 1.5,
    debug_sample: bool = False,
):
    all_msgs = []
    for i, chat_id in enumerate(chat_ids, 1):
        try:
            msgs, cname = await collect_messages_from_chat(
                client, chat_id, start_utc, end_utc, per_chat_limit=per_chat_limit, debug_sample=debug_sample
            )
            if msgs:
                logger.info("Chat %d/%d: %s -> %d messages in range", i, len(chat_ids), cname, len(msgs))
                all_msgs.extend(msgs)
            else:
                logger.debug("Chat %d/%d: %s -> 0 in range", i, len(chat_ids), cname)

        except Exception as e:
            logger.error("Error collecting from chat_id=%s: %s", chat_id, e)

        if i < len(chat_ids):
            await asyncio.sleep(delay_between_chats)

    return all_msgs

def write_raw_text(messages, raw_path="RawText.txt", report_path="Telegram_output.txt", dry_run=False):
    """
    RawText: only message texts (for regex extraction)
    Telegram_output: readable report for debugging
    """
    if dry_run:
        logger.info("[DRY RUN] Skipping file writes.")
        return

    with open(raw_path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(m["text"])
            f.write("\n\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== Message Report ===\n")
        f.write(f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Messages: {len(messages)}\n")
        f.write("=" * 70 + "\n\n")
        for m in messages:
            f.write(f"Chat: {m['chat_name']} | chat_id={m['chat_id']}\n")
            f.write(f"Message ID: {m['msg_id']}\n")
            f.write(f"Date (UTC): {m['date_utc']}\n")
            f.write("Content:\n")
            f.write(m["text"] + "\n")
            f.write("=" * 70 + "\n\n")


async def ensure_login(client: TelegramClient):
    await client.connect()
    if not await client.is_user_authorized():
        phone = input("Enter phone with country code (e.g. +49...): ").strip()
        await client.send_code_request(phone)
        code = input("Enter the code you received: ").strip()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            pwd = input("Two-step verification enabled. Enter password: ")
            await client.sign_in(password=pwd)

    logger.info("Telegram connected & authorized.")


async def async_main(args):
    cfg = load_config()
    if not cfg:
        sys.exit(1)

    client = TelegramClient(cfg["SESSION_NAME"], cfg["API_ID"], cfg["API_HASH"])

    try:
        await ensure_login(client)

        if args.list_dialogs:
            await list_dialogs(client, limit=50)
            return

        chat_ids = None
        if not args.no_cache:
            chat_ids = load_saved_chats()

        if args.chat is not None:
            chat_ids = [args.chat]
            logger.info("Overriding chats: single chat_id=%s", args.chat)
        elif not chat_ids:
            chat_ids = await select_relevant_chats(client, max_chats=args.max_chats)

        # تغییر به ۲۴ ساعت اخیر
        start_utc, end_utc = get_last_24h_range_utc()
        logger.info("Collecting messages in last 24 hours (UTC):")
        logger.info("  start=%s", start_utc.isoformat())
        logger.info("  end  =%s", end_utc.isoformat())
        logger.info("Chats to check: %d", len(chat_ids))
        logger.debug("chat_ids=%s", chat_ids)

        messages = await collect_messages(
            client,
            chat_ids,
            start_utc,
            end_utc,
            per_chat_limit=args.per_chat_limit,
            delay_between_chats=args.delay,
            debug_sample=args.debug_sample
        )

        logger.info("Collected total %d messages in range.", len(messages))

        write_raw_text(messages, raw_path="RawText.txt", report_path="Telegram_output.txt", dry_run=args.dry_run)

        if args.dry_run:
            logger.info("[DRY RUN] Skipping checker.")
            return

        new_count, total = extract_and_append_unique_configs("RawText.txt", "Final_Configs.txt")
        logger.info("Checker done. New configs added=%d | Total unique=%d", new_count, total)

    finally:
        await client.disconnect()
        logger.info("Disconnected.")


def build_arg_parser():
    p = argparse.ArgumentParser(description="Telegram V2Ray config collector (debug-friendly).")
    p.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    p.add_argument("--list-dialogs", action="store_true", help="List dialogs and exit.")
    p.add_argument("--dry-run", action="store_true", help="Do not write files and do not run checker.")
    p.add_argument("--no-cache", action="store_true", help="Ignore selected_chats.json and re-select chats.")
    p.add_argument("--chat", type=int, default=None, help="Test only one chat id (dialog.id).")
    p.add_argument("--max-chats", type=int, default=10, help="Max chats to check.")
    p.add_argument("--per-chat-limit", type=int, default=200, help="Max messages pulled per chat.")
    p.add_argument("--delay", type=float, default=1.5, help="Delay between chats (seconds).")
    p.add_argument("--debug-sample", action="store_true", help="Log each message timestamp during iteration (very verbose).")
    return p


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    setup_logging(args.debug)

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
