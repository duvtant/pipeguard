COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: up down logs build tunnel web-dev test reset
up:      ; $(COMPOSE) up --build -d
down:    ; $(COMPOSE) down
build:   ; $(COMPOSE) build
logs:    ; $(COMPOSE) logs -f --tail=100
tunnel:  ; $(COMPOSE) --profile tunnel up -d cloudflared
web-dev: ; cd web && pnpm dev
test:    ; python -m pytest -q
reset:   ; ./scripts/reset
