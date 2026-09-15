"""Модели данных и парсер ответа API расписания.

Формат ответа:

.. code-block:: json

    {
      "success": true,
      "data": {
        "entity": {
          "slug": "iti-31",
          "name": "ИТИ-31",
          "course": 3,
          "studyType": "FULL_TIME",
          "specialty": {"name": "...", "code": "6-05-0611-01"},
          "cafedra": "...", "faculty": "...",
          "subgroups": [{"slug": "iti-31-1", "subgroupNumber": 1}, ...]
        },
        "scheduleItems": [
          {
            "dayOfWeek": "TUESDAY",
            "weekType": "ALL",                // ALL | ODD | EVEN
            "lessonNumber": 1,
            "startTime": "08:20:00",
            "endTime": "09:45:00",
            "startDate": "2026-09-08",
            "endDate": "2026-12-28",
            "isOneTime": false,
            "subject": {"name": "...", "shortName": "..."},
            "lessonType": {"name": "Лабораторная работа", "shortName": "лаб"},  // nullable
            "teachers": [{"shortName": "..."}],
            "classrooms": [{"roomNumber": "2-309"}],
            "groups": [                          // nullable/absent
              {
                "slug": "iti-31",
                "name": "ИТИ-31",
                "subgroups": [{"subgroupNumber": 2, "slug": "iti-31-2"}]
              }
            ]
          }
        ],
        "metadata": {"totalCount": 34}
      }
    }

Порядок дней недели фиксирован (понедельник — первым).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Optional

DAY_ORDER = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]

DAY_ORDER_INDEX = {name: i for i, name in enumerate(DAY_ORDER)}

WEEK_ALL = "ALL"
WEEK_ODD = "ODD"
WEEK_EVEN = "EVEN"

# Как занятие относится к запрошенной группе.
SCOPE_SUBGROUPS = "subgroups"  # занятие только для части подгрупп
SCOPE_FULL = "full"  # занятие для всей группы
SCOPE_STREAM = "stream"  # совместное занятие с другими группами


def iso_to_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


_WS = re.compile(r"\s+")


def _clean(value: str) -> str:
    """Схлопывает лишние пробелы, приходящие из источника данных."""
    return _WS.sub(" ", value).strip()


@dataclass
class Entity:
    """Описание группы из ``data.entity``."""

    slug: str
    name: str
    course: int
    faculty: str
    faculty_short: str
    cafedra: str
    cafedra_short: str
    specialty_name: str
    specialty_code: str
    subgroups: list[int] = field(default_factory=list)
    # Короткое имя (для преподавателей — shortName).
    short_name: str = ""
    # Номер аудитории (для аудиторий — roomNumber).
    room_number: str = ""

    @property
    def display_name(self) -> str:
        """Человекочитаемое имя для заголовка расписания."""
        return self.name or self.short_name or self.room_number or self.slug


@dataclass
class ScheduleItem:
    """Одно занятие из ``data.scheduleItems``."""

    day_of_week: str
    week_type: str
    lesson_number: int
    start_time: str
    end_time: str
    start_date: dt.date
    end_date: dt.date
    is_one_time: bool
    subject_name: str
    subject_short_name: str
    lesson_type_name: Optional[str]
    lesson_type_short: Optional[str]
    teachers: list[str] = field(default_factory=list)
    classrooms: list[str] = field(default_factory=list)
    # Подгруппы запрошенной группы, для которых идёт занятие.
    # Пустой список => занятие для всей группы (или совместное).
    subgroup_numbers: list[int] = field(default_factory=list)
    # Как занятие относится к запрошенной группе.
    scope: str = SCOPE_FULL
    # Имена других групп в совместном занятии (для SCOPE_STREAM).
    other_groups: list[str] = field(default_factory=list)
    # Название запрошенной группы (например "ИТИ-31").
    group_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _entity_subgroups(entity_raw: dict[str, Any]) -> list[int]:
    subs = []
    for s in entity_raw.get("subgroups") or []:
        num = s.get("subgroupNumber")
        if num is not None:
            subs.append(int(num))
    return sorted(subs)


def parse_entity(entity_raw: dict[str, Any]) -> Entity:
    specialty = entity_raw.get("specialty") or {}
    return Entity(
        slug=entity_raw.get("slug", ""),
        name=entity_raw.get("name", "") or "",
        course=int(entity_raw.get("course", 0) or 0),
        faculty=entity_raw.get("faculty", "") or "",
        faculty_short=entity_raw.get("facultyShort", "") or "",
        cafedra=entity_raw.get("cafedra", "") or "",
        cafedra_short=entity_raw.get("cafedraShort", "") or "",
        specialty_name=specialty.get("name", "") or "",
        specialty_code=specialty.get("code", "") or "",
        subgroups=_entity_subgroups(entity_raw),
        short_name=entity_raw.get("shortName", "") or "",
        room_number=entity_raw.get("roomNumber", "") or "",
    )


def _teacher_names(teachers: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for t in teachers or []:
        names.append(t.get("shortName") or t.get("fullName") or "—")
    return names


def _room_numbers(classrooms: list[dict[str, Any]]) -> list[str]:
    return [c.get("roomNumber") or c.get("slug", "") for c in classrooms or []]


def _resolve_scope(
    item_raw: dict[str, Any], group_slug: str
) -> tuple[list[int], str, list[str]]:
    """Определяет, к каким подгруппам/группам относится занятие."""
    groups = item_raw.get("groups") or []
    if not groups:
        return [], SCOPE_FULL, []

    own: Optional[dict[str, Any]] = None
    others: list[str] = []
    for g in groups:
        if g.get("slug") == group_slug:
            own = g
        else:
            others.append(g.get("name") or g.get("slug", ""))
    if own is None:
        # Совместное занятие без явной записи нашей группы (потоковая лекция).
        return [], SCOPE_STREAM, others

    subs = [int(s["subgroupNumber"]) for s in own.get("subgroups") or []]
    subs = sorted(subs)
    if subs:
        return subs, SCOPE_SUBGROUPS, others
    return [], SCOPE_FULL, others


def _fallback_group_name(item_raw: dict[str, Any], group_name: str) -> str:
    """Возвращает имя группы для отображения.

    Если ``group_name`` пуст, берёт имя из первого элемента ``groups``
    в сырых данных (актуально для расписаний преподавателей, где
    ``entity.name`` может быть ``None``).
    """
    if group_name:
        return group_name
    for g in item_raw.get("groups") or []:
        name = g.get("name") or g.get("slug", "")
        if name:
            return name
    return ""


def parse_schedule_item(
    item_raw: dict[str, Any], group_slug: str, group_name: str = ""
) -> ScheduleItem:
    lesson_type = item_raw.get("lessonType")
    subgroup_numbers, scope, other_groups = _resolve_scope(item_raw, group_slug)
    resolved_name = _fallback_group_name(item_raw, group_name)
    return ScheduleItem(
        day_of_week=item_raw.get("dayOfWeek", "MONDAY"),
        week_type=item_raw.get("weekType", WEEK_ALL),
        lesson_number=int(item_raw.get("lessonNumber", 0) or 0),
        start_time=item_raw.get("startTime", ""),
        end_time=item_raw.get("endTime", ""),
        start_date=iso_to_date(item_raw["startDate"]),
        end_date=iso_to_date(item_raw["endDate"]),
        is_one_time=bool(item_raw.get("isOneTime", False)),
        subject_name=_clean(item_raw.get("subject", {}).get("name", "")),
        subject_short_name=_clean(item_raw.get("subject", {}).get("shortName", "")),
        lesson_type_name=lesson_type.get("name") if lesson_type else None,
        lesson_type_short=lesson_type.get("shortName") if lesson_type else None,
        teachers=_teacher_names(item_raw.get("teachers") or []),
        classrooms=_room_numbers(item_raw.get("classrooms") or []),
        subgroup_numbers=subgroup_numbers,
        scope=scope,
        other_groups=other_groups,
        group_name=resolved_name,
        raw=item_raw,
    )


def parse_payload(
    payload: dict[str, Any], group_slug: str
) -> tuple[Entity, list[ScheduleItem]]:
    if not payload.get("success", True):
        raise ValueError(f"API вернул success=false: {payload}")
    data = payload.get("data") or {}
    entity = parse_entity(data.get("entity") or {})
    items = [
        parse_schedule_item(it, group_slug, entity.name)
        for it in data.get("scheduleItems") or []
    ]
    return entity, items


# ---------------------------------------------------------------------------
# Модели автоподбора (autocomplete)
# ---------------------------------------------------------------------------


@dataclass
class AutocompleteGroup:
    slug: str
    name: str
    course: int
    specialty_name: str
    cafedra_short: str
    faculty_short: str
    subgroup_count: int


@dataclass
class AutocompleteTeacher:
    slug: str
    full_name: str
    short_name: str
    position: str
    cafedra_short: str
    faculty_short: str


@dataclass
class AutocompleteClassroom:
    slug: str
    name: str
    room_number: str
    building: str
    floor: int
    capacity: int
    room_type: str
    cafedra_short: str
    faculty_short: str


@dataclass
class AutocompleteResult:
    groups: list[AutocompleteGroup] = field(default_factory=list)
    teachers: list[AutocompleteTeacher] = field(default_factory=list)
    classrooms: list[AutocompleteClassroom] = field(default_factory=list)
    has_more: bool = False

    @property
    def total(self) -> int:
        return len(self.groups) + len(self.teachers) + len(self.classrooms)


def _parse_ac_teacher(raw: dict[str, Any]) -> AutocompleteTeacher:
    pos = raw.get("position") or {}
    caf = raw.get("cafedra") or {}
    fac = raw.get("faculty") or {}
    return AutocompleteTeacher(
        slug=raw.get("slug", ""),
        full_name=raw.get("fullName", ""),
        short_name=raw.get("shortName", ""),
        position=pos.get("shortName") or pos.get("name") or "",
        cafedra_short=caf.get("shortName") or "",
        faculty_short=fac.get("shortName") or "",
    )


def _parse_ac_classroom(raw: dict[str, Any]) -> AutocompleteClassroom:
    caf = raw.get("cafedra") or {}
    fac = raw.get("faculty") or {}
    return AutocompleteClassroom(
        slug=raw.get("slug", ""),
        name=raw.get("name", ""),
        room_number=raw.get("roomNumber") or raw.get("slug", ""),
        building=raw.get("building", ""),
        floor=int(raw.get("floor", 0) or 0),
        capacity=int(raw.get("capacity", 0) or 0),
        room_type=raw.get("type", ""),
        cafedra_short=caf.get("shortName") or "",
        faculty_short=fac.get("shortName") or "",
    )


def _parse_ac_group(raw: dict[str, Any]) -> AutocompleteGroup:
    return AutocompleteGroup(
        slug=raw.get("slug", ""),
        name=raw.get("name", ""),
        course=int(raw.get("course", 0) or 0),
        specialty_name=raw.get("specialtyName", ""),
        cafedra_short=raw.get("cafedraShortName", ""),
        faculty_short=raw.get("facultyShortName", ""),
        subgroup_count=int(raw.get("subgroupCount", 0) or 0),
    )


def parse_autocomplete(payload: dict[str, Any]) -> AutocompleteResult:
    """Разбирает ответ ``/autocomplete`` и возвращает ``AutocompleteResult``."""
    data = payload.get("data") or {}
    return AutocompleteResult(
        groups=[_parse_ac_group(g) for g in data.get("groups") or []],
        teachers=[_parse_ac_teacher(t) for t in data.get("teachers") or []],
        classrooms=[_parse_ac_classroom(c) for c in data.get("classrooms") or []],
        has_more=bool(data.get("hasMore", False)),
    )
