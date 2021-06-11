help:
	@echo "Commands:"
	@echo "install    : installs required packages."

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

install-test:
	python -m pip install -e ".[test]"

great-expectations:
	great_expectations checkpoint run v1ckpt
	great_expectations checkpoint run v2ckpt

test: great-expectations
	pytest --cov tagifai --cov app --cov-report html

test-non-training: great-expectations
	pytest -m "not training"