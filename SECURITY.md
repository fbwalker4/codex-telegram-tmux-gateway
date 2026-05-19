# Security Policy

## Supported Use

This project is intended for single-owner or tightly controlled local use. A Telegram bot becomes a remote control path into the configured Codex tmux session, so treat it with the same care as SSH access to the host.

## Sensitive Data

Do not commit:

- Telegram bot tokens
- chat IDs tied to private deployments
- `.env*` files
- runtime state/log files
- downloaded Telegram images
- private operator notes

The included `.gitignore` excludes the normal local runtime files.

## Reporting Security Issues

For public forks, use private GitHub security reporting if enabled. If not, contact the repository owner privately before opening a public issue with exploit details.

## Operational Guidance

- Use one bot token per gateway instance.
- Keep `TELEGRAM_OWNER_CHAT_ID` restricted to your own chat.
- Prefer Stark mode for general use.
- Use YOLO mode only for sessions you fully trust.
- Leave permission buttons disabled until you confirm the key sequence matches your Codex TUI.
- Rotate the Telegram bot token immediately if it is exposed.
- Run `./codex-telegram cleanup <instance>` periodically if images may contain sensitive material.
