.PHONY: init dev build up down logs restart ps help

## Показать это сообщение
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

## Первый запуск: каталоги, секрет mtg, .env из примера
init:
	bash scripts/init.sh

## Локально с hot-reload (только node-agent; 3x-ui/mtg не нужны для разработки)
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up node-agent

## Собрать образ node-agent из Dockerfile
build:
	docker compose build node-agent

## Поднять весь стек в фоне (3x-ui + mtg + node-agent)
up:
	docker compose up -d

## Остановить стек
down:
	docker compose down

## Стримить логи node-agent
logs:
	docker compose logs -f node-agent

## Перезапустить контейнер node-agent (без пересборки образа)
restart:
	docker compose restart node-agent

## Статус всех контейнеров стека
ps:
	docker compose ps
