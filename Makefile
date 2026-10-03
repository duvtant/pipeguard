COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: up down logs build tunnel web-dev test reset evaluate train tune
up:      ; $(COMPOSE) up --build -d
down:    ; $(COMPOSE) down
build:   ; $(COMPOSE) build
logs:    ; $(COMPOSE) logs -f --tail=100
tunnel:  ; $(COMPOSE) --profile tunnel up -d cloudflared
web-dev: ; cd web && pnpm dev
test:    ; $(COMPOSE) run --rm api python -m pytest -q
reset:   ; ./scripts/reset
evaluate: ; $(COMPOSE) run --rm api python -m ml.evaluate
train:    ; $(COMPOSE) run --rm api python -m ml.train
tune:     ; $(COMPOSE) run --rm api python -m ml.tune
