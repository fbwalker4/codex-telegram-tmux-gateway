#!/usr/bin/env bash
set -euo pipefail

INSTANCE="${CODEX_TELEGRAM_INSTANCE:-}"
NO_ATTACH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance)
      INSTANCE="${2:?Missing value for --instance}"
      shift 2
      ;;
    --instance=*)
      INSTANCE="${1#--instance=}"
      shift
      ;;
    --no-attach)
      NO_ATTACH=1
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--instance NAME] [--no-attach]"
      echo
      echo "Default instance uses .env.codex-telegram and tmux session codex."
      echo "Named instances use .env.codex-telegram-NAME and tmux session codex-NAME."
      echo "--no-attach starts/binds the instance without attaching to tmux."
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--instance NAME] [--no-attach]" >&2
      exit 1
      ;;
  esac
done

if [[ -n "${INSTANCE}" && "${INSTANCE}" != "default" ]]; then
  INSTANCE="$(printf '%s' "${INSTANCE}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/-/g; s/^[-_]+//; s/[-_]+$//')"
  if [[ -z "${INSTANCE}" ]]; then
    echo "Invalid --instance value." >&2
    exit 1
  fi
  export CODEX_TELEGRAM_INSTANCE="${INSTANCE}"
else
  INSTANCE=""
  unset CODEX_TELEGRAM_INSTANCE
fi

if [[ -n "${INSTANCE}" ]]; then
  DEFAULT_SESSION="codex-${INSTANCE}"
else
  DEFAULT_SESSION="codex"
fi

SESSION="${COD_TELEGRAM_TMUX_SESSION:-${DEFAULT_SESSION}}"
WINDOW="${COD_TELEGRAM_TMUX_WINDOW:-0}"
PANE="${COD_TELEGRAM_TMUX_PANE:-0}"
TARGET="${SESSION}:${WINDOW}.${PANE}"
CODEX_BIN="${CODEX_BIN:-$(command -v codex || true)}"
CODEX_RUNTIME_MODE="${CODEX_TELEGRAM_CODEX_MODE:-stark}"
case "${CODEX_RUNTIME_MODE}" in
  yolo)
    CODEX_SANDBOX="${CODEX_SANDBOX:-danger-full-access}"
    CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-never}"
    ;;
  stark|strict)
    CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
    CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-on-request}"
    ;;
  readonly|read-only)
    CODEX_SANDBOX="${CODEX_SANDBOX:-read-only}"
    CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-on-request}"
    ;;
  custom)
    CODEX_SANDBOX="${CODEX_SANDBOX:?Set CODEX_SANDBOX for custom mode}"
    CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:?Set CODEX_APPROVAL_POLICY for custom mode}"
    ;;
  *)
    echo "Unknown CODEX_TELEGRAM_CODEX_MODE: ${CODEX_RUNTIME_MODE}" >&2
    echo "Use yolo, stark, read-only, or custom." >&2
    exit 1
    ;;
esac
CODEX_ARGS=(
  "--sandbox" "${CODEX_SANDBOX}"
  "--ask-for-approval" "${CODEX_APPROVAL_POLICY}"
)
GATEWAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY="${GATEWAY_DIR}/COD_telegram_gateway.py"
PYTHON="${PYTHON:-$(command -v python3 || true)}"
CREATED_SESSION=0

if [[ -z "${CODEX_BIN}" ]]; then
  echo "codex was not found. Set CODEX_BIN=/path/to/codex or add codex to PATH." >&2
  exit 1
fi

if [[ -z "${PYTHON}" ]]; then
  echo "python3 was not found. Set PYTHON=/path/to/python3 or add python3 to PATH." >&2
  exit 1
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required for shared terminal/Telegram Codex sessions." >&2
  exit 1
fi

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  (
    cd "${GATEWAY_DIR}"
    "${PYTHON}" - "${GATEWAY}" "${PWD}" "${CODEX_RUNTIME_MODE}" "${INSTANCE:-default}" "${CODEX_BIN}" "${CODEX_ARGS[@]}" <<'PY'
import importlib.util
import sys

gateway, cwd, runtime_mode, instance, *argv = sys.argv[1:]
spec = importlib.util.spec_from_file_location("gw", gateway)
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
gw.log_event("codex_command", {
    "cwd": cwd,
    "argv": gw.redact_command(argv),
    "runtime_mode": runtime_mode,
    "instance": instance,
    "launcher": "start_codex_telegram_session.sh",
})
PY
  )
  tmux new-session -d -s "${SESSION}" -c "${PWD}" "${CODEX_BIN}" "${CODEX_ARGS[@]}"
  CREATED_SESSION=1
fi

(
  cd "${GATEWAY_DIR}"
  "${PYTHON}" - <<PY
import importlib.util
spec = importlib.util.spec_from_file_location("gw", "${GATEWAY}")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
gw.load_env_file()
gw.update_env_file({
    "CODEX_TELEGRAM_INSTANCE": "${INSTANCE:-default}",
    "COD_TELEGRAM_TMUX_TARGET": "${TARGET}",
    "COD_TELEGRAM_TMUX_REQUIRE_COMMAND": "codex",
    "CODEX_TELEGRAM_CODEX_MODE": "${CODEX_RUNTIME_MODE}",
    "CODEX_SANDBOX": "${CODEX_SANDBOX}",
    "CODEX_APPROVAL_POLICY": "${CODEX_APPROVAL_POLICY}",
})
gw.install_launch_agent()
gw.launchctl("unload", str(gw.LAUNCH_AGENT_PATH))
loaded = gw.launchctl("load", str(gw.LAUNCH_AGENT_PATH))
if loaded.returncode != 0:
    raise SystemExit(loaded.stderr.strip() or loaded.stdout.strip())
gw.log_event("gateway_bound", {
    "target": "${TARGET}",
    "instance": "${INSTANCE:-default}",
    "launch_agent_label": gw.LAUNCH_AGENT_LABEL,
    "launcher": "start_codex_telegram_session.sh",
})
PY
)

if [[ "${CREATED_SESSION}" == "1" ]]; then
  reply_prefix=""
  if [[ -n "${INSTANCE}" ]]; then
    reply_prefix="CODEX_TELEGRAM_INSTANCE=${INSTANCE} "
  fi
  bootstrap_prompt="You are the Codex session for Telegram gateway instance '${INSTANCE:-default}'. Telegram messages arrive prefixed as [Telegram]. Treat the text after [Telegram] exactly like the user typed it in the TUI. For final answers to Telegram, run: ${reply_prefix}${PYTHON} ${GATEWAY} send \"<reply>\". Keep Telegram replies concise unless the task requires detail. Do not wait for terminal input when a Telegram message arrives."
  printf '%s' "${bootstrap_prompt}" | tmux load-buffer -b "codex_telegram_bootstrap_${SESSION}" -
  tmux paste-buffer -b "codex_telegram_bootstrap_${SESSION}" -t "${TARGET}"
  tmux send-keys -t "${TARGET}" C-m
  tmux delete-buffer -b "codex_telegram_bootstrap_${SESSION}"
fi

echo "Telegram gateway instance ${INSTANCE:-default} bound to tmux target ${TARGET}."
if [[ "${NO_ATTACH}" == "1" ]]; then
  echo "Running detached. Attach later with: tmux attach-session -t ${SESSION}"
  exit 0
fi
echo "Attach/detach normally; detach with Ctrl-b then d."
exec tmux attach-session -t "${SESSION}"
