#!/usr/bin/env bash
# init.sh — идемпотентный bootstrap для нового VPN-сервера
# Создаёт каталоги, генерирует MTProto секрет, копирует .env.example → .env.
# Безопасно запускать повторно — уже созданные ресурсы пропускаются.
#
# Использование:
#   bash scripts/init.sh    # или: make init
set -euo pipefail

# Перейти в корень репо независимо от того, откуда запущен скрипт
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "===== VPN Node Agent — первый запуск ====="
echo ""

# ── 0. Проверить Docker ───────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "[ERR] Docker не найден. Установить:"
  echo "      curl -fsSL https://get.docker.com | sh"
  echo "      sudo usermod -aG docker \$USER && newgrp docker"
  exit 1
fi
echo "[OK]  Docker: $(docker --version | cut -d' ' -f3 | tr -d ',')"

# ── 1. Каталоги ──────────────────────────────────────────────────────────────
echo "[1/3] Создание каталогов..."
mkdir -p db cert config/mtg
echo "      db/  cert/  config/mtg/  — готово"

# ── 2. MTProto секрет ────────────────────────────────────────────────────────
echo "[2/3] MTProto конфиг..."
if [ ! -f config/mtg/config.toml ]; then
  echo "      Генерирую секрет (docker pull nineseconds/mtg:2)..."
  SECRET=$(docker run --rm nineseconds/mtg:2 generate-secret www.google.com)
  cat > config/mtg/config.toml <<EOF
secret = "$SECRET"
bind-to = "0.0.0.0:3128"
EOF
  echo "      config/mtg/config.toml создан"
  echo ""
  echo "      ━━━ MTProto секрет ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "      $SECRET"
  echo "      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "      (сохраните — повторно не отображается; файл: config/mtg/config.toml)"
  echo ""
else
  echo "      config/mtg/config.toml уже существует — пропускаю"
fi

# ── 3. .env ───────────────────────────────────────────────────────────────────
echo "[3/3] Файл .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "      .env создан из .env.example"
else
  echo "      .env уже существует — пропускаю"
fi

# ── Итог ─────────────────────────────────────────────────────────────────────
echo ""
echo "===== Готово. Следующие шаги: ====="
echo ""
echo "  1. Заполните .env (ОБЯЗАТЕЛЬНО перед первым запуском):"
echo "       nano .env"
echo "     Ключевые переменные:"
echo "       AGENT_SECRET   — сильный случайный секрет (openssl rand -hex 32)"
echo "       XUI_PASSWORD   — пароль панели 3x-ui"
echo "       MTG_SERVER_IP  — публичный IP этого сервера"
echo "       XUI_BASE_URL   — http://host.docker.internal:2053"
echo "                        (или с кастомным путём панели, если задан)"
echo ""
echo "  2. Поднимите стек:"
echo "       docker compose up -d"
echo "       # или: make up"
echo ""
echo "  3. Откройте панель 3x-ui в браузере:"
echo "       http://<YOUR_IP>:2053"
echo "     → Смените пароль по умолчанию"
echo "     → Создайте VLESS Reality inbound (порт 443, запомните inbound ID)"
echo "     → Укажите inbound ID в .env: XUI_VLESS_INBOUND_ID=<id>"
echo "     → docker compose restart node-agent  (или: make restart)"
echo ""
echo "  4. После настройки закройте внешний доступ к панели:"
echo "       ufw delete allow 2053/tcp"
echo ""
