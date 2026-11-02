# Campaign SaaS local helpers

up:
	docker compose -f deploy/docker-compose.yml up --build -d

down:
	docker compose -f deploy/docker-compose.yml down

dev: up

anti-drift:
	.venv/bin/python scripts/check_saas_anti_drift.py

test:
	.venv/bin/python -m pytest -q

openapi:
	.venv/bin/python scripts/generate_openapi.py
