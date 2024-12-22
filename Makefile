dev-up:
	docker compose --env-file .env -f docker-compose.dev.yml up -d

dev-down:
	docker compose --env-file .env -f docker-compose.dev.yml down

dev-build:
	docker compose --env-file .env -f docker-compose.dev.yml build

help:
	@echo "Usage: make [command]"
	@echo "Commands:"
	@echo "  dev-up: Start the development services"
	@echo "  dev-down: Stop the development services"
	@echo "  dev-build: Build the development services"
	@echo "  help: Show this help message"

.PHONY: dev-up dev-down dev-build help