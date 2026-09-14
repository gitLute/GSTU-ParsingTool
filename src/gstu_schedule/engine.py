"""Логика выбора занятий: фильтры по дате/неделе и подгруппе."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from .models import DAY_ORDER, WEEK_ALL, WEEK_EVEN, WEEK_ODD, ScheduleItem, Entity

# Число недель учитывается от старта семестра; weekType ODD/EVEN определяют чётность.
WEEKDAYS_PERIOD = dt.timedelta(days=7)


def term_start(items: list[ScheduleItem]) -> dt.date:
    """Понедельник первой недели семестра.

    Берётся самая ранняя startDate среди занятий, затем понедельник
    недели, в которую она попадает (неделя 1 считается с понедельника).
    При необходимости можно задать вручную через конфиг ``semester_start``.
    """
    earliest = min((it.start_date for it in items), default=dt.date.today())
    return earliest - dt.timedelta(days=earliest.weekday())


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


def week_days(value: dt.date) -> list[dt.date]:
    """Все дни недели (Пн..Вс), содержащие ``value``."""
    monday = value - dt.timedelta(days=value.weekday())
    return [monday + dt.timedelta(days=i) for i in range(7)]


def scheduled_days(
    items: list[ScheduleItem],
    dates: list[dt.date],
    subgroup_number: Optional[int],
    term_start_date: dt.date,
) -> dict[dt.date, list[ScheduleItem]]:
    """Раскладывает занятия по датам с учётом фильтров."""
    result: dict[dt.date, list[ScheduleItem]] = {}
    for day in dates:
        lessons = [
            it
            for it in items
            if item_applies_on(it, day, term_start_date)
            and subgroup_matches(it, subgroup_number)
        ]
        lessons.sort(key=lambda it: (it.lesson_number, it.start_time))
        result[day] = lessons
    return result
