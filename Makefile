.PHONY: help up down logs build api worker shell ingest test fmt lint

help:
	@echo "make up        - sobe toda a stack (api, worker, postgres, redis, qdrant, waha)"
	@echo "make down      - derruba a stack"
	@echo "make logs      - tail dos logs da api e worker"
	@echo "make ingest    - (re)indexa data/knowledge no Qdrant"
	@echo "make test      - roda pytest"
	@echo "make fmt       - formata com ruff"
	@echo "make lint      - lint com ruff"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

build:
	docker compose build

ingest:
	docker compose exec api python -m scripts.ingest_kb

test:
	docker compose exec api pytest

fmt:
	ruff format src tests scripts

lint:
	ruff check src tests scripts
