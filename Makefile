# Упрощённые команды для разработки (Linux/macOS, при наличии make).
PYTHON ?= python
PORT ?= 8000

.PHONY: install dev run test lint demo ingest clean

install:  ## установить зависимости сервиса
	$(PYTHON) -m pip install -r requirements.txt

dev:  ## установить зависимости для разработки и тестов
	$(PYTHON) -m pip install -r requirements-dev.txt

run:  ## запустить сервис
	$(PYTHON) -m src.main --port $(PORT)

test:  ## запустить тесты
	$(PYTHON) -m pytest

lint:  ## проверить код линтером
	$(PYTHON) -m ruff check src scripts tests

demo:  ## пересоздать демонстрационный отчёт
	$(PYTHON) scripts/generate_demo_report.py --output data/raw/demo_report_90d.xlsx

ingest:  ## импортировать файл: make ingest FILE=path/to/report.xlsx
	$(PYTHON) scripts/ingest_report.py "$(FILE)"

clean:  ## удалить кэши и локальную базу
	rm -rf .pytest_cache .ruff_cache **/__pycache__
	rm -f data/app.db data/app.db-wal data/app.db-shm
