"""Форматирование выбранного расписания: консоль, Markdown, JSON."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Optional

from .engine import Entity, ScheduleItem
from .models import DAY_ORDER

DAYS_RU = {
    "MONDAY": "Понедельник",
    "TUESDAY": "Вторник",
    "WEDNESDAY": "Среда",
    "THURSDAY": "Четверг",
    "FRIDAY": "Пятница",
    "SATURDAY": "Суббота",
    "SUNDAY": "Воскресенье",
}

MONTHS_GEN = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def _short_time(value: str) -> str:
    """'08:20:00' -> '08:20'."""
    return value[:5] if len(value) >= 5 else value


def _subgroup_label(item: ScheduleItem) -> str:
    name = item.group_name or "группа"
    if item.subgroup_numbers:
        nums = ", ".join(str(n) for n in item.subgroup_numbers)
        label = f"{name}, подгр. {nums}"
        if item.other_groups:
            label += " + " + ", ".join(item.other_groups)
        return label
    if item.other_groups:
        members = [item.group_name] if item.group_name else []
        members += item.other_groups
        return "поток: " + ", ".join(m for m in members if m)
    return name


def _lesson_dict(item: ScheduleItem, day: dt.date) -> dict[str, Any]:
    return {
        "lessonNumber": item.lesson_number,
        "startTime": _short_time(item.start_time),
        "endTime": _short_time(item.end_time),
        "subject": item.subject_short_name or item.subject_name,
        "subjectFull": item.subject_name,
        "lessonType": item.lesson_type_short or "—",
        "lessonTypeFull": item.lesson_type_name or "—",
        "groups": _subgroup_label(item),
        "subgroupNumbers": list(item.subgroup_numbers),
        "scope": item.scope,
        "teachers": list(item.teachers),
        "classrooms": list(item.classrooms),
        "weekType": item.week_type,
    }


def build_days_data(
    entity: Entity,
    dates: list[dt.date],
    scheduled: dict[dt.date, list[ScheduleItem]],
) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    for day in dates:
        lessons = [_lesson_dict(it, day) for it in scheduled.get(day, [])]
        days.append(
            {
                "date": day.isoformat(),
                "dayOfWeek": _day_key(day),
                "dayName": DAYS_RU[_day_key(day)],
                "lessons": lessons,
            }
        )
    return days


def _date_ru(day: dt.date) -> str:
    return f"{day.day} {MONTHS_GEN[day.month]} {day.year}"


def _day_key(day: dt.date) -> str:
    return DAY_ORDER[day.weekday()]


# --------------------------------------------------------------------------- консоль


def _console_day_block(day: dt.date, lessons: list[ScheduleItem]) -> str:
    lines: list[str] = []
    lines.append("─" * 72)
    lines.append(f" {DAYS_RU[_day_key(day)]}, {_date_ru(day)}".upper())
    lines.append("─" * 72)
    if not lessons:
        lines.append(" Занятий нет")
        return "\n".join(lines)
    for it in lessons:
        type_tag = f"[{it.lesson_type_short}]" if it.lesson_type_short else "[—]"
        subject = it.subject_name
        head = (
            f" {it.lesson_number}. {_short_time(it.start_time)} – {_short_time(it.end_time)}  "
            f"{type_tag}  {subject}"
        )
        lines.append(head)
        groups = _subgroup_label(it)
        props = f"   Группы: {groups}"
        if it.teachers:
            props += f"   Преп.: {', '.join(it.teachers)}"
        if it.classrooms:
            props += f"   Ауд.: {', '.join(it.classrooms)}"
        lines.append(props)
        lines.append("")
    return "\n".join(lines)


def format_console(
    entity: Entity,
    dates: list[dt.date],
    scheduled: dict[dt.date, list[ScheduleItem]],
    subgroup_number: Optional[int],
    lesson_types: Optional[list[str]],
    title: str,
) -> str:
    lines: list[str] = []
    header = f"Расписание группы {entity.name}"
    lines.append(f"{'=' * 72}")
    lines.append(f" {header}")
    lines.append(f" {title}")
    if subgroup_number is not None:
        lines.append(f" Подгруппа: {subgroup_number}")
    if lesson_types:
        lines.append(f" Тип занятия: {', '.join(lesson_types)}")
    lines.append(f"{'=' * 72}")
    lines.append("")
    for day in dates:
        lines.append(_console_day_block(day, scheduled.get(day, [])))
        lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- md


def _md_day_section(day: dt.date, lessons: list[ScheduleItem]) -> str:
    lines: list[str] = []
    lines.append(f"## {DAYS_RU[_day_key(day)]}, {day.isoformat()}")
    lines.append("")
    if not lessons:
        lines.append("_Занятий нет_")
        lines.append("")
        return "\n".join(lines)
    lines.append(
        "| № | Время | Предмет | Тип | Подгруппы | Преподаватель | Аудитория |"
    )
    lines.append(
        "|---|-------|---------|-----|-----------|---------------|-----------|"
    )
    for it in lessons:
        type_val = it.lesson_type_short or "—"
        lines.append(
            f"| {it.lesson_number} | {_short_time(it.start_time)}–{_short_time(it.end_time)} "
            f"| {it.subject_name} | {type_val} | {_subgroup_label(it)} "
            f"| {', '.join(it.teachers) if it.teachers else '—'} "
            f"| {', '.join(it.classrooms) if it.classrooms else '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_md(
    entity: Entity,
    dates: list[dt.date],
    scheduled: dict[dt.date, list[ScheduleItem]],
    subgroup_number: Optional[int],
    lesson_types: Optional[list[str]],
    title: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# Расписание группы {entity.name}")
    lines.append("")
    lines.append(f"{title}")
    if subgroup_number is not None:
        lines.append(f"Подгруппа: **{subgroup_number}**")
    if lesson_types:
        lines.append(f"Тип занятия: **{', '.join(lesson_types)}**")
    lines.append("")
    for day in dates:
        lines.append(_md_day_section(day, scheduled.get(day, [])))
    return "\n".join(lines)


# ---------------------------------------------------------------------------- json


def format_json(
    entity: Entity,
    dates: list[dt.date],
    scheduled: dict[dt.date, list[ScheduleItem]],
    subgroup_number: Optional[int],
    lesson_types: Optional[list[str]],
    title: str,
) -> str:
    data: dict[str, Any] = {
        "group": {
            "slug": entity.slug,
            "name": entity.name,
            "course": entity.course,
            "faculty": entity.faculty,
            "facultyShort": entity.faculty_short,
            "cafedra": entity.cafedra,
            "cafedraShort": entity.cafedra_short,
            "specialty": {"name": entity.specialty_name, "code": entity.specialty_code},
            "subgroups": entity.subgroups,
        },
        "scope": {
            "title": title,
            "subgroup": subgroup_number,
            "lessonTypes": list(lesson_types or []),
        },
        "days": build_days_data(entity, dates, scheduled),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
