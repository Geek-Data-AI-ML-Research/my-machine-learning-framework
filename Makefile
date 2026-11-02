.PHONY: dev up down openapi anti-drift test install-saas web-build

install-saas:
	.venv/bin/pip install -e ".[saas,dev]"

dev: up

up:
	docker compose -f deploy/docker-compose.yml up --build -d
	@echo "API  http://127.0.0.1:8000/health"
	@echo "Web  http://127.0.0.1:5173/"

down:
	docker compose -f deploy/docker-compose.yml down

openapi:
	.venv/bin/python scripts/generate_openapi.py

anti-drift:
	.venv/bin/python scripts/check_saas_anti_drift.py

test:
	.venv/bin/python -m pytest -q

web-build:
	mkdir -p web/dist
	cp web/public/index.html web/dist/index.html
	cp web/public/app.js web/dist/app.js
	cp web/public/styles.css web/dist/styles.css
