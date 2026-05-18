# codex-telegram-tmux-gateway

A small Telegram gateway for controlling one persistent Codex session from Telegram without losing terminal context.

The gateway polls a Telegram bot, accepts messages only from one allow-listed chat ID, sends Telegram's `typing` indicator as soon as a message is accepted, and injects the message into an existing `tmux` pane as if you typed it in the Codex TUI.

## Why This Exists

Running a new `codex exec` process for every Telegram message loses conversational and terminal context. This project keeps one Codex process alive inside `tmux` and routes Telegram messages into that same pane.

That means you can:

- start Codex locally in a terminal,
- walk away from the machine,
- send instructions from Telegram,
- receive final answers back in Telegram,
- keep the same Codex session and working directory.

## Features

- Telegram Bot API polling with no third-party Python dependencies.
- Single-chat allow-list via `TELEGRAM_OWNER_CHAT_ID`.
- `tmux` injection into one persistent Codex pane.
- Message prefixing as `[Telegram] <message>` so Codex can route replies correctly.
- Telegram `typing` chat action on receipt.
- Telegram inline buttons for Codex permission prompts.
- Runtime modes: YOLO, Stark, read-only, or custom.
- Chunked Telegram replies under Telegram's message length limit.
- Local JSONL event log for troubleshooting.
- macOS LaunchAgent install/start/stop helpers.
- Queue mode for logging messages without injecting them.

## Requirements

- macOS for LaunchAgent management.
- Python 3.10+.
- `tmux`.
- Codex CLI installed and available on `PATH`, or set `CODEX_BIN`.
- A Telegram bot token from BotFather.
- Your Telegram chat ID.

## Repository Name

Recommended GitHub repository name:

`codex-telegram-tmux-gateway`

It is descriptive and discoverable: Codex + Telegram + tmux + gateway.

## Quick Start

1. Clone the repository.

```bash
git clone https://github.com/<you>/codex-telegram-tmux-gateway.git
cd codex-telegram-tmux-gateway
```

2. Create your local env file.

```bash
cp .env.example .env.codex-telegram
chmod 600 .env.codex-telegram
```

Edit `.env.codex-telegram`:

```text
TELEGRAM_BOT_TOKEN=123456789:your-bot-token
TELEGRAM_OWNER_CHAT_ID=123456789
COD_TELEGRAM_TMUX_TARGET=codex:0.0
COD_TELEGRAM_TMUX_REQUIRE_COMMAND=codex
CODEX_TELEGRAM_CODEX_MODE=stark
```

3. Start a persistent Codex tmux session and bind the gateway.

```bash
./start_codex_telegram_session.sh
```

4. Send a Telegram message to your bot.

The gateway injects it into Codex as:

```text
[Telegram] your message here
```

5. Reply to Telegram from Codex with:

```bash
python3 COD_telegram_gateway.py send "your reply"
```

## Commands

Initialize or update the local env file:

```bash
python3 COD_telegram_gateway.py init-env --token '<telegram-bot-token>' --chat-id '<your-chat-id>'
```

Start/refresh the LaunchAgent for the current tmux pane:

```bash
python3 COD_telegram_gateway.py start-gateway
```

Check status:

```bash
python3 COD_telegram_gateway.py status
```

Stop the LaunchAgent:

```bash
python3 COD_telegram_gateway.py stop-gateway
```

Send a Telegram message:

```bash
python3 COD_telegram_gateway.py send "Done."
```

Send a typing indicator manually:

```bash
python3 COD_telegram_gateway.py typing
```

Run the gateway in the foreground:

```bash
python3 COD_telegram_gateway.py run --mode tmux --timeout 30
```

Queue only, without injecting into tmux:

```bash
python3 COD_telegram_gateway.py run --mode queue --timeout 30
```

Check the current tmux pane for a permission prompt and send Telegram buttons if one is visible:

```bash
python3 COD_telegram_gateway.py check-permission
```

## Runtime Modes

`start_codex_telegram_session.sh` supports four runtime modes through `CODEX_TELEGRAM_CODEX_MODE`.
If unset, the launcher defaults to `stark`.

| Mode | Codex sandbox | Approval policy | Use when |
|---|---|---|---|
| `yolo` | `danger-full-access` | `never` | You fully trust the session and want no permission prompts. |
| `stark` | `workspace-write` | `on-request` | You want normal file edits, but risky actions should ask. |
| `read-only` | `read-only` | `on-request` | You want inspection/review by default. |
| `custom` | `CODEX_SANDBOX` | `CODEX_APPROVAL_POLICY` | You want explicit control. |

Example:

```bash
CODEX_TELEGRAM_CODEX_MODE=stark ./start_codex_telegram_session.sh
```

For custom mode:

```bash
CODEX_TELEGRAM_CODEX_MODE=custom \
CODEX_SANDBOX=workspace-write \
CODEX_APPROVAL_POLICY=on-request \
./start_codex_telegram_session.sh
```

## Telegram Permission Buttons

When the gateway sees text in the tmux pane that looks like a Codex permission prompt, it sends a Telegram message with inline buttons:

- `Approve once`
- `Approve session`
- `Deny`

The gateway then sends configurable `tmux send-keys` tokens back to the Codex pane.

Defaults:

```text
COD_TELEGRAM_APPROVE_KEYS=C-m
COD_TELEGRAM_APPROVE_SESSION_KEYS=Right,C-m
COD_TELEGRAM_DENY_KEYS=Escape
```

These defaults are deliberately configurable because terminal approval UIs can change. If your Codex prompt requires different keys, update `.env.codex-telegram`.

## Security Model

This is intentionally simple and conservative:

- Telegram bot token stays in `.env.codex-telegram` or the process environment.
- `.env*` is ignored by git.
- Only `TELEGRAM_OWNER_CHAT_ID` is accepted.
- Unknown chats are logged and ignored.
- The gateway does not expose an HTTP server.
- The gateway does not run arbitrary shell commands by itself; it only injects text into your existing Codex tmux pane.
- Permission buttons send configured keystrokes to the active tmux pane. Review the prompt tail in Telegram before approving.

You are still responsible for what your Codex session is allowed to do. If your Codex process has broad filesystem or deployment permissions, Telegram becomes a remote control path to that session. Protect your Telegram account and bot token accordingly.

## Files You Should Not Commit

The included `.gitignore` excludes:

- `.env.codex-telegram` and other `.env*` files,
- `COD_gateway_events.jsonl`,
- `COD_gateway_state.json`,
- Python caches,
- generated local LaunchAgent plist,
- private operator notes.

Before publishing publicly, run:

```bash
git status --short
rg -n "TOKEN|SECRET|PASSWORD|PRIVATE|TELEGRAM_BOT_TOKEN|chat_id" . -S
```

Do not commit real tokens, private Telegram logs, customer/project notes, or machine-specific operating instructions.

## How It Works

1. `COD_telegram_gateway.py run --mode tmux` polls Telegram with `getUpdates`.
2. A message from the allow-listed chat is logged locally.
3. The gateway sends `sendChatAction(action="typing")` to Telegram.
4. The gateway wraps the message as `[Telegram] <text>`.
5. It loads that text into a temporary tmux buffer.
6. It pastes the buffer into the configured tmux pane.
7. It sends Enter to the pane.
8. Codex processes the message normally in the existing TUI session.
9. Codex replies to Telegram by running `COD_telegram_gateway.py send`.

## Notes

Telegram typing indicators are temporary. Telegram clients usually display them for only a few seconds per `sendChatAction` call. For long-running work, call `python3 COD_telegram_gateway.py typing` periodically and send concise progress updates.

## License

Add a license before publishing. MIT is a reasonable default for this kind of utility.
