# Kiraci development entry points (Linux/bash; WSL2 is the supported host).
# Override the venv: `make check VENV=/home/dev/kiraci-venv`
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install lint type test check run status verify

install: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

lint:
	$(PY) -m ruff check src/ tests/ tools/

type:
	$(PY) -m mypy src/

test:
	$(PY) -m pytest -q

check: lint type test

run:
	$(PY) -m kiraci.cli run

status:
	$(PY) -m kiraci.cli status

verify:
	$(PY) -m kiraci.cli verify
