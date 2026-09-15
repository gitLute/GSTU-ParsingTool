"""Логика выбора занятий: фильтры по дате/неделе, подгруппе и регулярным выражениям."""

from __future__ import annotations

import copy
import datetime as dt
import re
from collections import Counter
from typing import Optional

from .models import (
    DAY_ORDER,
    SCOPE_FULL,
    WEEK_ALL,
    WEEK_EVEN,
    WEEK_ODD,
    ScheduleItem,
    Entity,
)

# Сопоставление по регулярным выражениям ведётся регистронезависимо.
REGEX_FLAGS = re.IGNORECASE

# Число недель учитывается от старта семестра; weekType ODD/EVEN определяют чётность.
WEEKDAYS_PERIOD = dt.timedelta(days=7)


def term_start(items: list[ScheduleItem]) -> dt.date:
    """Понедельник первой недели семестра.

    Берётся понедельник недели, которая встречается чаще всего среди
    ``startDate`` занятий (мода). Такой выбор устойчив к единичным
    «выбивающимся» записям из прошлого периода — например, к двухгодичному
    курсу в расписании аудитории, который не должен уводить счётчик недель
    на десятки недель назад. При необходимости можно задать вручную через
    конфиг ``semester_start``.
    """
    if not items:
        today = dt.date.today()
        return today - dt.timedelta(days=today.weekday())
    weeks = Counter(
        it.start_date - dt.timedelta(days=it.start_date.weekday()) for it in items
    )
    best = max(weeks.values())
    return min(monday for monday, count in weeks.items() if count == best)


def week_number(value: dt.date, term_start_date: dt.date) -> int:
    """Номер недели семестра (1-базируемый) для даты."""
    delta = (value - term_start_date).days
    return delta // 7 + 1


def item_applies_on(
    item: ScheduleItem, value: dt.date, term_start_date: Optional[dt.date] = None
) -> bool:
    """Проверяет, попадает ли занятие ``item`` на дату ``value``."""
    if not (item.start_date <= value <= item.end_date):
        return False
    if DAY_ORDER.index(item.day_of_week) != value.weekday():
        return False
    if item.week_type == WEEK_ALL:
        return True
    start = term_start_date if term_start_date is not None else item.start_date
    week = week_number(value, start)
    if item.week_type == WEEK_ODD:
        return week % 2 == 1
    if item.week_type == WEEK_EVEN:
        return week % 2 == 0
    return False


def subgroup_matches(item: ScheduleItem, subgroup_number: Optional[int]) -> bool:
    """Подгрупповая фильтрация.

    - Без выбранной подгруппы показываем все занятия.
    - Занятие без привязки к подгруппам считается занятием всей группы.
    """
    if subgroup_number is None:
        return True
    if not item.subgroup_numbers:
        return True
    return subgroup_number in item.subgroup_numbers


# Значение фильтра, соответствующее занятиям без типа (lessonType == null).
TYPE_NONE = "none"


def lesson_type_matches(item: ScheduleItem, lesson_types: list[str]) -> bool:
    """Фильтр по типу занятия (лаб, лек, пр, ...).

    - Пустой список => все занятия.
    - Значение "none" соответствует занятиям без типа (физкультура и т.п.).
    - Сравнение регистронезависимое, по короткому имени типа.
    """
    if not lesson_types:
        return True
    wanted = {str(t).strip().lower() for t in lesson_types if str(t).strip()}
    if not wanted:
        return True
    actual = (item.lesson_type_short or "").strip().lower()
    if not actual:
        actual = TYPE_NONE
    return actual in wanted


# ---------------------------------------------------------------------------
# Regex


def _item_haystack(item: ScheduleItem) -> str:
    """Все текстовые поля занятия, склеенные в одну строку для поиска."""
    parts: list[str] = [
        item.subject_name,
        item.subject_short_name,
        item.lesson_type_name or "",
        item.lesson_type_short or "",
        item.group_name,
        " ".join(str(n) for n in item.subgroup_numbers),
    ]
    parts.extend(item.teachers)
    parts.extend(item.classrooms)
    parts.extend(item.other_groups)
    return "\n".join(p for p in parts if p.strip())


def validate_regex_filters(patterns: list[str] | None) -> list[str]:
    """Проверяет корректность шаблонов. Возвращает список ошибок (пусто — ок)."""
    errors: list[str] = []
    for p in patterns or []:
        try:
            re.compile(p, REGEX_FLAGS)
        except re.error as exc:
            errors.append(f"{p!r}: {exc}")
    return errors


def regex_matches(item: ScheduleItem, patterns: list[str] | None) -> bool:
    """Попадает ли занятие хотя бы под один из шаблонов.

    - ``None`` / пустой список → пропускаем проверку (всё проходит);
    - несколько шаблонов связываются через OR (любой совпал — ок).
    """
    if not patterns:
        return True
    hay = _item_haystack(item)
    for p in patterns:
        if re.search(p, hay, REGEX_FLAGS):
            return True
    return False


def week_days(value: dt.date) -> list[dt.date]:
    """Все дни недели (Пн..Вс), содержащие ``value``."""
    monday = value - dt.timedelta(days=value.weekday())
    return [monday + dt.timedelta(days=i) for i in range(7)]


def scheduled_days(
    items: list[ScheduleItem],
    dates: list[dt.date],
    subgroup_number: Optional[int],
    term_start_date: dt.date,
    lesson_types: Optional[list[str]] = None,
    regex_filter: Optional[list[str]] = None,
) -> dict[dt.date, list[ScheduleItem]]:
    """Раскладывает занятия по датам с учётом фильтров."""
    lesson_types = lesson_types or []
    result: dict[dt.date, list[ScheduleItem]] = {}
    for day in dates:
        lessons = [
            it
            for it in items
            if item_applies_on(it, day, term_start_date)
            and subgroup_matches(it, subgroup_number)
            and lesson_type_matches(it, lesson_types)
            and regex_matches(it, regex_filter)
        ]
        lessons.sort(key=lambda it: (it.lesson_number, it.start_time))
        result[day] = lessons
    return result


def _merge_key(
    item: ScheduleItem,
) -> tuple[str, tuple[str, ...], str, str, str, str, tuple[str, ...]]:
    """Ключ для группировки дублирующихся занятий."""
    return (
        item.subject_name,
        tuple(sorted(item.teachers)),
        item.lesson_type_short or "",
        item.start_time,
        item.end_time,
        item.week_type,
        tuple(sorted(item.classrooms)),
    )


def merge_duplicate_lessons(
    scheduled: dict[dt.date, list[ScheduleItem]],
) -> dict[dt.date, list[ScheduleItem]]:
    """Объединяет дублирующиеся занятия (один предмет, преподаватель, время).

    Используется для расписаний аудиторий/преподавателей, где одно занятие
    приходит отдельным элементом для каждой группы.
    """
    merged: dict[dt.date, list[ScheduleItem]] = {}
    for day, lessons in scheduled.items():
        groups: dict[tuple, list[ScheduleItem]] = {}
        for it in lessons:
            key = _merge_key(it)
            groups.setdefault(key, []).append(it)
        day_items: list[ScheduleItem] = []
        for key, items in groups.items():
            if len(items) == 1:
                day_items.append(items[0])
                continue
            first = copy.copy(items[0])
            all_groups: list[str] = []
            for it in items:
                for name in [it.group_name] + it.other_groups:
                    if name and name not in all_groups:
                        all_groups.append(name)
            first.group_name = ", ".join(all_groups)
            first.scope = SCOPE_FULL
            first.subgroup_numbers = []
            first.other_groups = []
            day_items.append(first)
        day_items.sort(key=lambda it: (it.lesson_number, it.start_time))
        merged[day] = day_items
    return merged
