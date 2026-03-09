.PHONY: run test install clean

run:
	.venv/bin/python run.py

test:
	.venv/bin/python -m pytest tests/ -v

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	find . -name '*.pyc' -delete
