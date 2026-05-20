---
name: telegram-reply
description: Use when a message is routed from Telegram, starts with [Telegram], or requires replying through the Codex Telegram Gateway. Ensures Codex sends user-facing answers through Telegram instead of only the terminal/final channel.
metadata:
  short-description: Reply through Telegram gateway
---

# Telegram Reply

When the user message is Telegram-routed, the user-facing answer must be sent through the gateway.

## Trigger

Use this skill when:

- the message starts with `[Telegram]`;
- the request says it came from Telegram;
- the conversation is about a Telegram-origin request;
- the user is waiting for the answer in Telegram.

## Required behavior

1. For quick acknowledgements (`heard`, `here`, `standing by`, `yes`, `done`), send the Telegram reply immediately. Do not inspect repos or run diagnostics first.
2. For longer tasks, send concise progress updates through Telegram while working.
3. Before ending the turn, send the final user-facing answer through Telegram.
4. Do not rely on the Codex final channel alone for Telegram-origin requests.
5. Keep replies concise unless the task requires detail.

## Commands

Preferred helper:

```bash
/Users/fbwalker4/projects/CodexTelegramGateway/tg-reply "Heard."
```

Explicit gateway command:

```bash
/opt/homebrew/bin/python3 /Users/fbwalker4/projects/CodexTelegramGateway/COD_telegram_gateway.py send --plain "Heard."
```

HTML formatting, when useful:

```bash
/Users/fbwalker4/projects/CodexTelegramGateway/tg-reply --html "<b>Done.</b> Checks passed."
```

## Final channel

After sending Telegram, a short final response in Codex is still acceptable, but it is secondary. Telegram is the source of truth for Telegram-origin requests.
