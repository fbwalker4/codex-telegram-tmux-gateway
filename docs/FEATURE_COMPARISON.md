# Feature Comparison

This comparison is for positioning, not a claim that one project is universally better. These tools make different architecture choices.

## Summary

`codex-telegram-tmux-gateway` is strongest when you want a small, local, no-server Telegram remote control for real Codex TUI sessions already running in tmux.

Other tools tend to be broader agent platforms. They may offer streaming output, provider switching, voice transcription, dashboards, topic routing, container orchestration, SDK-managed sessions, richer artifact workflows, or multi-user flows.

## Our Gateway

Strengths:

- Local Python implementation with no third-party runtime dependencies.
- No exposed HTTP server for normal operation.
- Uses tmux as the durable source of truth.
- One bot token per Codex session keeps routing simple.
- Named instances support multiple isolated bots/sessions.
- Works with the real Codex TUI, not a separate hosted runtime.
- Supports text in/out.
- Supports image in/out.
- Sends Telegram typing keepalive while Codex is working.
- Has opt-in permission buttons.
- Has explicit Stark, YOLO, read-only, and custom launch modes.
- Uses ignored local state/log/download files.

Tradeoffs:

- No streaming token-by-token response rendering.
- No dashboard.
- No voice transcription.
- No Telegram topic router.
- No multi-provider switching.
- No SDK-managed Codex thread browser.
- No packaged installer yet.
- Tests are lightweight and focused on helper behavior.

## TeleCodex

Public docs describe TeleCodex as a Telegram bridge for the OpenAI Codex CLI SDK.

Things TeleCodex appears to do that this gateway does not center:

- SDK-managed Codex sessions.
- Per-context sessions by Telegram chat or forum topic.
- Streaming responses and tool output.
- Live plan display.
- Voice/audio transcription.
- Document/file ingest and generated artifact delivery.
- Hand-off between Telegram and CLI session modes.

Where our gateway is different:

- It stays closer to the Terminal Codex TUI and tmux.
- It avoids an SDK session layer.
- It is smaller operationally and easier to inspect.

## HeyAgent

Public docs describe HeyAgent as a Telegram bridge for Claude Code and Codex CLI.

Things HeyAgent appears to do that this gateway does not center:

- Provider switching between Claude and Codex.
- Guided QR/phone setup flow.
- Session commands such as new/resume/status/reset.
- Local pairing flow with optional Cloudflare Quick Tunnel.
- Interactive local CLI input alongside Telegram.

Where our gateway is different:

- It is one-purpose: Telegram control of local Codex tmux sessions.
- It avoids pairing servers/tunnels in normal use.
- It uses one bot per session rather than provider/session switching.

## CCGram-Style Tmux Bridges

Public docs and posts describe CCGram-style tools as Telegram-to-terminal bridges for Claude Code, Codex, Gemini, and shell sessions.

Things CCGram-style tools often do that this gateway does not center:

- Universal terminal/session discovery.
- Telegram topic to tmux-window routing.
- Multi-agent/provider control from one bot.
- Rich permission/question handling.
- Shell session control beyond Codex.
- Natural-language-to-command or remote-control extras in some versions.

Where our gateway is different:

- It deliberately avoids general shell remote-control scope.
- It keeps authorization/routing simple.
- It is optimized for private owner-operated Codex sessions.

## CodexClaw / OpenClaw-Style Systems

Public descriptions position these as broader remote coding or agent control systems.

Things they may do that this gateway does not center:

- Subagent orchestration.
- GitHub/MCP skill integration.
- Scheduled automation.
- Backend selection between SDK and CLI sessions.
- Broader agent control plane behavior.

Where our gateway is different:

- It is not an agent platform.
- It does not try to orchestrate background work.
- It focuses on reliable Telegram access to existing terminal Codex sessions.

## Should We Promote It?

Promote it if the message is:

> A small, local, inspectable Telegram gateway for controlling persistent Codex tmux sessions, with text/image in and out, typing keepalive, simple named multi-bot sessions, and no hosted control plane.

Do not promote it as:

- a full agent dashboard,
- a multi-user system,
- a voice/file/artifact automation suite,
- a hosted OpenClaw replacement,
- a streaming Codex SDK client.

The project is useful and coherent because it is intentionally narrow.
