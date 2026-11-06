.PHONY: dev up down openapi api-docs anti-drift test install-saas web-build

install-saas:
	.venv/bin/pip install -e ".[saas,dev]"

dev: up

up:
	docker compose -f deploy/docker-compose.yml up --build -d
	@echo "API  http://127.0.0.1:8001/health"
	@echo "Web  http://127.0.0.1:5175/"
	@echo "MCP  http://127.0.0.1:8100/mcp"

down:
	docker compose -f deploy/docker-compose.yml down

openapi:
	.venv/bin/python scripts/generate_openapi.py

api-docs: openapi
	@test -f docs/reference/saas-api.md
	@test -f docs/reference/saas-plan-parity-matrix.md
	.venv/bin/python -m pytest -q tests/test_saas_api_docs.py tests/test_saas_plan_parity.py

anti-drift:
	.venv/bin/python scripts/check_saas_anti_drift.py

test:
	.venv/bin/python -m pytest -q

web-build:
	mkdir -p web/dist
	cp web/public/index.html web/dist/index.html
	cp web/public/app.js web/dist/app.js
	cp web/public/styles.css web/dist/styles.css
