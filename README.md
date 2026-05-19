# codex-telegram-tmux-gateway

A small Telegram gateway for controlling persistent Codex tmux sessions from Telegram without losing terminal context.

The gateway polls a Telegram bot, accepts messages only from an allow-listed chat ID, sends Telegram's `typing` indicator as soon as a message is accepted, and injects the message into a configured `tmux` pane as if you typed it in the Codex TUI. The default setup is a single bot/session pair; named instances let you run multiple isolated bots and Codex sessions side by side.

Created by F.B. "Rusty" Walker, IV and released as open source under the MIT License.

## Why This Exists

Codex is strongest when it is running where the work already lives: in a real terminal, inside the workspace, with the same context and tools you use at the keyboard. This project adds a small Telegram control surface to that local workflow, so you can keep operating terminal Codex sessions when you step away from the host machine.

Telegram is already a common control channel for remote agents, status updates, and quick approvals. This gateway lets Telegram participate in live Codex tmux sessions without turning your codebase, credentials, or terminal state over to a hosted runtime.

That means you can:

- start Codex locally in a terminal,
- walk away from the machine,
- send instructions from Telegram,
- receive final answers back in Telegram,
- keep the same Codex session and working directory,
- optionally run separate named bots for separate Codex sessions.

## Related Projects

This is not the only Telegram-to-Codex bridge. Other open-source projects take different approaches, including SDK-based sessions, Node.js runtimes, multi-agent orchestration, richer media handling, or dashboards.

This repo is intentionally focused:

- local Python with no third-party runtime dependencies,
- one owner chat allow-list per bot instance,
- one persistent `tmux` Codex pane per bot instance,
- named instances for running multiple isolated bots and Codex sessions,
- no exposed HTTP server,
- macOS LaunchAgent helpers for always-on local use,
- explicit support for Telegram permission buttons and Stark/YOLO/read-only launch modes.

The design goal is not to be a hosted agent framework. It is to remote-control real Terminal Codex sessions that are already running on your machine, in your real shell, with your real working directory and tmux continuity.

Other projects in this space include:

- CodexClaw: https://github.com/MackDing/CodexClaw
- HeyAgent: https://github.com/gergomiklos/heyagent
- TeleCodex: https://github.com/benedict2310/telecodex
- CCGram and similar tmux-based bridges discussed in the Codex community

## Features

- Telegram Bot API polling with no third-party Python dependencies.
- Per-instance owner chat allow-list via `TELEGRAM_OWNER_CHAT_ID`.
- `tmux` injection into persistent Codex panes.
- Named instance helper for one-bot-per-session operation.
- Configurable submit keystrokes for Codex TUI paste behavior.
- Message prefixing as `[Telegram] <message>` so Codex can route replies correctly.
- Telegram `typing` chat action on receipt.
- Typing keepalive while Codex is working, so Telegram does not look dropped.
- Telegram inline buttons for Codex permission prompts.
- Runtime modes: YOLO, Stark, read-only, or custom.
- Chunked Telegram replies under Telegram's message length limit.
- Local JSONL event log for troubleshooting.
- macOS LaunchAgent install/start/stop helpers.
- Queue mode for logging messages without injecting them.

## Requirements

- Python 3.10+.
- `tmux`.
- Codex CLI installed and available on `PATH`, or set `CODEX_BIN`.
- A Telegram bot token from BotFather.
- Your Telegram chat ID.

## Platform Support

The core gateway is portable anywhere Python 3, `tmux`, and the Codex CLI run:

- macOS: fully supported, including the included LaunchAgent start/stop helpers.
- Linux: the foreground gateway and tmux injection should work, but you will need to run it under your own process manager such as `systemd`, `supervisord`, or a shell/tmux session.
- Windows: not directly supported unless you are using a Unix-like environment with `tmux`, such as WSL.

The `start_codex_telegram_session.sh` convenience launcher is written for Unix-like shells. The macOS LaunchAgent pieces are macOS-only.

## Repository

GitHub: https://github.com/fbwalker4/codex-telegram-tmux-gateway

## Quick Start

### Simplest Operator Commands

After setup, use the helper command instead of remembering env vars:

```bash
./codex-telegram list
./codex-telegram restart tools
./codex-telegram status tools
./codex-telegram send tools "Tools instance is online."
```

Register a bot alias once:

```bash
./codex-telegram add tools --token '<tools-bot-token>' --chat-id '<your-chat-id>' --workdir "$HOME"
```

You can do this while another gateway is running. Starting a named instance does not stop other sessions because each instance has a separate tmux session and LaunchAgent label.

For normal use, prefer `restart NAME`. It stops only that named gateway, replaces only that named tmux session, seeds the Codex Telegram reply rule, skips stale queued Telegram updates, and starts polling again.

This writes ignored local files only:

```text
.env.codex-telegram-tools
codex_telegram_instances.json
```

### Let Codex Install It For You

If you already have Codex running on the machine where you want the gateway installed, you can give Codex this prompt:

```text
Install codex-telegram-tmux-gateway for me from:
https://github.com/fbwalker4/codex-telegram-tmux-gateway

Use the README. Do not create a new GitHub repository. Clone or update the existing package only. Set it up so Telegram messages go into a persistent Codex tmux session. Ask me for my Telegram bot token and owner chat ID if they are not already available. Keep secrets out of git. Use Stark mode by default. If I need multiple independent sessions, configure named instances with one bot per Codex session.
```

For multiple independent sessions, ask Codex to create named instances, one bot per session:

```text
Set up codex-telegram-tmux-gateway with separate named instances. Use one Telegram bot token per Codex tmux session. Keep each instance isolated with its own env file, state file, log, LaunchAgent, and tmux session. Do not create a new GitHub repository. Keep secrets out of git.
```

### Manual Install

1. Clone the repository.

```bash
git clone https://github.com/fbwalker4/codex-telegram-tmux-gateway.git
cd codex-telegram-tmux-gateway
```

2. Create a Telegram bot token.

- In Telegram, open the official `@BotFather`. Telegram documents BotFather as the tool for creating and managing bots: https://core.telegram.org/bots/features#botfather
- Send `/newbot`.
- Choose a display name.
- Choose a bot username ending in `bot`, such as `my_codex_gateway_bot`.
- Copy the token BotFather gives you.

Treat the token like a password. Anyone with that token can control your bot.

3. Start a chat with your new bot.

- Open the bot you just created.
- Send `/start`.
- Send one more short message, such as `hello`.

This creates an update that can be used to find your Telegram chat ID.

4. Find your Telegram chat ID.

Replace `<telegram-bot-token>` with the token from BotFather:

```bash
curl "https://api.telegram.org/bot<telegram-bot-token>/getUpdates"
```

Look for:

```json
"chat":{"id":123456789
```

That number is your `TELEGRAM_OWNER_CHAT_ID`.

5. Create your local env file.

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

Or initialize the env file with:

```bash
python3 COD_telegram_gateway.py init-env --token '<telegram-bot-token>' --chat-id '<your-chat-id>'
```

6. Start a persistent Codex tmux session and bind the gateway.

```bash
./start_codex_telegram_session.sh
```

For a named instance:

```bash
./start_codex_telegram_session.sh --instance tools
```

7. Send a Telegram message to your bot.

The gateway injects it into Codex as:

```text
[Telegram] your message here
```

8. Reply to Telegram from Codex with:

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

## Typing Keepalive

Telegram typing indicators expire after a few seconds. When a Telegram request is handed to Codex, the gateway refreshes `sendChatAction(action="typing")` until one of these happens:

- Codex sends a Telegram reply through `COD_telegram_gateway.py send`.
- The keepalive timeout expires.
- The gateway is stopped.

Defaults:

```text
COD_TELEGRAM_TYPING_KEEPALIVE_SECONDS=600
COD_TELEGRAM_TYPING_INTERVAL_SECONDS=4
```

Increase the timeout if your Codex tasks often run longer than ten minutes. Keep the interval near four seconds; Telegram clients do not display typing indefinitely from a single API call.

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

Permission buttons are disabled by default. Enable them only after confirming the key sequence matches your Codex TUI:

```text
COD_TELEGRAM_PERMISSION_BUTTONS=1
```

When enabled, if the gateway sees a real Codex permission prompt in the tmux pane, it sends a Telegram message with inline buttons:

- `Approve once`
- `Approve session`
- `Deny`

The gateway then sends configurable `tmux send-keys` tokens back to the Codex pane.

Defaults:

```text
COD_TELEGRAM_APPROVE_KEYS=C-m
COD_TELEGRAM_APPROVE_SESSION_KEYS=Down,C-m
COD_TELEGRAM_DENY_KEYS=Escape
COD_TELEGRAM_PERMISSION_BUTTONS=0
```

These defaults are deliberately configurable because terminal approval UIs can change. If your Codex prompt requires different keys, update `.env.codex-telegram`.

## Codex TUI Submit Keys

The gateway pastes Telegram text into the Codex TUI and then sends submit keys through tmux. The default is:

```text
COD_TELEGRAM_SUBMIT_KEYS=C-m,C-m
```

Two Enter keystrokes are intentional. Some Codex TUI paste states need the first Enter to finish the pasted input and the second to submit it. If your local Codex TUI submits with one Enter, set:

```text
COD_TELEGRAM_SUBMIT_KEYS=C-m
```

## Telegram Formatting

Telegram supports formatted bot messages through `parse_mode`, including `MarkdownV2` and `HTML`. This gateway supports both per message:

```bash
python3 COD_telegram_gateway.py send --parse-mode HTML '<b>Done</b>'
python3 COD_telegram_gateway.py send --parse-mode MarkdownV2 '*Done*'
./codex-telegram send tools --parse-mode HTML '<b>Done</b>'
./codex-telegram send tools --parse-mode MarkdownV2 '*Done*'
```

Leave `COD_TELEGRAM_PARSE_MODE` unset by default unless you have tested your formatting. Plain text is the safest global setting.

If you want formatted default replies, prefer HTML over MarkdownV2:

```text
COD_TELEGRAM_PARSE_MODE=HTML
```

HTML is usually less fragile for Codex replies because ordinary punctuation does not need the same broad escaping that MarkdownV2 requires. Escape literal `&`, `<`, and `>` as `&amp;`, `&lt;`, and `&gt;` when sending them as plain text in HTML mode.

MarkdownV2 is useful for deliberate one-off messages, but it is strict: characters such as `_`, `*`, `[`, `]`, `(`, `)`, `~`, backticks, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, and `!` must be escaped when they are meant as plain text. If Telegram rejects a formatted send because entities cannot be parsed, the gateway logs the error and retries the same text without `parse_mode`.

Telegram bot messages do not support arbitrary colored text. Use emoji, status symbols, custom emoji where available, or code/pre blocks for visual distinction.

Official reference: https://core.telegram.org/bots/api#formatting-options

## Multiple Bots Or Sessions

The default setup is a single bot/session pair: one bot token, one owner chat allow-list, and one Codex tmux target.

For multiple bots or sessions, use one named gateway instance per bot/session. Each named instance gets isolated local files, its own tmux session, and a separate LaunchAgent label.

Example:

```text
default -> .env.codex-telegram       -> codex:0.0       -> com.codex.COD_telegram_gateway
tools   -> .env.codex-telegram-tools -> codex-tools:0.0 -> com.codex.COD_telegram_gateway.tools
deploy  -> .env.codex-telegram-deploy -> codex-deploy:0.0 -> com.codex.COD_telegram_gateway.deploy
```

Create a separate bot token for each instance through BotFather, then initialize each instance:

```bash
./codex-telegram add tools --token '<tools-bot-token>' --chat-id '<your-chat-id>' --mode yolo --workdir "$HOME"
./codex-telegram add deploy --token '<deploy-bot-token>' --chat-id '<your-chat-id>' --mode stark --workdir "$HOME"
```

Restart each instance:

```bash
./codex-telegram restart tools
./codex-telegram restart deploy
```

`restart NAME` is the recommended daily-use command. It stops only that instance's LaunchAgent, kills only that instance's tmux session, boots a fresh Codex pane in the saved workdir and mode, seeds the Telegram reply rule, skips stale queued Telegram updates for that bot, and then starts polling.

`start NAME` reuses an existing tmux session when one already exists. That is useful when you intentionally want to preserve the current pane.

Advanced: start all saved instances at once:

```bash
./codex-telegram start-all
```

Check an instance:

```bash
./codex-telegram status tools
```

Send through an instance's bot:

```bash
./codex-telegram send tools "Tools instance is online."
```

Send one formatted message:

```bash
./codex-telegram send tools --parse-mode MarkdownV2 '*Tools instance is online*'
```

Each instance needs:

- its own Telegram bot token,
- its own owner chat ID,
- its own tmux target,
- its own env file,
- its own state file,
- its own event log,
- its own process manager or LaunchAgent label.

One bot per instance is the simplest model. A single bot routing multiple Codex sessions is possible, but it requires command or topic routing and more authorization logic.

If something feels stuck:

```bash
./codex-telegram status tools
./codex-telegram restart tools
tmux attach -t codex-tools
```

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

Before publishing your own fork publicly, run:

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

MIT License.

MIT is a good fit for this project because it is a small integration utility: it allows broad personal, commercial, and forked use while preserving the copyright notice and warranty disclaimer.
