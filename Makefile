.PHONY: help smoke smoke-full package

help:
	@echo "Commands:"
	@echo "  make smoke       # Chat-only health check using smoke-config.json"
	@echo "  make smoke-full  # Full endpoint check using smoke-config.json"
	@echo "  make package     # Rebuild dist/delphi-api-safe.skill"

smoke:
	python3 scripts/run_smoke.py --config smoke-config.json --mode chat

smoke-full:
	python3 scripts/run_smoke.py --config smoke-config.json --mode full

package:
	/Users/jc3/.openclaw/workspace/.venv-skillpack/bin/python /opt/homebrew/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py ./delphi-api-safe ./dist
