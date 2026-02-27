.PHONY: help smoke smoke-full package docs docs-stop

help:
	@echo "Commands:"
	@echo "  make smoke       # Chat-only health check using smoke-config.json"
	@echo "  make smoke-full  # Full endpoint check using smoke-config.json"
	@echo "  make package     # Rebuild dist/delphi-api-safe.skill"
	@echo "  make docs        # Start interactive API reference at localhost:8787"
	@echo "  make docs-stop   # Stop the API reference server"

smoke:
	python3 scripts/run_smoke.py --config smoke-config.json --mode chat

smoke-full:
	python3 scripts/run_smoke.py --config smoke-config.json --mode full

package:
	/Users/jc3/.openclaw/workspace/.venv-skillpack/bin/python /opt/homebrew/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py ./delphi-api-safe ./dist

docs:
	@echo ""
	@echo "  Starting Delphi V3 API Reference..."
	@echo "  Open http://localhost:8787/api-reference.html"
	@echo "  Press Ctrl+C to stop"
	@echo ""
	python3 docs/serve.py

docs-stop:
	@lsof -ti :8787 | xargs kill -9 2>/dev/null && echo "  Stopped." || echo "  Not running."
