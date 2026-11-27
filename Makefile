.PHONY: install install-dev lint format test health demo run docker-build clean

install:
	python -m pip install -r requirements.txt

install-dev:
	python -m pip install -r requirements-dev.txt

lint:
	python -m ruff check src tests main.py
	python -m ruff format --check src tests main.py
	python -m flake8 --max-line-length=120 src tests main.py

format:
	python -m ruff format src tests main.py

test:
	python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=75

health:
	python main.py --health

demo:
	python main.py --demo

run:
	python main.py --serve

docker-build:
	docker build -t techcorp-analytics:latest .

clean:
	python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in list(pathlib.Path('.').rglob('__pycache__')) + [pathlib.Path('.pytest_cache'), pathlib.Path('.ruff_cache'), pathlib.Path('.mypy_cache'), pathlib.Path('htmlcov')]]"
