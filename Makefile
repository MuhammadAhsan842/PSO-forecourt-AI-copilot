# Small conveniences for local dev.
# Everything works without make too — see the commands themselves.

.PHONY: help install dev-install lint typecheck fmt test api dashboard probe baseline replay clean

help:
	@echo "make install      - install package + inference deps"
	@echo "make dev-install  - install with dev deps (pytest, ruff, mypy)"
	@echo "make lint         - ruff check"
	@echo "make typecheck    - mypy src"
	@echo "make fmt          - ruff format"
	@echo "make test         - pytest"
	@echo "make api          - uvicorn dev server on :8080"
	@echo "make dashboard    - dashboard dev server on :5173"
	@echo "make probe        - run camera capability probe"
	@echo "make baseline     - capture 60s day-baseline stills"
	@echo "make replay CLIP=path.mp4 CAMERA=ptz1"

install:
	pip install -e '.[inference]'

dev-install:
	pip install -e '.[inference,dev]'

lint:
	ruff check src scripts tests

typecheck:
	mypy src

fmt:
	ruff format src scripts tests

test:
	pytest

api:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8080

dashboard:
	cd dashboard && npm install && npm run dev

probe:
	python -m scripts.camera_probe

baseline:
	python -m scripts.capture_baseline --label day --duration 60

replay:
	python -m scripts.replay_clip --input $(CLIP) --camera $(CAMERA) --annotated data/reports/replay.mp4

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
