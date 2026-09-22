#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP-сервер gstu-schedule: расписание занятий ГГТУ через LLM.

Полноценный сервер Model Context Protocol поверх парсера GSTU-ParsingTool.
Позволяет агентам:

  - получать расписание группы/преподавателя/аудитории на неделю или
    конкретную дату с фильтрами по подгруппе, типу занятия и регулярным
    выражениям (get_schedule);
  - искать сущности через автоподбор /autocomplete и получать их slug
    (search_entities) для последующей подстановки в get_schedule.

Данные загружаются с публичного API https://sc.gstu.by и возвращаются
структурированным JSON: дни недели с занятиями (время, предмет, тип,
группы, преподаватели, аудитории).
"""

import argparse
import datetime as dt
import os
import sys
import threading
import time

# PPID, зафиксированный при импорте модуля: родитель — сервис opencode,
# запустивший процесс. Захват на раннем этапе важен: сторож должен знать
# исходного родителя, а не subreaper'а, к которому процесс будет
# переподчинён после смерти родителя.
_INIT_PPID = os.getppid()

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from gstu_schedule.engine import (
    merge_duplicate_lessons,
    scheduled_days,
    term_start,
    validate_regex_filters,
    week_days,
    week_number,
)
from gstu_schedule.fetcher import (
    DEFAULT_API_BASE_URL,
    SCHEDULE_KINDS,
    build_api_url,
    fetch_autocomplete,
    fetch_schedule,
)
from gstu_schedule.formatters import build_days_data, validate_lesson_template
from gstu_schedule.models import Entity, parse_autocomplete, parse_payload

SERVER_NAME = "gstu-schedule"
SERVER_VERSION = "1.0.0"

instructions = (
    "Сервер отдаёт расписание занятий Гомельского государственного "
    "технического университета им. П. О. Сухого через публичное API "
    "sc.gstu.by. Типовой сценарий: search_entities (поиск группы, "
    "преподавателя или аудитории, например 'iti' или 'авакян') -> "
    "get_schedule со slug из результата. Расписание можно фильтровать "
    "по подгруппе, типу занятия и регулярным выражениям, а также "
    "запрашивать на конкретную дату или неделю."
)

mcp = FastMCP(
    SERVER_NAME,
    instructions=instructions,
)


# ---------------------------------------------------------------------------
# Хелперы.
# ---------------------------------------------------------------------------


def _title(ref: dt.date, start: dt.date, view: str) -> str:
    """Заголовок периода: неделя (Пн–Вс) или одна дата, с чётностью недели."""
    wn = week_number(ref, start)
    parity = "нечётная" if wn % 2 else "чётная"
    if view == "date":
        return f"Дата: {ref.isoformat()} (нед. {wn}, {parity})"
    monday = ref - dt.timedelta(days=ref.weekday())
    sunday = monday + dt.timedelta(days=6)
    return f"Неделя: {monday.isoformat()} – {sunday.isoformat()} (нед. {wn}, {parity})"


def _entity_dict(entity: Entity) -> dict:
    """Краткое описание сущности (группы/преподавателя/аудитории)."""
    return {
        "slug": entity.slug,
        "name": entity.display_name,
        "course": entity.course,
        "faculty": entity.faculty,
        "facultyShort": entity.faculty_short,
        "cafedra": entity.cafedra,
        "cafedraShort": entity.cafedra_short,
        "specialty": {"name": entity.specialty_name, "code": entity.specialty_code},
        "subgroups": entity.subgroups,
    }


def _check_subgroup(subgroup: int | None) -> None:
    if subgroup is not None and subgroup < 1:
        raise ToolError("subgroup должен быть положительным числом")


def _parse_date(value: str | None, field: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ToolError(
            f"некорректная дата {field}={value!r} (ожидается YYYY-MM-DD)"
        ) from None


def build_schedule_data(
    schedule_type: str,
    slug: str,
    date: str | None = None,
    view: str = "week",
    subgroup: int | None = None,
    lesson_types: list[str] | None = None,
    regex_filter: list[str] | None = None,
    semester_start: str | None = None,
    lesson_format: str | None = None,
) -> dict:
    """Загружает расписание с API и возвращает структурированные данные.

    Общая логика инструмента ``get_schedule``, вынесена отдельно для
    тестирования без MCP-транспорта. Ошибки — ``ToolError``.
    """
    if schedule_type not in SCHEDULE_KINDS:
        raise ToolError(
            f"schedule_type должен быть одним из: {', '.join(SCHEDULE_KINDS)}"
        )
    if view not in ("week", "date"):
        raise ToolError("view должен быть 'week' или 'date'")
    slug = (slug or "").strip()
    if not slug:
        raise ToolError("укажите непустой slug сущности")
    _check_subgroup(subgroup)

    ref = _parse_date(date, "date") or dt.date.today()
    t_start = _parse_date(semester_start, "semester_start")

    api_url = build_api_url(DEFAULT_API_BASE_URL, schedule_type, slug)
    payload = fetch_schedule(api_url)
    # Для расписания группы важна привязка к подгруппам; для преподавателя
    # и аудитории — нет (занятия приходят сразу со списком групп).
    group_slug = slug if schedule_type == "group" else ""
    entity, items = parse_payload(payload, group_slug)
    if not items:
        raise ToolError("Расписание пустое — занятий не найдено.")

    term = t_start or term_start(items)

    unknown = validate_lesson_template(lesson_format)
    if unknown:
        raise ToolError(
            "неизвестные плейсхолдеры в lesson_format: " + ", ".join(unknown)
        )
    regex_errors = validate_regex_filters(regex_filter)
    if regex_errors:
        raise ToolError("некорректные регулярные выражения: " + "; ".join(regex_errors))

    dates = week_days(ref) if view == "week" else [ref]
    title = _title(ref, term, view)

    scheduled = scheduled_days(items, dates, subgroup, term, lesson_types, regex_filter)
    scheduled = merge_duplicate_lessons(scheduled)

    return {
        "schedule": {"type": schedule_type, "slug": slug},
        "entity": _entity_dict(entity),
        "scope": {
            "title": title,
            "view": view,
            "date": ref.isoformat(),
            "subgroup": subgroup,
            "lessonTypes": list(lesson_types or []),
            "regexFilter": list(regex_filter or []),
        },
        "days": build_days_data(entity, dates, scheduled, lesson_format),
    }


def build_search_data(query: str) -> dict:
    """Автоподбор по /autocomplete (общая логика инструмента ``search_entities``)."""
    query = (query or "").strip()
    if not query:
        raise ToolError("укажите непустой запрос")
    payload = fetch_autocomplete(query)
    if not payload.get("success", True):
        raise ToolError("API вернул success=false")
    result = parse_autocomplete(payload)

    return {
        "query": query,
        "total": result.total,
        "has_more": result.has_more,
        "groups": [
            {
                "slug": g.slug,
                "name": g.name,
                "course": g.course,
                "specialty": g.specialty_name,
                "cafedra": g.cafedra_short,
                "faculty": g.faculty_short,
                "subgroupCount": g.subgroup_count,
            }
            for g in result.groups
        ],
        "teachers": [
            {
                "slug": t.slug,
                "fullName": t.full_name,
                "shortName": t.short_name,
                "position": t.position,
                "cafedra": t.cafedra_short,
                "faculty": t.faculty_short,
            }
            for t in result.teachers
        ],
        "classrooms": [
            {
                "slug": c.slug,
                "name": c.name,
                "roomNumber": c.room_number,
                "building": c.building,
                "floor": c.floor,
                "capacity": c.capacity,
                "type": c.room_type,
                "cafedra": c.cafedra_short,
                "faculty": c.faculty_short,
            }
            for c in result.classrooms
        ],
    }


# ---------------------------------------------------------------------------
# Инструменты.
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Расписание занятий ГГТУ на неделю или конкретную дату. "
        "schedule_type: 'group' (группа), 'teacher' (преподаватель), 'classroom' "
        "(аудитория); slug — идентификатор сущности, например 'iti-31', 'avakyan-s', "
        "'2-306' (получить через search_entities). date — опорная дата YYYY-MM-DD "
        "(по умолчанию сегодня); view: 'week' — неделя вокруг даты, 'date' — одна "
        "дата. subgroup — номер подгруппы 1/2/...; lesson_types — фильтр по типу "
        "занятия (лаб, лек, пр, ...; 'none' — занятия без типа); regex_filter — "
        "регулярные выражения по тексту занятия (предмет, преподаватель, аудитория; "
        "подходит хотя бы одно). semester_start — понедельник первой недели семестра "
        "(по умолчанию вычисляется по данным API). lesson_format — шаблон строки "
        "занятия с плейсхолдерами {number} {time} {subject} {subject_full} {type} "
        "{type_full} {groups} {teachers} {rooms} {week}. Возвращает дни с занятиями."
    )
)
def get_schedule(
    schedule_type: str = "group",
    slug: str = "",
    date: str | None = None,
    view: str = "week",
    subgroup: int | None = None,
    lesson_types: list[str] | None = None,
    regex_filter: list[str] | None = None,
    semester_start: str | None = None,
    lesson_format: str | None = None,
) -> dict:
    """Расписание группы/преподавателя/аудитории с фильтрами."""
    try:
        return build_schedule_data(
            schedule_type=schedule_type,
            slug=slug,
            date=date,
            view=view,
            subgroup=subgroup,
            lesson_types=lesson_types,
            regex_filter=regex_filter,
            semester_start=semester_start,
            lesson_format=lesson_format,
        )
    except ToolError:
        raise
    except (RuntimeError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise ToolError(f"некорректный ответ API: {exc}") from exc


@mcp.tool(
    description=(
        "Поиск групп, преподавателей и аудиторий через автоподбор API. "
        "query — подстрока имени или номера, например 'iti', 'авакян', '306'. "
        "Возвращает найденные сущности с slug для подстановки в get_schedule "
        "(у групп ещё курс и специальность, у преподавателей — должность и "
        "кафедра, у аудиторий — корпус, этаж, вместимость и тип)."
    )
)
def search_entities(query: str) -> dict:
    """Автоподбор сущностей по подстроке."""
    try:
        return build_search_data(query)
    except ToolError:
        raise
    except (RuntimeError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise ToolError(f"некорректный ответ API: {exc}") from exc


# ---------------------------------------------------------------------------
# Точка входа.
# ---------------------------------------------------------------------------


def spawn_parent_watchdog(interval=2.0):
    """Фоновый поток, завершающий процесс, если умер процесс-родитель.

    Локальные MCP-серверы opencode запускает как детей фонового сервиса
    (`opencode serve --service`). При штатном отключении транспорта сервер
    завершается сам (EOF на stdin), но если родитель погибает без закрытия
    каналов (kill -9, падение сервиса), процесс остаётся «сиротой» и висит
    в системе. Сторож следит за сменой PPID: осиротевший процесс
    переподчиняется init/subreaper'у, и его текущий PPID отличается от
    исходного — тогда сторож завершает сервер принудительно.

    Запущенный вручную (родитель — init, PPID <= 1) сервер не трогаем.
    """
    initial = _INIT_PPID
    if initial <= 1:
        return

    def _watch():
        while True:
            time.sleep(interval)
            if os.getppid() != initial:
                os._exit(0)

    threading.Thread(target=_watch, daemon=True).start()


def main(argv=None):
    """Запуск MCP-сервера (по умолчанию транспорт stdio)."""
    ap = argparse.ArgumentParser(
        prog="gstu-schedule-mcp-server",
        description="MCP-сервер расписания занятий ГГТУ.",
    )
    ap.add_argument(
        "--stdio",
        action="store_true",
        help="транспорт stdio (установлен по умолчанию; флаг для совместимости)",
    )
    ap.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="транспорт MCP (по умолчанию stdio)",
    )
    args = ap.parse_args(argv)

    if args.transport == "sse":
        print(
            "SSE-транспорт: http://127.0.0.1:8765/sse "
            "(точный адрес зависит от запуска mcp.run)",
            file=sys.stderr,
        )
        mcp.run(transport="sse")
    else:
        # Сторож родителя: если сервис opencode, породивший этот процесс,
        # завершится, сервер закроется сам и не останется «сиротой».
        spawn_parent_watchdog()
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
