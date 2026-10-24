CONFIG ?= config/params.yaml
# The demo uses real Laguna boundaries and modeled population unless CONFIG is given on the command line.
DEMO_CONFIG ?= config/climate.yaml
PYTHON ?= .venv/bin/python
WORKFLOW_DEMO_DB ?= $(CURDIR)/data/reports/guided_workflow.sqlite3
# Import agap from src directly. Python skips hidden .pth files, and macOS can
# mark .venv hidden, which breaks the editable install.
export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH))

.PHONY: benchmark manifest data simulate train allocate evaluate spatial longitudinal surveillance integrity all test clean demo experiments collect triage analyst prepare-public collect-climate collect-climate-arco prepare-climate

data:
	$(PYTHON) scripts/build_data.py --config $(CONFIG)

simulate:
	$(PYTHON) scripts/simulate.py --config $(CONFIG)

train:
	$(PYTHON) scripts/train.py --config $(CONFIG)

allocate:
	$(PYTHON) scripts/allocate.py --config $(CONFIG)

evaluate:
	$(PYTHON) scripts/evaluate.py --config $(CONFIG)

spatial:
	$(PYTHON) scripts/spatial.py --config $(CONFIG)

longitudinal:
	$(PYTHON) scripts/longitudinal.py --config $(CONFIG)

surveillance:
	$(PYTHON) scripts/surveillance.py --config $(CONFIG)

integrity:
	$(PYTHON) scripts/integrity.py --config $(CONFIG)

all:
	$(PYTHON) scripts/run_pipeline.py --config $(CONFIG)

demo:
	$(PYTHON) -m streamlit run app/main.py --server.headless true --server.address localhost --browser.gatherUsageStats false -- --config $(if $(filter command line,$(origin CONFIG)),$(CONFIG),$(DEMO_CONFIG))

.PHONY: api web web-build
api:
	$(PYTHON) -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

web:
	cd frontend && npm run dev

web-build:
	cd frontend && npm run build

.PHONY: test-fe
test-fe:
	cd frontend && npm test

.PHONY: demo-guided
demo-guided:
	AGAP_WORKFLOW_DB="$(WORKFLOW_DEMO_DB)" $(MAKE) demo $(if $(filter command line,$(origin CONFIG)),CONFIG=$(CONFIG))

triage:                          # PRD v3 risk level: retrain, cut-offs, Thai benchmark (outputs/)
	$(PYTHON) scripts/train_triage.py

analyst:                         # PRD v3 analyst view data from the frozen run and ERA5-Land (outputs/analyst/)
	$(PYTHON) scripts/build_analyst.py

experiments:
	$(PYTHON) scripts/experiments.py --config $(CONFIG)

manifest:                        # DATA-02 metadata for collected sources, no downloads
	$(PYTHON) scripts/update_manifest.py

collect:
	$(PYTHON) scripts/collect_data.py --demographics

prepare-public:
	$(PYTHON) scripts/prepare_public_data.py --config config/public.yaml

collect-climate:
	$(PYTHON) scripts/collect_climate.py

collect-climate-arco:                # ERA5-Land from the ECMWF ARCO Zarr stores (no CDS queue)
	$(PYTHON) scripts/collect_climate_arco.py

prepare-climate:
	$(PYTHON) scripts/prepare_climate.py

.PHONY: prepare-weather collect-map
collect-map:
	$(PYTHON) scripts/collect_basemap.py

prepare-weather:
	$(PYTHON) scripts/prepare_available_weather.py

benchmark:                       # NFR-07/08; defaults to the full profile
	$(PYTHON) scripts/benchmark.py --config $(if $(filter config/params.yaml,$(CONFIG)),config/full.yaml,$(CONFIG))

test:
	$(PYTHON) -m pytest

.PHONY: verify-browser
verify-browser:
	$(PYTHON) scripts/verify_workflow_browser.py --config $(CONFIG) --output-dir outputs/browser-verification/workflow-coordinator
	$(PYTHON) scripts/verify_offline_browser.py --config $(CONFIG) --output-dir outputs/browser-verification/coordinator

clean:
	rm -rf data/processed/* data/synthetic/* outputs/figures/* outputs/tables/*
	touch data/processed/.gitkeep data/synthetic/.gitkeep outputs/figures/.gitkeep outputs/tables/.gitkeep
