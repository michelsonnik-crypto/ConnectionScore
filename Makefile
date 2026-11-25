PYTHON ?= .venv/bin/python
RUN_ID ?= $(shell date -u +%Y%m%dT%H%M%SZ)

.PHONY: test data models diagnostics render part-a

test:
	MPLCONFIGDIR=/tmp/connectionscore-mpl $(PYTHON) -m unittest discover -s tests -p 'test_*.py'

data:
	MPLCONFIGDIR=/tmp/connectionscore-mpl $(PYTHON) scripts/part_a.py --stage data --run-id $(RUN_ID)-data

models:
	MPLCONFIGDIR=/tmp/connectionscore-mpl $(PYTHON) scripts/part_a.py --stage models --run-id $(RUN_ID)-models

diagnostics:
	MPLCONFIGDIR=/tmp/connectionscore-mpl $(PYTHON) scripts/part_a_diagnostics.py $(RUN_ID)-diagnostics

render:
	$(PYTHON) scripts/render_part_a.py --data-run $(RUN_ID)-data --model-run $(RUN_ID)-models --diagnostics-run $(RUN_ID)-diagnostics

part-a:
	$(MAKE) test
	$(MAKE) data RUN_ID=$(RUN_ID)
	$(MAKE) models RUN_ID=$(RUN_ID)
	$(MAKE) diagnostics RUN_ID=$(RUN_ID)
	$(MAKE) render RUN_ID=$(RUN_ID)
