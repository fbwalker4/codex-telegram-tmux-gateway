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

GATEWAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${CODEX_TELEGRAM_ENV:-${GATEWAY_DIR}/.env.codex-telegram}"
if [[ -n "${INSTANCE}" ]]; then
  ENV_FILE="${CODEX_TELEGRAM_ENV:-${GATEWAY_DIR}/.env.codex-telegram-${INSTANCE}}"
fi

load_instance_env() {
  local env_file="$1"
  [[ -f "${env_file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" == *"="* ]] || continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(printf '%s' "${key}" | xargs)"
    [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!key+x}" ]]; then
      export "${key}=${value}"
    fi
  done < "${env_file}"
}

load_instance_env "${ENV_FILE}"

if [[ -n "${INSTANCE}" ]]; then
  DEFAULT_SESSION="codex-${INSTANCE}"
else
  DEFAULT_SESSION="codex"
fi

SESSION="${COD_TELEGRAM_TMUX_SESSION:-${DEFAULT_SESSION}}"
WINDOW="${COD_TELEGRAM_TMUX_WINDOW:-0}"
PANE="${COD_TELEGRAM_TMUX_PANE:-0}"
TARGET="${SESSION}:${WINDOW}.${PANE}"
CODEX_WORKDIR="${CODEX_TELEGRAM_CODEX_WORKDIR:-${PWD}}"
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
GATEWAY="${GATEWAY_DIR}/COD_telegram_gateway.py"
PYTHON="${PYTHON:-$(command -v python3 || true)}"
CREATED_SESSION=0

capture_target() {
  tmux capture-pane -p -S -80 -t "${TARGET}" 2>/dev/null || true
}

wait_for_pane_text() {
  local pattern="$1"
  local timeout="${2:-30}"
  local end=$((SECONDS + timeout))
  while (( SECONDS < end )); do
    if capture_target | grep -Fqi -- "${pattern}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_codex_ready() {
  local timeout="${1:-60}"
  local end=$((SECONDS + timeout))
  while (( SECONDS < end )); do
    local pane
    pane="$(capture_target)"
    if printf '%s' "${pane}" | grep -Fq "Do you trust the contents of this directory?"; then
      tmux send-keys -t "${TARGET}" C-m
      sleep 2
      continue
    fi
    if printf '%s' "${pane}" | grep -Fq "› "; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_codex_idle() {
  local timeout="${1:-90}"
  local end=$((SECONDS + timeout))
  while (( SECONDS < end )); do
    local pane
    pane="$(capture_target)"
    if ! printf '%s' "${pane}" | grep -Fq "• Working ("; then
      return 0
    fi
    sleep 2
  done
  return 1
}

send_submit_keys() {
  local keys="${COD_TELEGRAM_SUBMIT_KEYS:-C-m,C-m}"
  local key
  local old_ifs="${IFS}"
  IFS=','
  for key in ${keys}; do
    key="$(printf '%s' "${key}" | xargs)"
    [[ -z "${key}" ]] && continue
    tmux send-keys -t "${TARGET}" "${key}"
    sleep 0.15
  done
  IFS="${old_ifs}"
}

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

if [[ ! -d "${CODEX_WORKDIR}" ]]; then
  echo "Configured Codex workdir does not exist: ${CODEX_WORKDIR}" >&2
  exit 1
fi

(
  cd "${GATEWAY_DIR}"
  "${PYTHON}" - <<PY
import importlib.util
spec = importlib.util.spec_from_file_location("gw", "${GATEWAY}")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
gw.load_env_file()
gw.launchctl("unload", str(gw.LAUNCH_AGENT_PATH))
PY
) >/dev/null 2>&1 || true

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  (
    cd "${GATEWAY_DIR}"
    "${PYTHON}" - "${GATEWAY}" "${CODEX_WORKDIR}" "${CODEX_RUNTIME_MODE}" "${INSTANCE:-default}" "${CODEX_BIN}" "${CODEX_ARGS[@]}" <<'PY'
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
  tmux new-session -d -s "${SESSION}" -c "${CODEX_WORKDIR}" "${CODEX_BIN}" "${CODEX_ARGS[@]}"
  CREATED_SESSION=1
fi

if [[ "${CREATED_SESSION}" == "1" ]]; then
  if ! wait_for_codex_ready 90; then
    echo "Codex session ${SESSION} did not become ready in time." >&2
    exit 1
  fi

  reply_prefix=""
  if [[ -n "${INSTANCE}" ]]; then
    reply_prefix="CODEX_TELEGRAM_INSTANCE=${INSTANCE} "
  fi
  bootstrap_prompt="You are the Codex session for Telegram gateway instance '${INSTANCE:-default}'. Telegram messages arrive prefixed as [Telegram]. Treat the text after [Telegram] exactly like the user typed it in the TUI. For final answers to Telegram, run: ${reply_prefix}${PYTHON} ${GATEWAY} send \"<reply>\". Keep Telegram replies concise unless the task requires detail. Do not wait for terminal input when a Telegram message arrives."
  printf '%s' "${bootstrap_prompt}" | tmux load-buffer -b "codex_telegram_bootstrap_${SESSION}" -
  tmux paste-buffer -b "codex_telegram_bootstrap_${SESSION}" -t "${TARGET}"
  send_submit_keys
  tmux delete-buffer -b "codex_telegram_bootstrap_${SESSION}"
  wait_for_codex_idle 120 || true
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
    "CODEX_TELEGRAM_CODEX_WORKDIR": "${CODEX_WORKDIR}",
    "COD_TELEGRAM_TMUX_TARGET": "${TARGET}",
    "COD_TELEGRAM_TMUX_REQUIRE_COMMAND": "codex",
    "CODEX_TELEGRAM_CODEX_MODE": "${CODEX_RUNTIME_MODE}",
    "CODEX_SANDBOX": "${CODEX_SANDBOX}",
    "CODEX_APPROVAL_POLICY": "${CODEX_APPROVAL_POLICY}",
})
if "${COD_TELEGRAM_SYNC_OFFSET_ON_START:-1}" == "1":
    gw.sync_offset()
gw.install_launch_agent()
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

echo "Telegram gateway instance ${INSTANCE:-default} bound to tmux target ${TARGET}."
if [[ "${NO_ATTACH}" == "1" ]]; then
  echo "Running detached. Attach later with: tmux attach-session -t ${SESSION}"
  exit 0
fi
echo "Attach/detach normally; detach with Ctrl-b then d."
exec tmux attach-session -t "${SESSION}"
