#!/usr/bin/env python3
"""Small Telegram Bot API bridge for Codex sessions.

No secrets are stored here. Provide TELEGRAM_BOT_TOKEN in the environment.
The update offset is stored under /private/tmp so polling does not dirty the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://api.telegram.org/bot{token}/{method}"
OFFSET_PATH = Path("/private/tmp/cw_codex_telegram_offset")


def token() -> str:
    value = os.environ.get("CW_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not value:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN first.")
    return value


def owner_chat_id() -> str:
    value = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not value:
        raise SystemExit("Set TELEGRAM_OWNER_CHAT_ID first.")
    return value


def api_call(method: str, params: dict[str, str | int] | None = None) -> dict:
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(API.format(token=token(), method=method), data=data)
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise SystemExit(json.dumps(payload, indent=2))
    return payload


def read_offset() -> int | None:
    try:
        text = OFFSET_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return int(text) if text else None


def write_offset(updates: list[dict]) -> None:
    if not updates:
        return
    OFFSET_PATH.write_text(str(max(u["update_id"] for u in updates) + 1), encoding="utf-8")


def format_update(update: dict) -> str:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = message.get("text") or message.get("caption") or ""
    name = " ".join(
        p for p in [sender.get("first_name", ""), sender.get("last_name", "")] if p
    ).strip()
    return (
        f"update_id={update.get('update_id')} "
        f"message_id={message.get('message_id')} "
        f"chat_id={chat.get('id')} from={name or sender.get('id')}: {text}"
    )


def poll_once(timeout: int, consume_existing: bool) -> list[dict]:
    params: dict[str, str | int] = {
        "timeout": timeout,
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }
    offset = read_offset()
    if offset is not None:
        params["offset"] = offset
    payload = api_call("getUpdates", params)
    updates = payload.get("result", [])
    if consume_existing:
        write_offset(updates)
    return updates


def cmd_send(args: argparse.Namespace) -> None:
    chat_id = args.chat_id or owner_chat_id()
    payload = api_call("sendMessage", {"chat_id": chat_id, "text": args.text})
    msg = payload["result"]
    print(f"sent message_id={msg['message_id']} chat_id={msg['chat']['id']}")


def cmd_poll(args: argparse.Namespace) -> None:
    updates = poll_once(args.timeout, consume_existing=not args.no_consume)
    if not updates:
        print("no updates")
        return
    for update in updates:
        print(format_update(update))


def cmd_listen(args: argparse.Namespace) -> None:
    print("listening; Ctrl-C to stop", flush=True)
    while True:
        for update in poll_once(args.timeout, consume_existing=True):
            print(format_update(update), flush=True)
        if args.interval:
            time.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send")
    send.add_argument("text")
    send.add_argument("--chat-id", default=None)
    send.set_defaults(func=cmd_send)

    poll = sub.add_parser("poll")
    poll.add_argument("--timeout", type=int, default=1)
    poll.add_argument("--no-consume", action="store_true")
    poll.set_defaults(func=cmd_poll)

    listen = sub.add_parser("listen")
    listen.add_argument("--timeout", type=int, default=30)
    listen.add_argument("--interval", type=float, default=0.0)
    listen.set_defaults(func=cmd_listen)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)


if __name__ == "__main__":
    main()
