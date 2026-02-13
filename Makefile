# Baofeng Logo Flasher - Reproducible Makefile

.PHONY: help ensure-venv install start stop restart status serve test clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
STREAMLIT := $(VENV)/bin/streamlit
APP := src/baofeng_logo_flasher/streamlit_ui.py
STREAMLIT_FLAGS := --logger.level=error --browser.gatherUsageStats=false
STREAMLIT_START_FLAGS := --server.fileWatcherType=none
RUN_DIR := .run
PID_FILE := $(RUN_DIR)/streamlit.pid
LOG_FILE := $(RUN_DIR)/streamlit.log

# ANSI colors for informative output
BLUE := \033[1;34m
GREEN := \033[1;32m
YELLOW := \033[1;33m
RED := \033[1;31m
CYAN := \033[1;36m
RESET := \033[0m

help:
	@printf "$(BLUE)Baofeng Logo Flasher - Available commands$(RESET)\n\n"
	@printf "  $(CYAN)make install$(RESET)    Create venv and install project deps (ui+dev)\n"
	@printf "  $(CYAN)make start$(RESET)      Start Streamlit in background (PID/log tracked)\n"
	@printf "  $(CYAN)make stop$(RESET)       Stop tracked Streamlit process\n"
	@printf "  $(CYAN)make restart$(RESET)    Restart tracked Streamlit process\n"
	@printf "  $(CYAN)make status$(RESET)     Show tracked Streamlit status\n"
	@printf "  $(CYAN)make serve$(RESET)      Run Streamlit in foreground\n"
	@printf "  $(CYAN)make test$(RESET)       Run pytest\n"
	@printf "  $(CYAN)make clean$(RESET)      Remove cache/temp/runtime files\n\n"

ensure-venv:
	@test -x $(PYTHON) || (printf "$(RED)✗ Virtual env missing.$(RESET) Run: $(CYAN)make install$(RESET)\n"; exit 1)

install:
	@printf "$(BLUE)📦 Setting up virtual environment...$(RESET)\n"
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PYTHON) -m pip install --upgrade pip
	@$(PIP) install -e ".[ui,dev]"
	@printf "$(GREEN)✓ Environment ready.$(RESET) Run: $(CYAN)make start$(RESET)\n"

start: ensure-venv
	@printf "$(BLUE)🚀 Starting Streamlit server...$(RESET)\n"
	@mkdir -p $(RUN_DIR)
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		printf "$(YELLOW)⚠ Streamlit already running$(RESET) (PID $$(cat $(PID_FILE))).\n"; \
		printf "  URL: $(CYAN)http://localhost:8501$(RESET)\n"; \
		exit 0; \
	fi
	@rm -f $(PID_FILE)
	@nohup env PYTHONPATH=src $(STREAMLIT) run $(APP) $(STREAMLIT_FLAGS) $(STREAMLIT_START_FLAGS) > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@sleep 2
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		printf "$(GREEN)✓ Streamlit started$(RESET) (PID $$(cat $(PID_FILE))).\n"; \
		printf "  URL: $(CYAN)http://localhost:8501$(RESET)\n"; \
		printf "  Log: $(CYAN)$(LOG_FILE)$(RESET)\n"; \
	else \
		printf "$(RED)✗ Failed to start Streamlit.$(RESET) Check: $(CYAN)$(LOG_FILE)$(RESET)\n"; \
		rm -f $(PID_FILE); \
		exit 1; \
	fi

stop:
	@printf "$(BLUE)🛑 Stopping Streamlit server...$(RESET)\n"
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID; \
			sleep 1; \
			if kill -0 $$PID 2>/dev/null; then kill -9 $$PID; fi; \
			printf "$(GREEN)✓ Stopped Streamlit$(RESET) (PID $$PID).\n"; \
		else \
			printf "$(YELLOW)⚠ Stale PID file removed$(RESET) ($(PID_FILE)).\n"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		printf "$(YELLOW)⚠ No tracked Streamlit process.$(RESET)\n"; \
	fi

restart: stop start

status:
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			printf "$(GREEN)✓ Running$(RESET) (PID $$PID)\n"; \
			printf "  URL: $(CYAN)http://localhost:8501$(RESET)\n"; \
			printf "  Log: $(CYAN)$(LOG_FILE)$(RESET)\n"; \
		else \
			printf "$(RED)✗ Not running$(RESET) (stale PID file: $(PID_FILE))\n"; \
			exit 1; \
		fi; \
	else \
		printf "$(RED)✗ Not running$(RESET)\n"; \
		exit 1; \
	fi

serve: ensure-venv
	@printf "$(BLUE)🚀 Running Streamlit in foreground$(RESET) (Ctrl+C to stop).\n"
	@env PYTHONPATH=src $(STREAMLIT) run $(APP) $(STREAMLIT_FLAGS)

test: ensure-venv
	@printf "$(BLUE)🧪 Running tests...$(RESET)\n"
	@PYTHONPATH=src $(PYTHON) -m pytest -q
	@printf "$(GREEN)✓ Test run complete$(RESET)\n"

clean:
	@printf "$(BLUE)🧹 Cleaning cache and runtime files...$(RESET)\n"
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
	@find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
	@rm -rf .mypy_cache $(RUN_DIR)
	@printf "$(GREEN)✓ Clean complete$(RESET)\n"
