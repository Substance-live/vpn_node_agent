# Деплой VPN Node Agent

Два сценария в зависимости от состояния сервера.

---

## Сценарий A — Чистый сервер (полный стек с нуля)

Поднимает 3x-ui + mtproto-proxy + node-agent одной командой.

```bash
# 1. Установить Docker (если нет)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Клонировать репозиторий
git clone <REPO_URL> /opt/vpn-node
cd /opt/vpn-node

# 3. Bootstrap: каталоги + MTG секрет + .env из примера
bash scripts/init.sh
# (или: make init)

# 4. Заполнить .env
nano .env
```

Обязательные переменные в `.env`:

| Переменная | Пример | Описание |
|------------|--------|----------|
| `AGENT_SECRET` | `$(openssl rand -hex 32)` | Секрет для Orchestrator |
| `XUI_PASSWORD` | `your-panel-password` | Пароль 3x-ui панели |
| `MTG_SERVER_IP` | `1.2.3.4` | Публичный IP сервера |
| `XUI_BASE_URL` | `http://host.docker.internal:2053` | URL панели изнутри Docker |

```bash
# 5. Поднять весь стек
docker compose up -d
# (или: make up)

# 6. Открыть панель 3x-ui
#    http://<YOUR_IP>:2053
#    → Сменить пароль по умолчанию
#    → Создать VLESS Reality inbound:
#       - Protocol: VLESS, Port: 443, Network: TCP
#       - Security: Reality
#       - Dest (SNI): microsoft.com:443 (или другой белый домен)
#       - Запомнить inbound ID (обычно 1)
#    → Указать реальный публичный IP в поле «Listen IP» inbound'а
#      (иначе vless:// ссылки будут без IP — см. раздел «Проблемы»)
#    → Прописать inbound ID в .env: XUI_VLESS_INBOUND_ID=<id>
#    → Перезапустить node-agent: docker compose restart node-agent

# 7. Закрыть внешний доступ к панели после настройки
sudo ufw delete allow 2053/tcp
```

---

## Сценарий B — Сервер с уже работающими 3x-ui и mtproto

> **Это твой случай**: 3x-ui и mtproto-proxy уже запущены на хосте или отдельными
> контейнерами. `docker compose up -d` (полный стек) вызовет конфликт имён контейнеров
> и портов. Поднимаем **только node-agent**.

```bash
# 1. Клонировать репозиторий
git clone <REPO_URL> /opt/vpn-node
cd /opt/vpn-node

# 2. Создать .env вручную (НЕ запускать make init — не нужно генерировать MTG секрет)
cp .env.example .env
nano .env
```

Переменные для Сценария B (все обязательны):

```bash
# Секрет для Orchestrator (сгенерировать)
AGENT_SECRET=$(openssl rand -hex 32)
echo "AGENT_SECRET=$AGENT_SECRET" >> .env

# Панель 3x-ui (подключение изнутри Docker через host.docker.internal)
# Если панель запущена на стандартном порту 2053:
XUI_BASE_URL=http://host.docker.internal:2053
# Если у панели кастомный порт и/или base path (пример):
# XUI_BASE_URL=http://host.docker.internal:13371/fast_speed

XUI_USERNAME=admin          # ваш логин в 3x-ui
XUI_PASSWORD=<пароль>       # ваш пароль в 3x-ui
XUI_VLESS_INBOUND_ID=1      # ID inbound'а VLESS Reality в 3x-ui

# MTProto (публичный IP и порт mtproto-proxy)
MTG_SERVER_IP=<публичный IP сервера>
MTG_PORT=2443

# ВАЖНО: читаем СУЩЕСТВУЮЩИЙ секрет mtg, не генерируем новый
# (иначе tg-ссылка не совпадёт с работающим прокси)
MTG_CONFIG_HOST_PATH=/etc/mtg/config.toml

PORT=8080
LOG_LEVEL=INFO
LOG_FORMAT=json
```

```bash
# 3. Поднять ТОЛЬКО node-agent (--no-deps пропускает depends_on: 3x-ui/mtproto)
docker compose up -d --no-deps --build node-agent

# 4. Проверить, что контейнер запустился
docker ps
# node-agent    Up N seconds (health: starting)
```

---

## nginx + TLS (общий для обоих сценариев)

```bash
# Установить nginx (если нет)
sudo apt install -y nginx

# Создать самоподписанный сертификат (быстрый старт)
# Для прода заменить на certbot (см. ниже)
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/node-agent.key \
  -out    /etc/nginx/ssl/node-agent.crt \
  -subj "/CN=$(curl -s ifconfig.me)"

# Скопировать конфиг из репо
sudo cp nginx/node-agent.conf /etc/nginx/sites-available/node-agent
sudo ln -sf /etc/nginx/sites-available/node-agent /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default    # убрать дефолтный конфиг если мешает

# Проверить и перезагрузить nginx
sudo nginx -t && sudo systemctl reload nginx

# Открыть порт 8443 (node-agent API)
sudo ufw allow 8443/tcp
# Порт 8080 наружу НЕ открывать — compose бинд только 127.0.0.1:8080

# Проверить через nginx
curl -k https://127.0.0.1:8443/api/v1/health
```

### Ограничить доступ по IP Orchestrator'а

После проверки раскомментировать в `/etc/nginx/sites-available/node-agent`:
```nginx
    allow <ORCHESTRATOR_IP>;
    deny all;
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Certbot (Let's Encrypt) — для прода

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
# Certbot обновит /etc/nginx/sites-available/node-agent автоматически
```

---

## Финальный smoke-test

Через Swagger UI (`https://<IP>:8443/docs` или `-k` для self-signed):

```bash
SERVER=<IP>
SECRET=<AGENT_SECRET из .env>
H="X-Agent-Secret: $SECRET"

# 1. Health — все бэкенды "ok" (vless_backend/mtproto_backend)
curl -sk -H "$H" https://$SERVER:8443/api/v1/health | python3 -m json.tool

# 2. MTProto info — получить tg-ссылку, проверить в Telegram
curl -sk -H "$H" https://$SERVER:8443/api/v1/mtproto/info | python3 -m json.tool
# → tg_link: "tg://proxy?server=IP&port=2443&secret=..."
# Вставить в Telegram (Settings → Data & Storage → Proxy) и проверить что работает

# 3. VLESS CRUD
# Создать пользователя (ответ → config_link)
curl -sk -X POST https://$SERVER:8443/api/v1/vless/users \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"external_id":"test-user-1","expire_days":30}' | python3 -m json.tool
# → config_link: "vless://UUID@IP:443?..."  ← вставить в VPN-клиент, убедиться что работает

# Получить статистику (должны появиться traffic_up/down_bytes после использования)
curl -sk -H "$H" https://$SERVER:8443/api/v1/vless/users/test-user-1 | python3 -m json.tool

# Отключить пользователя (VPN перестаёт работать)
curl -sk -X PATCH https://$SERVER:8443/api/v1/vless/users/test-user-1 \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"is_enabled":false}' | python3 -m json.tool

# Включить обратно
curl -sk -X PATCH https://$SERVER:8443/api/v1/vless/users/test-user-1 \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"is_enabled":true}' | python3 -m json.tool

# Удалить тестового пользователя
curl -sk -X DELETE -H "$H" https://$SERVER:8443/api/v1/vless/users/test-user-1
# → 204 No Content (пустое тело)
```

---

## Проблемы и решения

### `vless://` ссылка содержит `@:443` вместо `@IP:443`

**Причина**: в 3x-ui поле «Listen IP» у inbound'а пустое (слушает на всех интерфейсах).
Node-agent берёт адрес для ссылки из этого поля.

**Решение**: в панели 3x-ui открыть inbound → поле «Listen IP» → вписать **публичный IP сервера**
(тот же, что в `MTG_SERVER_IP`). После сохранения перезапустить node-agent:
```bash
docker compose restart node-agent
```

### `vless_backend: "offline"` после запуска

Проверить, доступна ли 3x-ui из контейнера:
```bash
docker exec node-agent wget -qO- http://host.docker.internal:2053/login
# должен вернуть HTML страницу или JSON
```
Если `host.docker.internal` не резолвится — убедитесь, что Docker версии 20.10+
(`docker --version`) и `extra_hosts: host.docker.internal:host-gateway` в compose (уже прописано).

### `mtproto_backend: "offline"`

Проверить путь к конфигу:
```bash
docker exec node-agent cat /etc/mtg/config.toml
# должен содержать строку: secret = "..."
```
Если пусто — убедитесь, что `MTG_CONFIG_HOST_PATH` в `.env` указывает на существующий файл.

### Контейнер node-agent постоянно рестартует

```bash
docker logs node-agent --tail 50
```
Чаще всего причина — неверный `.env` (отсутствующая переменная, неверный URL).
