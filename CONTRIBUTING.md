# Contributing

Thanks for considering a contribution.

## Ground Rules

- Keep the gateway local-first and dependency-light.
- Do not add hosted services, web servers, or third-party runtime dependencies unless they are clearly optional.
- Keep secrets and local runtime files out of git.
- Prefer one-bot-per-session isolation over complex shared routing.
- Preserve macOS support, but keep Linux foreground/tmux use viable.

## Development Checks

Run:

```bash
make check
```

This runs Python syntax checks, shell syntax checks, unit tests, and whitespace checks.

If `make` is unavailable, run:

```bash
python3 -m py_compile COD_telegram_gateway.py COD_telegram_bridge.py
bash -n codex-telegram
bash -n start_codex_telegram_session.sh
python3 -m unittest discover -s tests
git diff --check
```

## Pull Requests

Include:

- what changed,
- how it was tested,
- whether the change affects local secrets, Telegram permissions, images, or tmux routing.

Avoid unrelated formatting churn.
