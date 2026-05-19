.PHONY: test check syntax

PYTHON ?= python3

syntax:
	$(PYTHON) -m py_compile COD_telegram_gateway.py COD_telegram_bridge.py
	bash -n codex-telegram
	bash -n start_codex_telegram_session.sh

test:
	$(PYTHON) -m unittest discover -s tests

check: syntax test
	git diff --check
