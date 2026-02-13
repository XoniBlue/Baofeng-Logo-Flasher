SHELL := /bin/zsh

WEB_DIR := web
WORKER_DIR := cloudflare/log-intake-worker

LOG_WORKER_BASE_URL ?= https://baofeng-log-intake.robbiem707-354.workers.dev
ADMIN_TOKEN ?=
LIMIT ?= 20

.PHONY: help install dev dev-web dev-worker preflight test build worker-typecheck errors success health cf-reauth cf-migrate cf-deploy

help:
	@echo "Simple deploy workflow"
	@echo ""
	@echo "Development"
	@echo "  make dev                  # start web + worker dev servers together"
	@echo "  make dev-web              # start web dev server only"
	@echo "  make dev-worker           # start worker dev server only"
	@echo ""
	@echo "Pre-deploy checks"
	@echo "  make test                 # web tests"
	@echo "  make build                # web production build"
	@echo "  make worker-typecheck     # worker TypeScript check"
	@echo "  make preflight            # test + build + worker-typecheck"
	@echo ""
	@echo "Cloudflare telemetry checks"
	@echo "  make errors LIMIT=20      # recent errors (requires ADMIN_TOKEN)"
	@echo "  make success              # successful flash count"
	@echo "  make health               # worker health"
	@echo ""
	@echo "Cloudflare auth/deploy"
	@echo "  make cf-reauth            # wrangler logout/login"
	@echo "  make cf-migrate           # run telemetry D1 migration (remote)"
	@echo "  make cf-deploy            # deploy worker"
	@echo ""
	@echo "Vars: LOG_WORKER_BASE_URL, ADMIN_TOKEN, LIMIT"

install:
	@npm --prefix $(WEB_DIR) ci
	@npm --prefix $(WORKER_DIR) ci

dev:
	@echo "Starting web and worker dev servers (Ctrl+C to stop both)..."
	@set -e; \
		npm --prefix $(WEB_DIR) run dev & \
		WEB_PID=$$!; \
		npm --prefix $(WORKER_DIR) run dev & \
		WORKER_PID=$$!; \
		cleanup() { \
			kill $$WEB_PID $$WORKER_PID 2>/dev/null || true; \
			wait $$WEB_PID 2>/dev/null || true; \
			wait $$WORKER_PID 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		wait $$WEB_PID $$WORKER_PID

dev-web:
	@npm --prefix $(WEB_DIR) run dev

dev-worker:
	@npm --prefix $(WORKER_DIR) run dev

test:
	@npm --prefix $(WEB_DIR) test

build:
	@npm --prefix $(WEB_DIR) run build

worker-typecheck:
	@cd $(WORKER_DIR) && npx tsc --noEmit -p tsconfig.json

preflight: test build worker-typecheck

errors:
	@if [ -z "$(ADMIN_TOKEN)" ]; then \
		echo "ADMIN_TOKEN is required (example: make errors ADMIN_TOKEN=... LIMIT=20)"; \
		exit 1; \
	fi
	@ADMIN_TOKEN="$(ADMIN_TOKEN)" LOG_WORKER_BASE_URL="$(LOG_WORKER_BASE_URL)" \
		npm --prefix $(WORKER_DIR) run recent -- --limit $(LIMIT)

success:
	@curl -sS "$(LOG_WORKER_BASE_URL)/metrics/flash-count" && echo

health:
	@curl -sS "$(LOG_WORKER_BASE_URL)/health" && echo

cf-reauth:
	@cd $(WORKER_DIR) && wrangler logout && wrangler login

cf-migrate:
	@npm --prefix $(WORKER_DIR) run d1:migrate:v1:remote

cf-deploy:
	@npm --prefix $(WORKER_DIR) run deploy
