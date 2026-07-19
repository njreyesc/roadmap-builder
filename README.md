# roadmap-builder

Строит **дорожную карту (roadmap)** сразу в двух форматах — **Excel (`.xlsx`)** и
**PowerPoint (`.pptx`)** — из плана работ по спринтам или из списка фич с оценками
(аналитика / разработка / тестирование).

Главное: **писать код не нужно.** Это [Agent Skill](roadmap-builder/SKILL.md) для
Claude Code — вы даёте файл и пишете Клоду простые фразы, а он всё делает сам.

## Как пользоваться (без кода)

Полная простая инструкция — **[ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md)**. Коротко:

1. **Установи** (один раз) — напишите Клоду:
   > Установи roadmap-builder
2. **Дай данные** — приложите файл (Excel-план, выгрузку Jira) или продиктуйте
   список фич словами.
3. **Запусти** — напишите:
   > Сделай roadmap из этого файла

Получите два файла: `roadmap.xlsx` и `roadmap.pptx`.

**Менять — тоже словами**, файлы руками не правьте:

> Сдвинь фичу «Оплата» на две недели вперёд
> Добавь фичу «Уведомления»: аналитика 1 неделя, разработка 2 спринта
> Перенеси веху «Выход на КО» на 15 сентября

## Что умеет

- Два входа: **Excel-план работ** (спринты в колонках, задачи в ячейках) или
  **список фич с оценками** (человеко-дни / недели / спринты, зависимости, вехи).
- Раскладывает фазы фич по неделям с учётом пропускной способности команды
  (`capacity`), сам считает сдвиги, если что-то не влезает.
- Понимает текстовый список фич и CSV-выгрузку эпиков из Jira.
- Собирает оба файла из одного источника, поэтому Excel и PowerPoint всегда
  совпадают.
- В карте: сетка месяц→недели, дорожки по фичам, полосы работ, вехи-ромбы,
  выноски, линия «сегодня», флажки старта и финиша.

---

## Для разработчиков (запуск вручную)

Скрипты работают и как обычные CLI-утилиты на Python — если хочется собрать
roadmap без Клода.

**Установка** (Python 3.10+):

```bash
pip install -r requirements.txt
```

**Из списка фич с оценками:**

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

### Структура репозитория

```
roadmap-builder/
├── SKILL.md              описание скилла и правила построения
├── references/           гид по входу и JSON-схемы
├── scripts/              планировщик, конвертеры, рендереры xlsx/pptx
├── examples/             рабочие примеры входных файлов
└── tests/                pytest на планировщик и общий модуль
```

### Тесты

```bash
cd roadmap-builder && python -m pytest
```

## Лицензия

[MIT](LICENSE)
