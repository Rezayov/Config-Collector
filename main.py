import asyncio
import json
import logging
import sys
import argparse
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

from Checker import extract_and_append_unique_configs

logger = logging.getLogger("tg_config_collector")


# ----------------------------
# Logging
# ----------------------------
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


# ----------------------------
# Config
# ----------------------------
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
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    return start, end


# ----------------------------
# Message text extraction
# ----------------------------
def extract_text_with_urls(msg) -> str:
    base = msg.message or ""
    if msg.entities and msg.message:
        for ent in msg.entities:
            if isinstance(ent, MessageEntityTextUrl):
                base += f"\n{ent.url}"
            elif isinstance(ent, MessageEntityUrl):
                url = msg.message[ent.offset: ent.offset + ent.length]
                base += f"\n{url}"
    return base.strip()


# ----------------------------
# Dialog listing (debug tool)
# ----------------------------
async def list_dialogs(client: TelegramClient, limit: int = 50):
    # This is just for printing some dialogs, not for selection logic.
    dialogs = await client.get_dialogs(limit=limit)
    logger.info("=" * 80)
    logger.info("Dialogs (showing up to %d):", limit)
    logger.info("=" * 80)

    for i, d in enumerate(dialogs, 1):
        ent = d.entity
        name = getattr(ent, "title", None) or (
            (getattr(ent, "first_name", "") + " " + (getattr(ent, "last_name", "") or "")).strip()
        )
        dtype = "Channel/Group" if getattr(ent, "title", None) else "User"
        logger.info("%3d) %-14s | %-45s | dialog.id=%s | entity.id=%s", i, dtype, name[:45], d.id, getattr(ent, "id", None))


# ----------------------------
# Chat selection (NO LIMIT using iter_dialogs)
# ----------------------------
async def select_relevant_chats(
    client: TelegramClient,
    include_users: bool = False,
    keywords=None,
    max_chats: int = 0,              # 0 = no limit
    save_path: str = None            # None = do not save
):
    """
    Uses client.iter_dialogs() to traverse ALL dialogs (no hidden limit).
    - include_users=False => only channels/groups (anything with .title)
    - keywords list => if provided, keep only chats whose title matches any keyword
    - max_chats=0 => no limit
    """
    if keywords is None:
        keywords = [
            "v2ray", "proxy", "config", "vpn", "server",
            "vmess", "vless", "trojan", "shadowsocks",
            "mtproto", "outline", "network"
        ]

    chosen_ids = []
    matched = 0
    scanned = 0

    async for d in client.iter_dialogs():
        scanned += 1
        ent = d.entity
        title = getattr(ent, "title", None)

        # Decide whether to include this dialog:
        if title:
            # Channel/Group
            t = title.lower()
            ok = any(k in t for k in keywords) if keywords else True
        else:
            # User/private chat
            if not include_users:
                continue
            name = (getattr(ent, "first_name", "") + " " + (getattr(ent, "last_name", "") or "")).strip().lower()
            ok = any(k in name for k in keywords) if keywords else True

        if not ok:
            continue

        matched += 1
        chosen_ids.append(d.id)

        if max_chats and max_chats > 0 and len(chosen_ids) >= max_chats:
            break

    logger.info("Dialogs scanned=%d | matched=%d | selected=%d", scanned, matched, len(chosen_ids))

    if save_path:
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(chosen_ids, f, ensure_ascii=False, indent=2)
            logger.info("Saved selected chats to %s", save_path)
        except Exception as e:
            logger.warning("Could not save selected chats: %s", e)

    return chosen_ids


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


# ----------------------------
# Message collection (NO LIMIT, stop by time)
# ----------------------------
async def collect_messages_from_chat(
    client: TelegramClient,
    chat_id,
    start_utc: datetime,
    end_utc: datetime,
    debug_sample: bool = False,
):
    entity = await client.get_entity(chat_id)
    chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")

    collected = []

    try:
        # limit=None => NO LIMIT. We stop when msg_time < start_utc
        async for msg in client.iter_messages(entity, limit=None):
            if not msg.date:
                continue

            msg_time = msg.date  # UTC aware

            if debug_sample:
                logger.debug("DBG chat=%s msg_id=%s msg_time=%s", chat_name, msg.id, msg_time)

            # iter_messages goes from newest -> oldest
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
        # after sleeping, skip this chat to avoid loops; you can also retry if you want
        return [], chat_name


async def collect_messages(
    client: TelegramClient,
    chat_ids,
    start_utc: datetime,
    end_utc: datetime,
    delay_between_chats: float = 0.0,
    debug_sample: bool = False,
):
    all_msgs = []

    for i, chat_id in enumerate(chat_ids, 1):
        try:
            msgs, cname = await collect_messages_from_chat(
                client, chat_id, start_utc, end_utc, debug_sample=debug_sample
            )
            logger.info("Chat %d/%d: %s -> %d messages in range", i, len(chat_ids), cname, len(msgs))
            all_msgs.extend(msgs)

        except Exception as e:
            logger.error("Error collecting from chat_id=%s: %s", chat_id, e)

        if i < len(chat_ids) and delay_between_chats and delay_between_chats > 0:
            await asyncio.sleep(delay_between_chats)

    return all_msgs


# ----------------------------
# Output files
# ----------------------------
def write_raw_text(messages, raw_path="RawText.txt", report_path="Telegram_output.txt", dry_run=False):
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


# ----------------------------
# Auth
# ----------------------------
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


# ----------------------------
# Main
# ----------------------------
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

        # Decide chats list
        chat_ids = None

        # Cache behavior: default OFF unless --use-cache is set
        if args.use_cache:
            chat_ids = load_saved_chats(args.cache_file)

        if args.chat is not None:
            chat_ids = [args.chat]
            logger.info("Overriding chats: single chat_id=%s", args.chat)
        elif not chat_ids:
            # Select from ALL dialogs using iter_dialogs()
            chat_ids = await select_relevant_chats(
                client,
                include_users=args.include_users,
                keywords=None if args.no_keywords else None,  # keywords in function default; see below
                max_chats=args.max_chats,   # 0 => unlimited
                save_path=args.cache_file if args.save_cache else None
            )

        # 24h window
        start_utc, end_utc = get_last_24h_range_utc()
        logger.info("Collecting messages in last 24 hours (UTC):")
        logger.info("  start=%s", start_utc.isoformat())
        logger.info("  end  =%s", end_utc.isoformat())
        logger.info("Chats to check: %d", len(chat_ids))

        messages = await collect_messages(
            client,
            chat_ids,
            start_utc,
            end_utc,
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
    p = argparse.ArgumentParser(description="Telegram config collector (scan ALL dialogs + ALL msgs in last 24h).")
    p.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    p.add_argument("--list-dialogs", action="store_true", help="List some dialogs and exit.")
    p.add_argument("--dry-run", action="store_true", help="Do not write files and do not run checker.")
    p.add_argument("--chat", type=int, default=None, help="Test only one chat id (dialog.id).")

    # CHAT SELECTION
    p.add_argument("--max-chats", type=int, default=0,
                  help="Max chats to check. Use 0 for NO LIMIT (scan all matched chats).")
    p.add_argument("--include-users", action="store_true",
                  help="Also include private/user dialogs (default: only channels/groups).")
    p.add_argument("--no-keywords", action="store_true",
                  help="Do NOT filter by keywords; include all channels/groups (and users if --include-users).")

    # CACHE CONTROL (default OFF)
    p.add_argument("--use-cache", action="store_true",
                  help="Load chat_ids from cache file (selected_chats.json).")
    p.add_argument("--save-cache", action="store_true",
                  help="Save selected chat_ids to cache file.")
    p.add_argument("--cache-file", type=str, default="selected_chats.json",
                  help="Cache file path.")

    # PERFORMANCE / DEBUG
    p.add_argument("--delay", type=float, default=0.0, help="Delay between chats (seconds).")
    p.add_argument("--debug-sample", action="store_true",
                  help="Log each message timestamp during iteration (very verbose).")
    return p


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    setup_logging(args.debug)

    # If user wants "no keywords", override selector keywords to empty list by setting them to None and skipping filter.
    # Easiest: modify select_relevant_chats call logic:
    # We'll just monkey patch by using the flag below inside async_main:
    # (Implementation note: we keep keywords default inside function and handle no_keywords there.)

    # Patch: inject behavior into select_relevant_chats by wrapping it
    _orig_select = select_relevant_chats

    async def select_relevant_chats(client, include_users=False, keywords=None, max_chats=0, save_path=None):
        if args.no_keywords:
            # keywords=[] means accept all
            keywords = []
        else:
            # use defaults
            keywords = None
        return await _orig_select(client, include_users=include_users, keywords=keywords, max_chats=max_chats, save_path=save_path)

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
