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
   (самая ранняя `startDate`, округлённая до понедельника; переопределяется
   конфигом `semester_start`). Номер недели — целое от 1;
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
│   └── gstu_schedule/
│       ├── __main__.py            # запуск: python3 -m gstu_schedule
│       ├── cli.py                 # аргументы командной строки
│       ├── config.py              # загрузка конфига (config.json)
│       ├── fetcher.py             # HTTP-запрос к API
│       ├── models.py              # модели и парсер ответа API
│       ├── engine.py              # фильтры по дате/неделе и подгруппе
│       ├── formatters.py          # вывод: консоль, Markdown, JSON
│       └── app.py                 # оркестрация
├── config.json                    # конфигурация по умолчанию
└── README.md
```

## Требования

- Python 3.9+ (используются только стандартные библиотеки; установка пакетов
  не требуется).

## Запуск

Из корня проекта:

```bash
# весь вывод в консоль — неделя, содержащая сегодняшний день (если группа в конфиге)
PYTHONPATH=src python3 -m gstu_schedule

# расписание группы
PYTHONPATH=src python3 -m gstu_schedule --type group --group iti-31

# расписание преподавателя
PYTHONPATH=src python3 -m gstu_schedule --type teacher --teacher avakyan-s

# расписание аудитории
PYTHONPATH=src python3 -m gstu_schedule --type classroom --classroom 2-306

# то же без переменной окружения
python3 src/main.py --group iti-31
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
  вычисляется автоматически как понедельник недели самой ранней `startDate`
  из данных API. Укажите вручную, если чётность/нечётность недель
  не совпадает с реальным расписанием.

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
PYTHONPATH=src python3 -m gstu_schedule \
  --lesson-format "{number}) {time} {subject_full} [{type}] — {teachers}, ауд. {rooms}"
```

Шаблон с `{{` и `}}` позволяет выводить фигурные скобки. Неизвестные
плейсхолдеры сообщаются как ошибка и не выполняются.

Параметры командной строки перекрывают значения конфига.

## Примеры использования

```bash
# Группа: день по дате, обе подгруппы
PYTHONPATH=src python3 -m gstu_schedule --type group --group iti-31 --view date

# Группа: вся неделя по умолчанию из конфига
PYTHONPATH=src python3 -m gstu_schedule

# День по дате, только 1-я подгруппа
PYTHONPATH=src python3 -m gstu_schedule --group iti-31 --view date --date 2026-09-16 --subgroup 1

# Преподаватель через эндпоинт
PYTHONPATH=src python3 -m gstu_schedule --teacher avakyan-s

# Аудитория через эндпоинт
PYTHONPATH=src python3 -m gstu_schedule --classroom 2-306

# Неделя с 21.09.2026 (нечётная), сохранить .md и .json
PYTHONPATH=src python3 -m gstu_schedule --group iti-31 --date 2026-09-21 --format all

# Только 2-я подгруппа, только markdown
PYTHONPATH=src python3 -m gstu_schedule --group iti-31 --subgroup 2 --format md

# То же, но в файл с произвольным именем
PYTHONPATH=src python3 -m gstu_schedule --group iti-31 --subgroup 2 --format md --output-file my_schedule

# Только лекции и лабораторные (неделя по умолчанию)
PYTHONPATH=src python3 -m gstu_schedule --lesson-type лек --lesson-type лаб

# Только занятия без типа (физкультура, кураторский час)
PYTHONPATH=src python3 -m gstu_schedule --lesson-type none

# Только занятия, где в тексте есть "Разработка приложений" (регистронезависимо)
PYTHONPATH=src python3 -m gstu_schedule --regex "разработка приложений"

# Занятия у преподавателя Иванова или в аудитории 2-3xx
PYTHONPATH=src python3 -m gstu_schedule --regex "иванов" --regex "2-3\d\d"

# Regex + фильтр по типу: лабораторные по "Трехмерное моделирование" и "Двумерная визуализация"
PYTHONPATH=src python3 -m gstu_schedule --lesson-type лаб --regex "\b(трех|дву)\w*"

# Комбинация фильтров: 1-я подгруппа, только практические, свой формат пары
PYTHONPATH=src python3 -m gstu_schedule --group iti-31 --subgroup 1 --lesson-type пр \
  --lesson-format "{time} | {subject_full} | {groups} | {teachers}"

# Сохранить JSON в другой каталог
PYTHONPATH=src python3 -m gstu_schedule --format json --output-dir ./result

# Другая группа
PYTHONPATH=src python3 -m gstu_schedule --group itp-31

# Свой URL API (тип определяется автоматически по пути)
PYTHONPATH=src python3 -m gstu_schedule \
  --api-url "https://sc.gstu.by/api/schedules/teacher/avakyan-s"

PYTHONPATH=src python3 -m gstu_schedule \
  --api-url "https://sc.gstu.by/api/schedules/classroom/2-306"

# Создать шаблон конфига и продолжить работу через config.json
PYTHONPATH=src python3 -m gstu_schedule --write-default-config
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

## Тесты

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```