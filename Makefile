.PHONY: dev up down logs test lint format generate-data

dev:
	docker compose up --build

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

test:
	cd apps/api && pytest -q

lint:
	cd apps/api && ruff check . && mypy app

format:
	cd apps/api && ruff format .

generate-data:
	python scripts/generate_synthetic_data.py --count 500 --output data/generated/transactions.jsonl
