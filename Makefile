.PHONY: help setup smoke smoke-search smoke-full smoke-v4 package docs docs-stop

help:
	@echo "Commands:"
	@echo "  make setup        # Interactive wizard to create smoke-config.json"
	@echo "  make smoke        # V3 chat-only health check using smoke-config.json"
	@echo "  make smoke-search # V3 chat + knowledge base search tests"
	@echo "  make smoke-full   # V3 full endpoint check using smoke-config.json"
	@echo "  make smoke-v4     # V4 Developer Platform check (read-only by default)"
	@echo "  make package      # Rebuild dist/delphi-api-safe.skill"
	@echo "  make docs         # Start interactive API reference (V3 + V4) at localhost:8787"
	@echo "  make docs-stop    # Stop the API reference server"

setup:
	python3 scripts/setup.py

smoke:
	python3 scripts/run_smoke.py --config smoke-config.json --mode chat

smoke-search:
	python3 scripts/run_smoke.py --config smoke-config.json --mode chat --search

smoke-full:
	python3 scripts/run_smoke.py --config smoke-config.json --mode full

smoke-v4:
	python3 scripts/run_smoke.py --config smoke-config.json --api v4

package:
	python3 scripts/package_skill.py ./delphi-api-safe ./dist

docs:
	@echo ""
	@echo "  Starting Delphi V3 API Reference..."
	@echo "  Open http://localhost:8787/api-reference.html"
	@echo "  Press Ctrl+C to stop"
	@echo ""
	python3 docs/serve.py

docs-stop:
	@lsof -ti :8787 | xargs kill -9 2>/dev/null && echo "  Stopped." || echo "  Not running."
