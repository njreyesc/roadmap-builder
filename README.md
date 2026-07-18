# roadmap-builder

Строит **roadmap (дорожную карту)** сразу в двух форматах — **Excel (`.xlsx`)** и
**PowerPoint (`.pptx`)** — из плана работ по спринтам/неделям или из списка фич с
оценками фаз (аналитика / разработка / тестирование). Дорожки группируются по
фичам; рендереры детерминированные, вся правка идёт через JSON.

Проект оформлен как [Agent Skill](roadmap-builder/SKILL.md) для Claude Code, но
скрипты работают и как обычные CLI-утилиты на Python.

## Возможности

- Два входа: **Excel-план работ** (спринты в колонках, задачи в ячейках) или
  **список фич с оценками** (человеко-дни / недели / спринты, зависимости, вехи).
- Детерминированный планировщик: раскладывает фазы фич по неделям с учётом
  `capacity` (пропускной способности команды), считает каскадные сдвиги.
- Импорт из текстового списка фич и из CSV-выгрузки эпиков Jira.
- Единый источник истины — `roadmap.json`; из него собираются оба файла.
- Вывод: сетка месяц→недели, свимлейны по фичам, полосы работ, вехи-ромбы,
  выноски, линия «сегодня», флажки старта/финиша.

## Установка

```bash
pip install -r requirements.txt
```

Требуется Python 3.10+ и пакеты `openpyxl`, `python-pptx`.

## Быстрый старт

**Режим B — из списка фич с оценками:**

```bash
cd roadmap-builder
python scripts/plan_features.py examples/sample_features.json roadmap.json
python scripts/build_xlsx.py roadmap.json roadmap.xlsx
python scripts/build_pptx.py roadmap.json roadmap.pptx
```

**Из текстового списка или выгрузки Jira** — сперва конвертер в `features.json`:

```bash
python scripts/text_to_features.py features.txt features.json --start 2026-07-20 \
    --capacity analytics:2,dev:3,testing:2
python scripts/jira_to_features.py epics.csv features.json --start 2026-07-20 \
    --capacity analytics:2,dev:3,testing:2
```

Полный гид по входным данным и влиянию `capacity` на сроки —
[`roadmap-builder/references/input-guide.md`](roadmap-builder/references/input-guide.md).

## Структура репозитория

```
roadmap-builder/
├── SKILL.md              описание скилла и правила построения
├── references/           гид по входу и JSON-схемы
├── scripts/              планировщик, конвертеры, рендереры xlsx/pptx
├── examples/             рабочие примеры входных файлов
└── tests/                pytest на планировщик и общий модуль
```

## Тесты

```bash
cd roadmap-builder && python -m pytest
```

## Лицензия

[MIT](LICENSE)
