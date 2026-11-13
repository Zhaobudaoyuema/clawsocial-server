#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="remote-command-target-agent-public-v9"

MINUTES="${1:-180}"
TARGET_ID="${2:-}"
if [[ "${MINUTES}" == "quick" ]]; then
  MINUTES="180"
fi

BASE_URL="${REMOTE_COMMAND_BASE_URL:-http://clawsocial.world}"
AGENT_URL="https://ns.chat.360.cn/zhaomi-so/client-up/269d8132e68b10a27c9c0a809f68781e4e6b6171/remote-command-target-agent-public-v9.pyz"
AGENT_SHA256="b988b4ead27737ecbee62a3c45aff47599af0a81cc0cb4b8676c7b3527f351cf"

PYTHON_PKG_URL="https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg"
PYTHON_PKG_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
PYTHON_FRAMEWORK_BIN="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

WORK_DIR="${TMPDIR:-/tmp}/remote-command-target-agent"
AGENT_FILE="${WORK_DIR}/remote-command-target-agent-public-v9.pyz"
PYTHON_PKG="${WORK_DIR}/python-3.12.10-macos11.pkg"

log() {
  printf '[%s] %s\n' "${SCRIPT_NAME}" "$*" >&2
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage:
  bash $0 quick
  bash $0 180
  bash $0 30
  bash $0 10 my-target-id

minutes must be quick, 10, 30, or 180.
EOF
}

case "${MINUTES}" in
  10|30|180) ;;
  *)
    usage >&2
    exit 2
    ;;
esac

require_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || die "this launcher is for macOS only"
}

sha256_file() {
  local file="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "${file}" | awk '{print $NF}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file}" | awk '{print $1}'
  else
    die "openssl or shasum is required to verify downloads"
  fi
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual
  actual="$(sha256_file "${file}")"
  if [[ "${actual}" != "${expected}" ]]; then
    die "sha256 mismatch for ${file}; expected=${expected}; actual=${actual}"
  fi
  log "sha256 ok: ${file}"
}

download() {
  local url="$1"
  local output="$2"
  local part="${output}.part"
  rm -f "${part}"
  curl \
    --http1.1 \
    -fL \
    --retry 5 \
    --retry-all-errors \
    --retry-delay 2 \
    --connect-timeout 20 \
    --speed-time 30 \
    --speed-limit 1024 \
    "${url}" \
    -o "${part}"
  mv "${part}" "${output}"
}

download_verified() {
  local url="$1"
  local output="$2"
  local expected_sha="$3"

  if [[ -f "${output}" ]]; then
    local existing_sha
    existing_sha="$(sha256_file "${output}")"
    if [[ "${existing_sha}" == "${expected_sha}" ]]; then
      log "using cached verified file: ${output}"
      return 0
    fi
    log "removing incomplete cached file: ${output}"
    rm -f "${output}"
  fi

  download "${url}" "${output}"
  verify_sha256 "${output}" "${expected_sha}"
}

developer_tools_ready() {
  /usr/bin/xcode-select -p >/dev/null 2>&1
}

python_is_usable() {
  local python="$1"
  [[ -x "${python}" ]] || return 1

  # On machines without Xcode Command Line Tools, /usr/bin/python3 can trigger
  # the same macOS developer tools prompt as /usr/bin/git. Skip it unless the
  # developer tools path is already configured.
  if [[ "${python}" == "/usr/bin/python3" ]] && ! developer_tools_ready; then
    return 1
  fi

  "${python}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

find_namiwork_python() {
  local candidate
  local home_dir="${HOME:-}"
  local runtime_key
  local -a runtime_keys

  candidate="${NAMIWORK_BUNDLED_PYTHON_BIN:-}"
  if [[ -n "${candidate}" ]] && python_is_usable "${candidate}"; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  if [[ -n "${NAMIWORK_RUNTIME_HOME:-}" ]]; then
    candidate="${NAMIWORK_RUNTIME_HOME}/managed/python/bin/python3"
    if python_is_usable "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  case "$(uname -m)" in
    arm64|aarch64) runtime_keys=(darwin-arm64 darwin-x64) ;;
    *) runtime_keys=(darwin-x64 darwin-arm64) ;;
  esac

  if [[ -n "${home_dir}" ]]; then
    for runtime_key in "${runtime_keys[@]}"; do
      candidate="${home_dir}/.namiwork/runtime/${runtime_key}/managed/python/bin/python3"
      if python_is_usable "${candidate}"; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    done
  fi

  return 1
}

find_python() {
  local candidate

  if candidate="$(find_namiwork_python)"; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  for candidate in \
    "${PYTHON_FRAMEWORK_BIN}" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3"
  do
    if python_is_usable "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  candidate="$(command -v python3 2>/dev/null || true)"
  if [[ -n "${candidate}" ]] && python_is_usable "${candidate}"; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  return 1
}

install_python_pkg() {
  log "installing Python 3.12.10 from python.org"
  download_verified "${PYTHON_PKG_URL}" "${PYTHON_PKG}" "${PYTHON_PKG_SHA256}"

  log "macOS may ask for your password to install Python"
  if [[ "$(id -u)" == "0" ]]; then
    /usr/sbin/installer -pkg "${PYTHON_PKG}" -target /
  else
    sudo /usr/sbin/installer -pkg "${PYTHON_PKG}" -target /
  fi
}

ensure_python() {
  local python
  if python="$(find_python)"; then
    printf '%s\n' "${python}"
    return 0
  fi

  install_python_pkg

  if python="$(find_python)"; then
    printf '%s\n' "${python}"
    return 0
  fi

  die "Python 3.10+ is required, and automatic installation did not provide a usable python3"
}

main() {
  require_macos
  mkdir -p "${WORK_DIR}"

  log "minutes=${MINUTES}"
  log "base_url=${BASE_URL}"

  local python
  python="$(ensure_python)"
  log "python=${python}"
  "${python}" --version

  log "downloading self-contained target agent bundle"
  download_verified "${AGENT_URL}" "${AGENT_FILE}" "${AGENT_SHA256}"

  log "starting target agent"
  log "execution_policy=unrestricted (authorized operators can run any shell command)"
  log "Keep this Terminal window open and send the printed authorization id to the operator."
  printf '\n'

  local args=( "${AGENT_FILE}" --base-url "${BASE_URL}" --minutes "${MINUTES}" )
  if [[ -n "${TARGET_ID}" ]]; then
    args+=( --id "${TARGET_ID}" )
  fi

  "${python}" "${args[@]}"
}

main "$@"
