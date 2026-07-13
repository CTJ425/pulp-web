# 所有操作的唯一入口(CLAUDE.md 指令表);每個 target 保證 exit 0 = 成功
SHELL := /bin/bash
ENV_FILE := deploy/compose/.env
COMPOSE := docker compose -f deploy/compose/compose.yml --env-file $(ENV_FILE) --profile dev
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.PHONY: dev status seed smoke test test-api e2e lint down down-clean fixtures env

env: $(ENV_FILE)
$(ENV_FILE):
	./scripts/gen-env.sh $(ENV_FILE)

fixtures:
	./scripts/build-fixtures.sh

dev: env fixtures
	$(COMPOSE) up -d --wait
	@# 冪等:每次都把 admin 密碼設成 .env 的值
	$(COMPOSE) exec pulp pulpcore-manager reset-admin-password \
	  --password "$$(grep -E '^PULP_ADMIN_PASSWORD=' $(ENV_FILE) | cut -d= -f2)"
	./scripts/status.sh

status:
	./scripts/status.sh

seed:
	$(COMPOSE) run --rm --build tools bash scripts/seed-fixtures.sh

smoke:
	$(COMPOSE) run --rm --build tools bash scripts/smoke.sh

test:
	cd bff && $(UV) run pytest ../tests/unit -q

test-api:
	cd bff && $(UV) run pytest ../tests/api -q

e2e:
	cd tests/e2e && npm run test

lint:
	cd bff && $(UV) run ruff check app ../tests/unit ../tests/api
	cd frontend && npm run lint && npx tsc -b

down:
	$(COMPOSE) down

# 連資料一起清(volumes);fixtures 產物保留
down-clean:
	$(COMPOSE) down -v
