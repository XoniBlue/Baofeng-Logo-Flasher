# Baofeng Logo Flasher - Development Makefile

.PHONY: start stop restart status test install clean help shell serve zip-repo

# Virtual environment paths
VENV := ./venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
STREAMLIT := $(VENV)/bin/streamlit
ACTIVATE := source $(VENV)/bin/activate

# Default target
help:
	@echo "Baofeng Logo Flasher - Available Commands:"
	@echo ""
	@echo "  make start    - Activate venv & start server (background)"
	@echo "  make stop     - Stop server & deactivate venv"
	@echo "  make restart  - Stop and start again"
	@echo "  make serve    - Run in foreground (Ctrl+C to stop)"
	@echo "  make status   - Check if server is running"
	@echo "  make test     - Run the test suite"
	@echo "  make install  - Create venv and install dependencies"
	@echo "  make clean    - Remove cache and temp files"
	@echo "  make shell    - Open interactive shell with venv"
	@echo "  make zip-repo - Create repo zip (excluding venv/cache/backups)"
	@echo ""

# Start the Streamlit server (background, with venv)
# NOTE: Requires 'ui' extra: pip install -e ".[ui]"
start:
	@echo "🔄 Activating virtual environment..."
	@echo "🚀 Starting Streamlit server..."
	@bash -c '$(ACTIVATE) && streamlit run src/baofeng_logo_flasher/streamlit_ui.py --logger.level=error &'
	@sleep 2
	@echo "✓ venv activated, server running at http://localhost:8501"
	@echo ""
	@echo "To stop: make stop"

# Run in foreground (Ctrl+C to stop)
serve:
	@echo "🔄 Activating virtual environment..."
	@echo "🚀 Starting Streamlit server (foreground)..."
	@echo "   Press Ctrl+C to stop"
	@echo ""
	@bash -c '$(ACTIVATE) && streamlit run src/baofeng_logo_flasher/streamlit_ui.py'
	@echo ""
	@echo "✓ Server stopped, venv deactivated"

# Stop the Streamlit server
stop:
	@echo "🛑 Stopping Streamlit server..."
	@pkill -f streamlit 2>/dev/null && echo "✓ Server stopped" || echo "⚠ No server was running"
	@echo "✓ Virtual environment deactivated"

# Restart the server
restart: stop
	@sleep 1
	@$(MAKE) start

# Check server status
status:
	@if pgrep -f streamlit > /dev/null; then \
		echo "✓ Streamlit is running (PID: $$(pgrep -f streamlit))"; \
		echo "  URL: http://localhost:8501"; \
		echo "  venv: active"; \
	else \
		echo "✗ Streamlit is not running"; \
		echo "  venv: inactive"; \
	fi

# Run tests (with venv)
test:
	@echo "🔄 Activating virtual environment..."
	@echo "🧪 Running tests..."
	@bash -c '$(ACTIVATE) && python -m pytest tests/ -v'
	@echo "✓ Tests complete, venv deactivated"

# Test one chunk gray upload (debugging)
test-gray:
	@echo "🔄 Testing single chunk gray upload..."
	@bash -c '$(ACTIVATE) && python test_one_chunk_gray.py'

# Install dependencies (creates venv if needed)
install:
	@echo "📦 Setting up virtual environment..."
	@test -d $(VENV) || python3 -m venv $(VENV)
	@echo "📦 Installing dependencies (CLI + UI + dev)..."
	@bash -c '$(ACTIVATE) && pip install -e ".[ui,dev]"'
	@echo "✓ Virtual environment ready!"
	@echo ""
	@echo "Run 'make start' to launch the web UI"
	@echo "Run 'baofeng-logo-flasher --help' to use CLI"

# Open interactive shell with venv activated
shell:
	@echo "🐚 Opening shell with venv activated..."
	@echo "   Type 'exit' to deactivate and return"
	@bash --rcfile <(echo 'source $(VENV)/bin/activate && PS1="(venv) \w $$ "')
	@echo "✓ venv deactivated"

# Clean cache files
clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .mypy_cache 2>/dev/null || true
	@echo "✓ Cleaned"

# Create repo zip excluding large/derived folders
zip-repo:
	@echo "📦 Creating repo zip..."
	@zip -r LogoFlasher_repo.zip . \
	  -x "venv/*" ".venv/*" "__pycache__/*" "*.pyc" "*.pyo" "*.pyd" \
	     ".git/*" ".gitignore" "*.egg-info/*" "dist/*" "build/*" \
	     ".pytest_cache/*" ".mypy_cache/*" ".ruff_cache/*" \
	     "backups/*" "inputs/*" ".DS_Store"
	@echo "✓ Created LogoFlasher_repo.zip"
