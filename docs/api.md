# REST API

Базовый адрес при локальном запуске: `http://127.0.0.1:8000`.
Интерактивная документация — `/docs` (Swagger UI), `/redoc`, схема — `/openapi.json`.

Формат обмена — JSON (`application/json`), кроме загрузки (`multipart/form-data`)
и экспорта (файлы).

## Содержание

- [Общие правила](#общие-правила)
- [Служебные](#служебные)
- [Отчёты](#отчёты)
- [Аналитика](#аналитика)
- [Экспорт](#экспорт)
- [Коды ошибок](#коды-ошибок)

## Общие правила

- Лист задаётся параметром `sheet`: `details` («Детали») или `trackers` («Трекеры»).
- Детализация: `granularity=day|month|all`.
- Агрегация числовых метрик: `aggregation=avg|sum|min|max` (по умолчанию `avg`).
- Даты — `YYYY-MM-DD`, фильтр включительный с обеих сторон.
- `report_id` ограничивает выборку одним отчётом; без него учитываются все отчёты.
- Тема графиков: `theme=light|dark` (по умолчанию `light`).

## Служебные

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "data/app.db",
  "reports": 2,
  "details_rows": 250,
  "trackers_rows": 250,
  "cache": {"entries": 3, "max_entries": 384, "hits": 5, "misses": 3, "hit_rate": 0.625, "ttl_seconds": 300}
}
```

### `GET /api/catalog`

Возвращает листы, колонки и метрики, доступные агрегации и детализации.

```json
{
  "app": "DataScope",
  "version": "1.0.0",
  "default_sheet": "details",
  "default_metrics": {"details": "fps", "trackers": "avg_hz"},
  "sheets": [
    {
      "key": "details",
      "title": "Детали",
      "description": "Технические характеристики видеофайлов.",
      "columns": [{"key": "date", "title": "Дата", "kind": "date", "format": "date"}],
      "metrics": [
        {
          "key": "bitrate", "title": "Битрейт", "kind": "number", "unit": "Мбит/с",
          "group": "Видео", "chartable": true, "aggregation": "avg",
          "aggregations": ["avg", "sum", "min", "max"], "decimals": 2
        }
      ]
    }
  ],
  "granularities": [{"key": "day", "title": "По дням"}],
  "aggregations": [{"key": "avg", "title": "Среднее"}]
}
```

## Отчёты

### `GET /api/reports`

```json
{
  "items": [
    {
      "id": "rep_f51644b18966",
      "title": "Демо-набор: сентябрь–ноябрь 2026",
      "filename": "demo_report_90d.xlsx",
      "uploaded_at": "2026-11-21T19:07:13+00:00",
      "size_bytes": 44678,
      "sha256": "0c1c725c…",
      "details_rows": 215,
      "trackers_rows": 215,
      "skipped_rows": 0,
      "status": "ready",
      "message": null
    }
  ],
  "total": 1
}
```

### `POST /api/reports`

`multipart/form-data`:

| Поле | Обязательно | Описание |
|------|-------------|----------|
| `file` | да | `.xlsx` или `.xlsm`, до `DASHBOARD_MAX_UPLOAD_MB` МБ |
| `title` | нет | название отчёта в интерфейсе |

Ответ `201 Created`:

```json
{
  "report": {"id": "rep_…", "details_rows": 35, "trackers_rows": 35, "status": "ready"},
  "duplicate": false,
  "message": "Обработано строк: Детали — 35, Трекеры — 35"
}
```

Повторная загрузка того же файла: `duplicate: true`, новый отчёт не создаётся.

```bash
curl -X POST http://127.0.0.1:8000/api/reports \
  -F "file=@data/raw/data_detail-report.xlsx" \
  -F "title=Исходный отчёт"
```

### `GET /api/reports/{id}`

Карточка отчёта; `404`, если отчёт не найден.

### `GET /api/reports/{id}/download`

Исходный Excel-файл (`Content-Disposition: attachment`).

### `DELETE /api/reports/{id}`

Удаляет отчёт, его строки (каскадно) и сохранённый файл, сбрасывает кэш.

```json
{"id": "rep_…", "deleted": true, "message": "Отчёт удалён"}
```

## Аналитика

### `GET /api/dashboard`

Главный эндпоинт дашборда: KPI и все графики выбранного листа.

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `sheet` | `details` \| `trackers` | `details` | лист отчёта |
| `granularity` | `day` \| `month` \| `all` | `day` | детализация |
| `aggregation` | `avg` \| `sum` \| `min` \| `max` | `avg` | агрегация |
| `date_from`, `date_to` | дата | — | период |
| `report_id` | строка | — | один отчёт |
| `theme` | `light` \| `dark` | `light` | палитра графиков |

Фрагмент ответа:

```json
{
  "sheet": "details",
  "sheet_title": "Детали",
  "granularity": "month",
  "aggregation": "avg",
  "total_rows": 250,
  "period": {"date_from": "2026-09-01", "date_to": "2026-10-14"},
  "kpis": [
    {"id": "episodes", "label": "Эпизодов", "value": 250, "display": "250", "unit": "шт.",
     "hint": "250 файлов трекинга", "tone": "primary"}
  ],
  "charts": [
    {
      "metric": "fps",
      "title": "FPS фактический",
      "unit": "fps",
      "group": "Видео",
      "kind": "numeric",
      "figure": {"data": [{"type": "bar", "x": ["сен 2026"], "y": [29.8]}], "layout": {}},
      "meta": {"summary": "среднее 29,76 fps · 250 эпизодов · 2 периода", "overall": {}}
    }
  ],
  "generated_at": "2026-11-21T19:20:00+00:00"
}
```

Порядок `charts`: сначала группа «Видео» (или «Трекинг»), затем «Время»,
«Качество», «Идентификация». Внутри группы — порядок каталога.

### `GET /api/charts/{sheet}/{metric}`

Один график в том же формате (`figure` + `meta`). Полезно для точечной
перерисовки карточки без запроса всего дашборда.

```bash
curl "http://127.0.0.1:8000/api/charts/trackers/avg_hz?granularity=month&theme=dark"
```

### `GET /api/table/{sheet}`

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `limit` | 25 | размер страницы (1…500) |
| `offset` | 0 | смещение |
| `sort` | `date` | колонка сортировки |
| `order` | `desc` | `asc` / `desc` |
| `search` | — | поиск по всем текстовым значениям |
| `date_from`, `date_to`, `report_id` | — | фильтры |

```json
{
  "sheet": "details",
  "columns": [{"key": "date", "title": "Дата", "kind": "date"}],
  "rows": [{"date": "2026-10-14", "episode": "PT_215", "bitrate": 7.06}],
  "total": 250,
  "limit": 25,
  "offset": 0,
  "sort": "date",
  "order": "desc"
}
```

Поиск ищет по предрассчитанному `search_text` (нижний регистр всех значений,
включая неизвестные колонки), поэтому работает и с кириллицей.

## Экспорт

### `GET /api/export/{sheet}.csv`

CSV, кодировка UTF-8 с BOM, разделитель `;`, окончания строк CRLF — открывается
в Excel без «кракозябр». Принимает те же фильтры, что и таблица (без пагинации).

### `GET /api/export/{sheet}.xlsx`

Excel-книга с оформленной шапкой. Файл собирается во временном каталоге
`data/exports` и удаляется после отдачи.

## Коды ошибок

| Код | Когда возникает |
|-----|-----------------|
| `400` | некорректный запрос на уровне домена |
| `404` | отчёт не найден, исходный файл отсутствует |
| `413` | файл больше лимита |
| `422` | неверные параметры, неизвестная метрика/лист, неподдерживаемый формат файла |

Формат тела ошибки:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Поддерживаются только файлы .xlsx и .xlsm",
    "details": {"filename": "report.txt"}
  }
}
```

Ошибки валидации FastAPI (например, `limit=0`) приходят в стандартном формате
`{"detail": [...]}`.
