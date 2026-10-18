.PHONY: seed test eval benchmark demo web-build syntax

seed:
	python data/generate_demo.py

test:
	python -m pytest -q

eval: seed
	python -m evaluation.run

benchmark: seed
	python -m benchmark.run

syntax: seed
	python -m pytest -q tests/test_falkordb_spike_v2.py

web-build:
	cd web && npm run typecheck && npm run build

demo:
	docker compose up --build
