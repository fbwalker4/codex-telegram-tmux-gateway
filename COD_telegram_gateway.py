#!/usr/bin/env python3
"""Always-on Telegram gateway for a persistent Codex tmux session.

This daemon is intentionally conservative:
- allow-list one Telegram chat id
- writes durable local event/state files
- can either queue only or inject requests into an existing tmux Codex pane

Secrets are loaded from environment or .env.codex-telegram, which is ignored by
the repo's .env* rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


GATEWAY_ROOT = Path(__file__).resolve().parent
DEFAULT_CODEX_WORKDIR = Path.home()
ENV_PATH = Path(os.environ.get("CODEX_TELEGRAM_ENV", GATEWAY_ROOT / ".env.codex-telegram"))
STATE_PATH = GATEWAY_ROOT / "COD_gateway_state.json"
EVENTS_PATH = GATEWAY_ROOT / "COD_gateway_events.jsonl"
API = "https://api.telegram.org/bot{token}/{method}"
MAX_TG_LEN = 3900
DEFAULT_TMUX_TARGET = "codex:0.0"
DEFAULT_TMUX_REQUIRE_COMMAND = "codex"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / "com.codex.COD_telegram_gateway.plist"
APPROVAL_PROMPT_PATTERNS = (
    "approve once",
    "approve session",
    "allow command",
    "allow this command",
    "permission to run",
    "requires approval",
    "requires confirmation",
    "escalated permissions",
    "codex wants to run",
    "do you want to run",
    "would you like to run",
    "run this command?",
)


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def update_env_file(updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip().strip("'\"")
    existing.update(updates)
    ENV_PATH.write_text(
        "".join(f"{key}={value}\n" for key, value in existing.items()),
        encoding="utf-8",
    )
    os.chmod(ENV_PATH, 0o600)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(kind: str, data: dict[str, Any]) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": now_iso(), "kind": kind, **data}
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def redact_command(args: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    secret_markers = ("TOKEN", "SECRET", "KEY", "PASSWORD", "WHSEC", "SK_")
    for arg in args:
        upper = arg.upper()
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        if any(marker in upper for marker in secret_markers):
            redacted.append("[REDACTED]")
            if "=" not in arg:
                redact_next = True
            continue
        redacted.append(arg)
    return redacted


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing {name}. Put it in {ENV_PATH} or the process environment.")
    return value


def bot_token() -> str:
    return os.environ.get("CW_TELEGRAM_BOT_TOKEN") or require_env("TELEGRAM_BOT_TOKEN")


def owner_chat_id() -> str:
    return require_env("TELEGRAM_OWNER_CHAT_ID")


def api_call(method: str, params: dict[str, Any] | None = None, timeout: int = 90) -> dict[str, Any]:
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(API.format(token=bot_token(), method=method), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload


def send_message(text: str, chat_id: str | None = None, reply_markup: dict[str, Any] | None = None) -> None:
    target = chat_id or owner_chat_id()
    chunks = [text[i : i + MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)] or [""]
    for chunk in chunks:
        params: dict[str, Any] = {"chat_id": target, "text": chunk}
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)
        payload = api_call("sendMessage", params)
        result = payload.get("result", {})
        log_event(
            "outbound",
            {
                "chat_id": str(target),
                "message_id": result.get("message_id"),
                "chars": len(chunk),
                "preview": chunk[:160],
            },
        )


def send_chat_action(action: str = "typing", chat_id: str | None = None) -> None:
    target = chat_id or owner_chat_id()
    payload = api_call("sendChatAction", {"chat_id": target, "action": action}, timeout=10)
    if payload.get("ok"):
        log_event("chat_action", {"chat_id": str(target), "action": action})


def get_updates(timeout: int) -> list[dict[str, Any]]:
    state = read_state()
    params: dict[str, Any] = {
        "timeout": timeout,
        "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
    }
    if "offset" in state:
        params["offset"] = int(state["offset"])
    payload = api_call("getUpdates", params, timeout=timeout + 10)
    return payload.get("result", [])


def update_offset(update: dict[str, Any]) -> None:
    state = read_state()
    state["offset"] = int(update["update_id"]) + 1
    state["updated_at"] = now_iso()
    write_state(state)


def extract_callback(update: dict[str, Any]) -> dict[str, Any] | None:
    callback = update.get("callback_query")
    if not callback:
        return None
    sender = callback.get("from") or {}
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    return {
        "update_id": update.get("update_id"),
        "callback_query_id": callback.get("id"),
        "chat_id": str(chat.get("id", "")),
        "from_id": str(sender.get("id", "")),
        "from_name": " ".join(
            p for p in [sender.get("first_name", ""), sender.get("last_name", "")] if p
        ).strip(),
        "data": callback.get("data") or "",
        "message_id": message.get("message_id"),
    }


def extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    chat = msg.get("chat") or {}
    sender = msg.get("from") or {}
    text = msg.get("text") or msg.get("caption") or ""
    return {
        "update_id": update.get("update_id"),
        "message_id": msg.get("message_id"),
        "chat_id": str(chat.get("id", "")),
        "from_id": str(sender.get("id", "")),
        "from_name": " ".join(
            p for p in [sender.get("first_name", ""), sender.get("last_name", "")] if p
        ).strip(),
        "text": text,
    }


def build_codex_prompt(message: dict[str, Any]) -> str:
    return f"[Telegram] {message['text']}"


def tmux_target() -> str:
    return os.environ.get("COD_TELEGRAM_TMUX_TARGET", DEFAULT_TMUX_TARGET)


def tmux_require_command() -> str:
    return os.environ.get("COD_TELEGRAM_TMUX_REQUIRE_COMMAND", DEFAULT_TMUX_REQUIRE_COMMAND)


def run_tmux(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["tmux", *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )


def split_tmux_keys(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def current_tmux_target() -> str:
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        raise RuntimeError(
            "This terminal is not inside tmux, so the gateway cannot attach to this exact Codex session. "
            "Start Codex inside tmux first, then run this command from that Codex session."
        )
    proc = run_tmux(["display-message", "-p", "-t", pane, "#S:#I.#P"])
    if proc.returncode != 0:
        raise RuntimeError(f"Could not resolve current tmux pane: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def ensure_tmux_target(target: str) -> tuple[bool, str]:
    session = target.split(":", 1)[0]
    has_session = run_tmux(["has-session", "-t", session])
    if has_session.returncode != 0:
        return (
            False,
            f"Codex tmux session is not running. Start Codex first in tmux target `{target}`, "
            f"then resend the Telegram message.",
        )

    pane_check = run_tmux(["display-message", "-p", "-t", target, "#{pane_id} #{pane_current_command}"])
    if pane_check.returncode != 0:
        return (
            False,
            f"Codex tmux session exists, but target pane `{target}` was not found: "
            f"{pane_check.stderr.strip() or pane_check.stdout.strip()}",
        )

    require_command = tmux_require_command().strip()
    if require_command:
        current = pane_check.stdout.strip().split(" ", 1)[1] if " " in pane_check.stdout.strip() else ""
        if require_command.lower() not in current.lower():
            return (
                False,
                f"Target `{target}` is running `{current or 'unknown'}`, not Codex. "
                f"Start Codex in that pane or set COD_TELEGRAM_TMUX_REQUIRE_COMMAND= to disable this check.",
            )

    return True, ""


def capture_tmux_text(target: str, lines: int = 80) -> str:
    proc = run_tmux(["capture-pane", "-p", "-S", f"-{lines}", "-t", target])
    if proc.returncode != 0:
        raise RuntimeError(f"tmux capture-pane failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def approval_prompt_signature(text: str) -> str | None:
    tail = "\n".join(line.rstrip() for line in text.splitlines()[-30:])
    lowered = tail.lower()
    if not any(pattern in lowered for pattern in APPROVAL_PROMPT_PATTERNS):
        return None
    return hashlib.sha256(tail.encode("utf-8")).hexdigest()[:16]


def approval_keyboard(signature: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve once", "callback_data": f"perm:{signature}:approve"},
                {"text": "Deny", "callback_data": f"perm:{signature}:deny"},
            ],
            [
                {"text": "Approve session", "callback_data": f"perm:{signature}:approve_session"},
            ],
        ]
    }


def send_permission_prompt_if_needed(target: str | None = None, chat_id: str | None = None) -> None:
    target = target or tmux_target()
    state = read_state()
    pane_text = capture_tmux_text(target)
    signature = approval_prompt_signature(pane_text)
    if not signature:
        return

    pending = state.get("pending_permission") or {}
    if pending.get("signature") == signature:
        return

    state["pending_permission"] = {
        "signature": signature,
        "target": target,
        "status": "sent",
        "created_at": now_iso(),
    }
    write_state(state)
    preview = "\n".join(pane_text.splitlines()[-10:]).strip()
    send_message(
        "Codex is asking for permission.\n\n"
        "Review the terminal prompt before approving. Use Deny if you are unsure.\n\n"
        f"Prompt tail:\n{preview[-1200:]}",
        chat_id=chat_id,
        reply_markup=approval_keyboard(signature),
    )
    log_event("permission_prompt_sent", {"target": target, "signature": signature})


def inject_tmux_prompt(message: dict[str, Any]) -> str:
    target = tmux_target()
    ok, error = ensure_tmux_target(target)
    if not ok:
        raise RuntimeError(error)

    prompt = build_codex_prompt(message)
    buffer_name = f"codex_tg_{message['update_id']}"
    load = run_tmux(["load-buffer", "-b", buffer_name, "-"], input_text=prompt)
    if load.returncode != 0:
        raise RuntimeError(f"tmux load-buffer failed: {load.stderr.strip() or load.stdout.strip()}")

    paste = run_tmux(["paste-buffer", "-b", buffer_name, "-t", target])
    if paste.returncode != 0:
        run_tmux(["delete-buffer", "-b", buffer_name])
        raise RuntimeError(f"tmux paste-buffer failed: {paste.stderr.strip() or paste.stdout.strip()}")

    time.sleep(0.2)
    enter = run_tmux(["send-keys", "-t", target, "C-m"])
    run_tmux(["delete-buffer", "-b", buffer_name])
    if enter.returncode != 0:
        raise RuntimeError(f"tmux send-keys failed: {enter.stderr.strip() or enter.stdout.strip()}")

    log_event("tmux_injected", {"update_id": message["update_id"], "target": target, "chars": len(prompt)})
    time.sleep(0.8)
    try:
        send_permission_prompt_if_needed(target, message["chat_id"])
    except Exception as exc:
        log_event("permission_watch_error", {"target": target, "error": str(exc)})
    return f"Sent to Codex tmux target `{target}`."


def permission_key_sequence(action: str) -> list[str]:
    defaults = {
        "approve": "C-m",
        "approve_session": "Right,C-m",
        "deny": "Escape",
    }
    env_names = {
        "approve": "COD_TELEGRAM_APPROVE_KEYS",
        "approve_session": "COD_TELEGRAM_APPROVE_SESSION_KEYS",
        "deny": "COD_TELEGRAM_DENY_KEYS",
    }
    value = os.environ.get(env_names[action], defaults[action])
    return split_tmux_keys(value)


def answer_callback(callback_query_id: str, text: str, alert: bool = False) -> None:
    api_call(
        "answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text, "show_alert": "true" if alert else "false"},
        timeout=10,
    )


def handle_permission_callback(callback: dict[str, Any]) -> None:
    allowed = owner_chat_id()
    if callback["chat_id"] != allowed:
        log_event("ignored_callback", callback)
        answer_callback(callback["callback_query_id"], "Not authorized.", alert=True)
        return

    parts = callback["data"].split(":")
    if len(parts) != 3 or parts[0] != "perm":
        answer_callback(callback["callback_query_id"], "Unknown action.", alert=True)
        return

    _, signature, action = parts
    if action not in {"approve", "approve_session", "deny"}:
        answer_callback(callback["callback_query_id"], "Unknown permission action.", alert=True)
        return

    state = read_state()
    pending = state.get("pending_permission") or {}
    if pending.get("signature") != signature:
        answer_callback(callback["callback_query_id"], "That permission prompt is no longer current.", alert=True)
        return

    target = pending.get("target") or tmux_target()
    keys = permission_key_sequence(action)
    proc = run_tmux(["send-keys", "-t", target, *keys])
    if proc.returncode != 0:
        answer_callback(callback["callback_query_id"], "Could not send keys to tmux.", alert=True)
        raise RuntimeError(f"tmux permission send-keys failed: {proc.stderr.strip() or proc.stdout.strip()}")

    pending["status"] = action
    pending["resolved_at"] = now_iso()
    state["pending_permission"] = pending
    write_state(state)
    answer_callback(callback["callback_query_id"], f"Sent: {action.replace('_', ' ')}")
    send_message(f"Permission response sent to Codex: {action.replace('_', ' ')}", callback["chat_id"])
    log_event("permission_callback", {"target": target, "signature": signature, "action": action, "keys": keys})


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )


def install_launch_agent() -> None:
    python = sys.executable or "/usr/bin/python3"
    script = str(Path(__file__).resolve())
    workdir = str(GATEWAY_ROOT)
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.codex.COD_telegram_gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>{escape(python)}</string>
        <string>{escape(script)}</string>
        <string>run</string>
        <string>--mode</string>
        <string>tmux</string>
        <string>--timeout</string>
        <string>30</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{escape(workdir)}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{escape(path)}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/COD_telegram_gateway.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/COD_telegram_gateway.log</string>
</dict>
</plist>
"""
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT_PATH.write_text(plist, encoding="utf-8")


def start_gateway_for_current_pane() -> None:
    load_env_file()
    target = current_tmux_target()
    ok, error = ensure_tmux_target(target)
    if not ok:
        raise SystemExit(error)

    update_env_file(
        {
            "COD_TELEGRAM_TMUX_TARGET": target,
            "COD_TELEGRAM_TMUX_REQUIRE_COMMAND": tmux_require_command(),
        }
    )
    install_launch_agent()
    launchctl("unload", str(LAUNCH_AGENT_PATH))
    loaded = launchctl("load", str(LAUNCH_AGENT_PATH))
    if loaded.returncode != 0:
        raise SystemExit(f"launchctl load failed: {loaded.stderr.strip() or loaded.stdout.strip()}")
    log_event("gateway_bound", {"target": target})
    print(f"Telegram gateway is bound to this Codex tmux pane: {target}")


def stop_gateway() -> None:
    stopped = launchctl("unload", str(LAUNCH_AGENT_PATH))
    if stopped.returncode != 0 and "Could not find specified service" not in stopped.stderr:
        raise SystemExit(f"launchctl unload failed: {stopped.stderr.strip() or stopped.stdout.strip()}")
    log_event("gateway_stopped", {})
    print("Telegram gateway stopped.")


def gateway_status() -> None:
    load_env_file()
    print(f"target={tmux_target()}")
    ok, error = ensure_tmux_target(tmux_target())
    print(f"tmux_ready={ok}")
    if error:
        print(f"tmux_error={error}")
    listed = launchctl("list")
    line = ""
    for raw in listed.stdout.splitlines():
        if "com.codex.COD_telegram_gateway" in raw:
            line = raw
            break
    print(f"launch_agent={line or 'not loaded'}")


def handle_update(update: dict[str, Any], mode: str) -> None:
    callback = extract_callback(update)
    if callback:
        try:
            handle_permission_callback(callback)
        finally:
            update_offset(update)
        return

    message = extract_message(update)
    if not message:
        update_offset(update)
        return

    allowed = owner_chat_id()
    if message["chat_id"] != allowed:
        log_event("ignored_chat", message)
        update_offset(update)
        return

    log_event("inbound", message)

    text = message["text"].strip()
    if not text:
        send_message("Received an empty/non-text message. Text handling is wired first.", message["chat_id"])
        update_offset(update)
        return

    if text.startswith("/"):
        send_message("Received command. For now, send plain text instructions and I will queue or process them.", message["chat_id"])
        update_offset(update)
        return

    try:
        send_chat_action("typing", message["chat_id"])
    except Exception as exc:
        log_event("chat_action_error", {**message, "error": str(exc)})

    if mode == "queue":
        log_event("queued_only", message)
        update_offset(update)
        return

    try:
        if mode == "tmux":
            inject_tmux_prompt(message)
        else:
            raise RuntimeError(f"Unsupported gateway mode `{mode}`. Only `tmux` and `queue` are allowed.")
    except subprocess.TimeoutExpired:
        send_message("Codex runner timed out. The message is logged; I need to resume from the host session.", message["chat_id"])
        log_event("codex_timeout", message)
    except Exception as exc:
        send_message(f"Gateway received the message, but could not hand it to Codex: {exc}", message["chat_id"])
        log_event("codex_error", {**message, "error": str(exc)})
    finally:
        update_offset(update)


def loop(mode: str, timeout: int, once: bool) -> None:
    load_env_file()
    log_event("gateway_start", {"mode": mode, "once": once})
    while True:
        try:
            updates = get_updates(timeout)
            for update in updates:
                handle_update(update, mode)
            if mode == "tmux":
                try:
                    send_permission_prompt_if_needed()
                except Exception as exc:
                    log_event("permission_watch_error", {"target": tmux_target(), "error": str(exc)})
        except Exception as exc:
            log_event("loop_error", {"error": str(exc)})
            time.sleep(5)
        if once:
            break


def sync_offset() -> None:
    load_env_file()
    updates = get_updates(1)
    if updates:
        state = read_state()
        state["offset"] = max(int(u["update_id"]) for u in updates) + 1
        state["updated_at"] = now_iso()
        write_state(state)
        print(f"synced offset to {state['offset']} ({len(updates)} existing update(s) skipped)")
    else:
        print("no existing updates; offset unchanged")


def init_env(token: str, chat_id: str) -> None:
    ENV_PATH.write_text(
        f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_OWNER_CHAT_ID={chat_id}\n",
        encoding="utf-8",
    )
    os.chmod(ENV_PATH, 0o600)
    print(f"wrote {ENV_PATH} with mode 600")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-env")
    init.add_argument("--token", required=True)
    init.add_argument("--chat-id", required=True)

    send = sub.add_parser("send")
    send.add_argument("text")

    typing = sub.add_parser("typing")
    typing.add_argument("--action", default="typing")

    sub.add_parser("check-permission")

    sub.add_parser("sync-offset")
    sub.add_parser("start-gateway")
    sub.add_parser("stop-gateway")
    sub.add_parser("status")

    run = sub.add_parser("run")
    run.add_argument("--mode", choices=["queue", "tmux"], default="queue")
    run.add_argument("--timeout", type=int, default=30)
    run.add_argument("--once", action="store_true")

    args = parser.parse_args()
    if args.command == "init-env":
        init_env(args.token, args.chat_id)
    elif args.command == "send":
        load_env_file()
        send_message(args.text)
    elif args.command == "typing":
        load_env_file()
        send_chat_action(args.action)
    elif args.command == "check-permission":
        load_env_file()
        send_permission_prompt_if_needed()
    elif args.command == "sync-offset":
        sync_offset()
    elif args.command == "start-gateway":
        try:
            start_gateway_for_current_pane()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None
    elif args.command == "stop-gateway":
        stop_gateway()
    elif args.command == "status":
        gateway_status()
    elif args.command == "run":
        loop(args.mode, args.timeout, args.once)


if __name__ == "__main__":
    main()
