# Разработка

## 1. Окружение

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -r requirements-dev.txt
pytest
ruff check app scripts tests
python -m src.main --reload
```

`--reload` перезапускает сервер при изменении Python-кода. Статические файлы
(`src/components`, `src/styles`) отдаются с диска — достаточно обновить страницу.

## 2. Принципы

1. **API тонкий.** Маршруты только валидируют параметры и вызывают сервис.
2. **Сервисы не импортируют FastAPI.** Их можно тестировать отдельно.
3. **SQL — только в `src/services/repository.py`.** Идентификаторы таблиц и колонок
   берутся из белых списков, значения передаются параметрами.
4. **Каталог метрик — источник правды.** Новое поле добавляется в `catalog.py`,
   остальное (парсер, API, графики, таблица) подхватывает его автоматически.
5. **Ошибки — доменные.** В сервисах поднимается `ValidationError`/`NotFoundError`,
   обработчик в `main.py` превращает их в JSON с нужным статусом.

## 3. Как добавить метрику

1. Убедитесь, что колонка есть в таблице (`src/services/database.py`). Если нет —
   добавьте поле в `details`/`trackers` и в `_record_to_row` оно попадёт само
   (ключи берутся из `PRAGMA table_info`).
2. В `src/services/catalog.py` добавьте `Column(...)`:
   ```python
   Column(
       "bitrate_peak", "Пиковый битрейт", "number", unit="Мбит/с",
       group="Видео", chartable=True, decimals=2, fmt="number",
       description="Максимальный битрейт за эпизод.",
       aliases=("пиковый битрейт", "peak bitrate"),
   )
   ```
3. Если колонка не обязательна, задайте `positive_only=True` — нули будут
   исключены из агрегатов.
4. Добавьте алиасы для реального заголовка и, при необходимости, правило в
   `_guess_key` (`src/services/normalization.py`).
5. Обновите `tests/conftest.py` (шапки/строки) и тесты, проверяющие счётчики
   метрик (`tests/test_api.py::test_catalog`).

График появится автоматически: `dashboard.py` перебирает `sheet.metrics`.

## 4. Как добавить новый лист

1. Опишите таблицу в `database.py` и добавьте её в `SHEET_TABLES`.
2. Создайте `Sheet(...)` в `catalog.py` с колонками.
3. Расширьте `detect_sheet_key` (например, «События» → `events`).
4. Добавьте ветку финализатора в `parser._prepare_row`, если нужны производные поля.
5. Добавьте лист в тесты и документацию.

## 5. Как добавить эндпоинт

1. Схему ответа — в `src/api/schemas.py`.
2. Маршрут — в соответствующий `routes_*.py`, зависимости из `deps.py`.
3. Бизнес-логику — в `src/services`, без обращения к `Request`.
4. Тест — в `tests/test_api.py`.

## 6. Как изменить график

Все фигуры собираются в `src/services/charts.py`:

- `numeric_figure` — столбцы + усы + линия количества;
- `histogram_figure` — распределение и среднее;
- `categorical_figure` — стек или рейтинг.

Общие настройки — `_layout` и `_axes`. Цвета тем — в словаре `THEMES`.
Клиент просто вызывает `Plotly.react`, поэтому менять JS не нужно.

## 7. Тесты

```bash
pytest -q                     # все тесты
pytest tests/test_api.py -q   # только API
pytest -k "parser and date"   # по имени
```

- `tests/conftest.py` собирает тестовый `.xlsx` и приложение с временной БД
  (`load_settings(data_dir=tmp_path, auto_seed=False)`);
- каждый тест получает чистую базу, поэтому порядок тестов не важен;
- для проверки JSON-фигур используется `json.dumps` — это ловит numpy-типы.

## 8. Линтер и стиль

- `ruff` с правилами `E,F,W,I,B,UP`, длина строки 110;
- импорты сортируются автоматически (`ruff check --fix`);
- имена модулей — существительные (`parser`, `aggregator`), функции — глаголы;
- docstring у каждого публичного модуля и функции;
- сообщения пользователю — на русском, код и комментарии — на русском/английском
  в зависимости от контекста (в проекте преобладает русский).

## 9. Демо-данные

```bash
python scripts/generate_demo_report.py --days 36 --per-day 6 --seed 42
```

Генератор детерминирован: при одном `--seed` файл побайтово повторяем.
Меняя `--days`, `--per-day` и `--start`, можно получить набор под конкретную
демонстрацию (например, 3 месяца по 10 эпизодов в день).

## 10. Релизный чек-лист

- [ ] `pytest` — все тесты зелёные;
- [ ] `ruff check app scripts tests` — без замечаний;
- [ ] `python -m src.main` — дашборд открывается, графики строятся;
- [ ] загрузка реального отчёта и экспорт CSV/XLSX работают;
- [ ] `CHANGELOG.md` обновлён, версия в `src/config.py` и `pyproject.toml` совпадает;
- [ ] скриншоты в `docs/screenshots` актуальны;
- [ ] `data/app.db` и `data/uploads` не попали в коммит.
