#!/usr/bin/env bash
# 啟動本機 PanWatch（panwatch-tw，port 8000）：
#   1. Podman machine 沒跑就啟動，並等到 podman 連得上
#   2. 容器停止就 start；不存在就用既有 image 建立（不會重建 image）
#   3. 等 /api/version 回應後印出版本
set -euo pipefail

CONTAINER="${PANWATCH_CONTAINER:-panwatch-tw}"
IMAGE="${PANWATCH_IMAGE:-localhost/panwatch-tw:dev}"
VOLUME="${PANWATCH_VOLUME:-panwatch_tw_data}"
PORT="${PANWATCH_PORT:-8000}"
WAIT_SECONDS=90

log() { printf '[panwatch] %s\n' "$*"; }
die() { printf '[panwatch] 錯誤：%s\n' "$*" >&2; exit 1; }

command -v podman >/dev/null || die "找不到 podman"

ensure_machine() {
  local state
  state="$(podman machine inspect --format '{{.State}}' 2>/dev/null || true)"
  if [[ "$state" == "running" ]] && podman info >/dev/null 2>&1; then
    log "Podman machine 已在執行"
    return
  fi
  if [[ "$state" != "running" ]]; then
    log "啟動 Podman machine（目前狀態：${state:-未知}）…"
    podman machine start || die "podman machine start 失敗"
  fi
  for _ in $(seq 1 30); do
    podman info >/dev/null 2>&1 && { log "Podman 已可連線"; return; }
    sleep 1
  done
  die "Podman machine 已啟動但 30 秒內連不上 socket"
}

ensure_container() {
  local running
  if ! podman container exists "${CONTAINER}"; then
    podman image exists "${IMAGE}" || die "容器與 image（${IMAGE}）都不存在，請先依 status.md 的指令建置"
    log "容器 ${CONTAINER} 不存在，用 ${IMAGE} 建立…"
    podman run -d --name "${CONTAINER}" -p "${PORT}:8000" \
      -v "${VOLUME}:/app/data" -e PLAYWRIGHT_SKIP_BROWSER_INSTALL=1 "${IMAGE}" >/dev/null
    return
  fi
  running="$(podman inspect --format '{{.State.Running}}' "${CONTAINER}")"
  if [[ "$running" == "true" ]]; then
    log "容器 ${CONTAINER} 已在執行"
  else
    log "啟動容器 ${CONTAINER}…"
    podman start "${CONTAINER}" >/dev/null
  fi
}

wait_healthy() {
  local url="http://127.0.0.1:${PORT}/api/version" body
  log "等待 ${url} …"
  for _ in $(seq 1 "$WAIT_SECONDS"); do
    if body="$(curl -fsS --max-time 2 "${url}" 2>/dev/null)"; then
      log "已就緒：${body}"
      log "網址：http://localhost:${PORT}"
      return
    fi
    sleep 1
  done
  podman logs --tail 30 "${CONTAINER}" >&2 || true
  die "${WAIT_SECONDS} 秒內 /api/version 沒有回應（上方為容器最後 30 行 log）"
}

ensure_machine
ensure_container
wait_healthy
