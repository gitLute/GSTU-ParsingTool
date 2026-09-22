# GSTU-ParsingTool

[![Python CI](https://github.com/gitLute/GSTU-ParsingTool/actions/workflows/python-ci.yml/badge.svg)](https://github.com/gitLute/GSTU-ParsingTool/actions/workflows/python-ci.yml)

Консольная утилита для получения и форматирования расписания занятий
Гомельского государственного технического университета им. П. О. Сухого
через публичное API (`https://sc.gstu.by`).

Поддерживаются три типа расписания:

| Тип | Эндпоинт | Пример |
|-----|----------|--------|
| Группа | `…/api/schedules/group/{slug}` | `group/iti-31` |
| Преподаватель | `…/api/schedules/teacher/{slug}` | `teacher/avakyan-s` |
| Аудитория | `…/api/schedules/classroom/{room}` | `classroom/2-306` |

## Краткое описание алгоритма

1. **Загрузка.** Приложение выполняет HTTP GET к API-ссылке вида
   `https://sc.gstu.by/api/schedules/{type}/{slug}` (модуль `fetcher.py`).
   Ответ — JSON: запись `data.entity` содержит описание сущности (группы,
   преподавателя или аудитории), `data.scheduleItems` — занятия.
2. **Разбор.** Каждое занятие превращается в датакласс `ScheduleItem`
   (`models.py`): день недели, тип недели (`ALL`/`ODD`/`EVEN`), номер пары,
   время начала/конца, период действия, предмет, тип занятия, преподаватели,
   аудитории. По полю `groups[].subgroups[]` определяется, к какой подгруппе
   относится занятие:
   - `subgroups` — занятие только для указанных подгрупп;
   - группа без подгрупп — занятие для всей группы;
   - записи других групп (или их отсутствие) — совместное занятие потока.
3. **Выборка** (`engine.py`). Вычисляется понедельник первой недели семестра
   (понедельник недели, которая чаще всего встречается среди `startDate`
   занятий; переопределяется конфигом `semester_start`). Номер недели — целое от 1;
   `ODD`/`EVEN` соответствуют нечётной/чётной неделе. Для даты проверяются:
   попадание в период `startDate–endDate`, совпадение дня недели и чётности
   недели. Параллельно применяется фильтр подгруппы: выбранная подгруппа не
   видит занятия чужих подгрупп, но видит занятия всей группы. Для расписаний
   аудиторий и преподавателей одинаковые занятия (один предмет, преподаватель,
   время, аудитория), пришедшие отдельными записями на каждую группу,
   объединяются в одну пару со списком групп.
4. **Форматирование** (`formatters.py`). Подготовленное расписание выводится
   в консоль или сохраняется в `.md`/`.json`. В заголовке указывается, чьё это
   расписание: группы, преподавателя или аудитории.
5. **Управление** (`config.py`, `cli.py`). Входные данные задаются в
   `config.json` и/или параметрами командной строки (параметры имеют приоритет).

## Структура проекта

```
GSTU-ParsingTool/
├── src/
│   ├── main.py                    # запуск: python3 src/main.py
│   ├── gstu_schedule/
│   │   ├── __main__.py            # запуск: python3 -m gstu_schedule
│   │   ├── cli.py                 # аргументы командной строки
│   │   ├── config.py              # загрузка конфига (config.json)
│   │   ├── fetcher.py             # HTTP-запрос к API
│   │   ├── models.py              # модели и парсер ответа API
│   │   ├── engine.py              # фильтры по дате/неделе и подгруппе
│   │   ├── formatters.py          # вывод: консоль, Markdown, JSON
│   │   └── app.py                 # оркестрация
│   └── gstu_schedule_mcp/
│       ├── __main__.py            # запуск: python3 -m gstu_schedule_mcp
│       └── server.py              # MCP-сервер (FastMCP)
├── scripts/
│   └── selftest.py                # smoke-тест MCP-сервера (stdio + реальный API)
├── pyproject.toml                 # сборка/установка пакета (incl. MCP-сервера)
├── config.json                    # конфигурация по умолчанию
└── README.md
```

## Требования

- Python 3.9+ (используются только стандартные библиотеки; установка пакетов
  при запуске не требуется, для сборки бинарника нужен только `pyinstaller`).

## Компиляция в бинарный файл

Проект собирается в один исполняемый файл через
[PyInstaller](https://pyinstaller.org/). Так как используются только модули
стандартной библиотеки, дополнительные `--hidden-import` не требуются.
Из корня проекта:

```bash
pip install pyinstaller
pyinstaller --onefile --clean --name gstu-parsing-tool src/main.py
```

Готовый бинарник появляется в каталоге `dist/`:

- `dist/gstu-parsing-tool` — Linux/macOS;
- `dist/gstu-parsing-tool.exe` — Windows.

## Запуск

После сборки бинарник запускается из корня проекта напрямую — без
`PYTHONPATH`, `python3` и установки пакетов:

```bash
# весь вывод в консоль — неделя, содержащая сегодняшний день (если группа в конфиге)
gstu-parsing-tool

# расписание группы
gstu-parsing-tool --type group --group iti-31

# расписание преподавателя
gstu-parsing-tool --type teacher --teacher avakyan-s

# расписание аудитории
gstu-parsing-tool --type classroom --classroom 2-306
```

### Параметры командной строки

| Параметр | Назначение |
|----------|-----------|
| `--config PATH` | путь к конфигу (по умолчанию `config.json`) |
| `--type group\|teacher\|classroom` | тип расписания (стандартная выдача) |
| `--group SLUG` | группа, например `iti-31` |
| `--teacher SLUG` | преподаватель, например `avakyan-s` |
| `--classroom ROOM` | аудитория, например `2-306` |
| `--api-url URL` | полный URL API (перекрывает `api_base_url`+`type`) |
| `--search QUERY` | поиск по autocomplete (группы, преподаватели, аудитории); вместо показа расписания выводит список найденных сущностей |
| `--search-hints QUERY` | поиск по autocomplete: выводит только готовые команды (`--group SLUG`, `--teacher SLUG`, `--classroom ROOM`) |
| `--subgroup N` | номер подгруппы; без указания показываются обе |
| `--lesson-type ТИП` | тип занятия: `лаб`, `лек`, `пр`, …; можно несколько раз, `none` — без типа |
| `--regex PATTERN` | регулярное выражение для поиска по тексту занятия; можно несколько раз — подходит хотя бы одно |
| `--view week\|date` | формат показа: неделя или конкретная дата |
| `--date YYYY-MM-DD` | опорная дата (по умолчанию сегодня) |
| `--format console\|md\|json\|all` | формат вывода |
| `--lesson-format ШАБЛОН` | свой шаблон строки одного занятия (плейсхолдеры ниже) |
| `--output-dir PATH` | каталог для файлов вывода (по умолчанию `out/`) |
| `--output-file NAME` | имя файла вывода без расширения |
| `--write-default-config` | создать шаблон `config.json` и завершиться |

Параметры `--group`, `--teacher` и `--classroom` неявно задают тип
расписания, если `--type` не указан.

`--search` и `--search-hints` запрашивают один и тот же эндпоинт
`/autocomplete`, но выводят результат по-разному:

- `--search QUERY` — человекочитаемый список по категориям
  («Преподаватели», «Аудитории», «Группы»);
- `--search-hints QUERY` — только готовые команды для копирования
  (`--teacher avakyan-s   # Авакян Сергей Левонович`), удобно для подстановки
  в шелл/скрипты.

## Конфигурация (`config.json`)

```json
{
  "schedule_type": "group",
  "group": "iti-31",
  "teacher": null,
  "classroom": null,
  "api_base_url": "https://sc.gstu.by/api/schedules/",
  "api_url": null,
  "subgroup": null,
  "lesson_types": [],
  "regex_filter": null,
  "view": "week",
  "date": null,
  "semester_start": null,
  "output_format": "console",
  "lesson_format": null,
  "output_dir": "out",
  "output_file": null
}
```

- `schedule_type`: `"group"`, `"teacher"` или `"classroom"` — какая сущность
  показывается по умолчанию;
- `group` / `teacher` / `classroom`: slug выбранной сущности. Для выбранного
  `schedule_type` используется соответствующее поле: `group` → `group`,
  `teacher` → `teacher`, `classroom` → `classroom`;
- `subgroup`: `null` (обе), `1`, `2`, …;
- `lesson_types`: список коротких имён типов занятий (`["лаб", "лек"]`);
  пустой список — все типы; элемент `"none"` — занятия без типа;
- `regex_filter`: строка или список регулярных выражений; занятие
  показывается, если его текст (предмет, преподаватель, аудитория, группы)
  совпал хотя бы с одним шаблоном. Поиск регистронезависимый. `null` — без
  фильтра;
- `view`: `"week"` — неделя вокруг даты, `"date"` — одна дата;
- `date`: опорная дата, при `null` берётся сегодня;
- `semester_start`: понедельник первой недели семестра. При `null`
  вычисляется автоматически как понедельник недели, которая встречается
  чаще всего среди `startDate` занятий (мода) — устойчив к единичным
  «выбивающимся» записям прошлого периода в расписаниях аудиторий. Укажите
  вручную, если чётность/нечётность недель не совпадает с реальным
  расписанием.

### Свой формат пунктов занятий (`lesson_format`)

Поле конфига `lesson_format` или параметр `--lesson-format` задаёт шаблон
одной строки занятия. В консоли и Markdown каждая пара выводится по этому
шаблону (вместо встроенной вёрстки/таблицы), в JSON к каждой записи занятия
добавляется поле `formatted`.

Доступные плейсхолдеры:

| Плейсхолдер | Значение |
|-------------|----------|
| `{number}` | номер пары |
| `{start}`, `{end}` | начало / конец |
| `{time}` | `начало–конец` |
| `{subject}` | короткое название предмета |
| `{subject_full}` | полное название предмета |
| `{type}` | короткий тип занятия (лаб/лек/пр/—) |
| `{type_full}` | полное имя типа |
| `{groups}` | задействованные группы/подгруппы |
| `{teachers}` | преподаватели |
| `{rooms}` | аудитории |
| `{week}` | тип недели (ALL/ODD/EVEN) |

Пример:

```bash
gstu-parsing-tool \
  --lesson-format "{number}) {time} {subject_full} [{type}] — {teachers}, ауд. {rooms}"
```

Шаблон с `{{` и `}}` позволяет выводить фигурные скобки. Неизвестные
плейсхолдеры сообщаются как ошибка и не выполняются.

Параметры командной строки перекрывают значения конфига.

## Примеры использования

```bash
# Группа: день по дате, обе подгруппы
gstu-parsing-tool --type group --group iti-31 --view date

# Группа: вся неделя по умолчанию из конфига
gstu-parsing-tool

# День по дате, только 1-я подгруппа
gstu-parsing-tool --group iti-31 --view date --date 2026-09-16 --subgroup 1

# Преподаватель через эндпоинт
gstu-parsing-tool --teacher avakyan-s

# Аудитория через эндпоинт
gstu-parsing-tool --classroom 2-306

# Поиск преподавателя (автоподбор)
gstu-parsing-tool --search "авакян"

# Поиск аудитории по номеру
gstu-parsing-tool --search "306"

# Поиск группы (подстрока имени)
gstu-parsing-tool --search "iti"

# Поиск с выводом только готовых команд (для скриптов/подстановки)
gstu-parsing-tool --search-hints "авакян"

# Готовые команды удобно подставлять дальше:
gstu-parsing-tool $(gstu-parsing-tool --search-hints "306" | head -1)

# Неделя с 21.09.2026 (нечётная), сохранить .md и .json
gstu-parsing-tool --group iti-31 --date 2026-09-21 --format all

# Только 2-я подгруппа, только markdown
gstu-parsing-tool --group iti-31 --subgroup 2 --format md

# То же, но в файл с произвольным именем
gstu-parsing-tool --group iti-31 --subgroup 2 --format md --output-file my_schedule

# Только лекции и лабораторные (неделя по умолчанию)
gstu-parsing-tool --lesson-type лек --lesson-type лаб

# Только занятия без типа (физкультура, кураторский час)
gstu-parsing-tool --lesson-type none

# Только занятия, где в тексте есть "Разработка приложений" (регистронезависимо)
gstu-parsing-tool --regex "разработка приложений"

# Занятия у преподавателя Иванова или в аудитории 2-3xx
gstu-parsing-tool --regex "иванов" --regex "2-3\d\d"

# Regex + фильтр по типу: лабораторные по "Трехмерное моделирование" и "Двумерная визуализация"
gstu-parsing-tool --lesson-type лаб --regex "\b(трех|дву)\w*"

# Комбинация фильтров: 1-я подгруппа, только практические, свой формат пары
gstu-parsing-tool --group iti-31 --subgroup 1 --lesson-type пр \
  --lesson-format "{time} | {subject_full} | {groups} | {teachers}"

# Сохранить JSON в другой каталог
gstu-parsing-tool --format json --output-dir ./result

# Другая группа
gstu-parsing-tool --group itp-31

# Свой URL API (тип определяется автоматически по пути)
gstu-parsing-tool \
  --api-url "https://sc.gstu.by/api/schedules/teacher/avakyan-s"

gstu-parsing-tool \
  --api-url "https://sc.gstu.by/api/schedules/classroom/2-306"

# Создать шаблон конфига и продолжить работу через config.json
gstu-parsing-tool --write-default-config
```

Результат сохраняется в файлы `{slug}_sub{subgroup}_{view}_{date}.md` и
`.json` в каталоге `out/` (задаётся через `--output-dir`), где `{slug}` —
группа, преподаватель или аудитория. Если выбрана подгруппа, она попадает
в имя файла: `iti-31_sub1_week_2026-09-21.md`. При `--output-file NAME` имя
файла фиксируется.

### Формат одного пункта расписания

Каждое занятие содержит: время проведения (начало, конец, день недели),
название предмета, задействованные подгруппы, тип занятия (лек, лаб, пр, …),
преподавателя и аудиторию. В одно и то же время у разных подгрупп могут идти
разные занятия — такие пары выводятся отдельными строками/строками таблицы.
Для расписаний преподавателей и аудиторий одинаковые пары (один предмет,
преподаватель, время и аудитория) объединяются в одну запись со списком групп.

## MCP-сервер

Помимо консольной утилиты проект включает MCP-сервер (Model Context
Protocol) — модуль `gstu_schedule_mcp`. Через него LLM-агент (например,
opencode) получает расписание занятий напрямую:

- `get_schedule` — расписание группы/преподавателя/аудитории на неделю
  или конкретную дату с фильтрами по подгруппе, типу занятия и
  регулярным выражениям;
- `search_entities` — автоподбор сущностей по подстроке (группы,
  преподаватели, аудитории) с выдачей `slug` для подстановки.

Сервер переиспользует парсер и логику выбора занятий консольной утилиты
(`gstu_schedule`), поэтому результаты идентичны CLI: та же неделя,
чётность, объединение дублирующихся пар, фильтры.

### Установка

Пакет устанавливается в Python-venv для MCP-серверов
`/home/lute/.local/bin/MCP/PytnonVenv` (Python 3.10+, `mcp>=1.12`):

```bash
/home/lute/.local/bin/MCP/PytnonVenv/bin/pip install -e .
```

После установки появляется консольный скрипт:

```bash
/home/lute/.local/bin/MCP/PytnonVenv/bin/gstu-schedule-mcp-server --stdio
```

Пакет также можно запустить из исходников без установки:

```bash
PYTHONPATH=src python3 -m gstu_schedule_mcp --stdio
```

Сервер включает «сторож родителя»: если сервис opencode, породивший его,
умрёт без закрытия каналов (kill -9, падение сервиса), сервер заметит
смену PPID и завершится сам, не оставаясь «сиротой» в системе. При ручном
запуске сторож не мешает.

### Подключение к opencode

В `~/.config/opencode/opencode.json` в секцию `mcp.servers` добавляется:

```json
"gstu-schedule": {
  "type": "local",
  "command": [
    "/home/lute/.local/bin/MCP/PytnonVenv/bin/gstu-schedule-mcp-server",
    "--stdio"
  ]
}
```

После перезапуска opencode сервер доступен как `gstu-schedule`.

### Инструменты

| Инструмент | Назначение |
|---|---|
| `get_schedule` | расписание группы (`iti-31`), преподавателя (`avakyan-s`) или аудитории (`2-306`) на неделю/дату; фильтры: `subgroup`, `lesson_types` (лаб/лек/пр, `none` — без типа), `regex_filter`, `semester_start`; опциональный шаблон занятия `lesson_format` (`{number} {time} {subject} {subject_full} {type} {type_full} {groups} {teachers} {rooms} {week}`) |
| `search_entities` | поиск по автоподбору: подстрока имени/номера → сущности со `slug` для `get_schedule` |

### Примеры использования агентом

1. Найти группу по подстроке: `search_entities(query="iti")`.
2. Показать расписание на неделю: `get_schedule(schedule_type="group", slug="iti-31", view="week")`.
3. Один день только 1-й подгруппы: `get_schedule(schedule_type="group", slug="iti-31", view="date", date="2026-09-21", subgroup=1)`.
4. Лабораторные у преподавателя: `get_schedule(schedule_type="teacher", slug="avakyan-s", lesson_types=["лаб"])`.
5. Поиск аудитории по номеру и её расписание:
   `search_entities(query="306")` → `get_schedule(schedule_type="classroom", slug="2-306")`.

### Smoke-тест

Скрипт запускает сервер как stdio-процесс и проверяет оба инструмента
с реальным API:

```bash
/home/lute/.local/bin/MCP/PytnonVenv/bin/python scripts/selftest.py
```

Аргументы: `--type group|teacher|classroom`, `--slug`, `--date`, `--view`,
`--subgroup`, `--lesson-types`, `--regex`, `--format`, `--search`.

Юнит-тесты не требуют сети и проверяют построение данных на синтетических
ответах API (`tests/test_mcp_server.py`).

## Тесты

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```
