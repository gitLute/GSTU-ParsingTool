"""Тесты логики выбора занятий (неделя/подгруппа) и парсера."""

from __future__ import annotations

import datetime as dt
import unittest

from gstu_schedule.engine import (
    TYPE_NONE,
    item_applies_on,
    lesson_type_matches,
    subgroup_matches,
    term_start,
    week_number,
)
from gstu_schedule.formatters import (
    _subgroup_label,
    lesson_vars,
    render_lesson,
    validate_lesson_template,
)
from gstu_schedule.models import (
    WEEK_ALL,
    WEEK_EVEN,
    WEEK_ODD,
    SCOPE_FULL,
    SCOPE_STREAM,
    SCOPE_SUBGROUPS,
    ScheduleItem,
    parse_payload,
)


def item_factory(
    day: str,
    week_type: str,
    subgroup_numbers: list[int] | None = None,
    scope: str = SCOPE_FULL,
    lesson_type_short: str | None = "лаб",
    group_name: str = "ИТИ-31",
) -> ScheduleItem:
    numbers = subgroup_numbers or []
    scope = SCOPE_SUBGROUPS if numbers else scope
    return ScheduleItem(
        day_of_week=day,
        week_type=week_type,
        lesson_number=1,
        start_time="08:20:00",
        end_time="09:45:00",
        start_date=dt.date(2026, 9, 7),
        end_date=dt.date(2026, 12, 28),
        is_one_time=False,
        subject_name="Предмет",
        subject_short_name="П",
        lesson_type_name=None,
        lesson_type_short=lesson_type_short,
        subgroup_numbers=numbers,
        scope=scope,
        other_groups=[],
        group_name=group_name,
    )


SEMESTER = dt.date(2026, 9, 7)  # понедельник недели 1


class WeekNumberTests(unittest.TestCase):
    def test_exact_week_numbers(self):
        self.assertEqual(week_number(dt.date(2026, 9, 7), SEMESTER), 1)
        self.assertEqual(week_number(dt.date(2026, 9, 14), SEMESTER), 2)
        self.assertEqual(week_number(dt.date(2026, 9, 21), SEMESTER), 3)


class AppliesOnTests(unittest.TestCase):
    def test_all_week(self):
        item = item_factory("MONDAY", WEEK_ALL)
        self.assertTrue(item_applies_on(item, dt.date(2026, 9, 14), SEMESTER))
        self.assertFalse(item_applies_on(item, dt.date(2026, 9, 15), SEMESTER))

    def test_odd_even(self):
        odd = item_factory("WEDNESDAY", WEEK_ODD)
        even = item_factory("WEDNESDAY", WEEK_EVEN)
        w_odd = dt.date(2026, 9, 23)  # неделя 3, нечётная
        w_even = dt.date(2026, 9, 16)  # неделя 2, чётная
        self.assertTrue(item_applies_on(even, w_even, SEMESTER))
        self.assertFalse(item_applies_on(odd, w_even, SEMESTER))
        self.assertTrue(item_applies_on(odd, w_odd, SEMESTER))
        self.assertFalse(item_applies_on(even, w_odd, SEMESTER))

    def test_date_window(self):
        item = item_factory("MONDAY", WEEK_ALL)
        self.assertFalse(item_applies_on(item, dt.date(2026, 8, 3), SEMESTER))
        self.assertFalse(item_applies_on(item, dt.date(2027, 1, 4), SEMESTER))


class SubgroupTests(unittest.TestCase):
    def test_no_filter_shows_all(self):
        for subs in ([1], [2], []):
            self.assertTrue(
                subgroup_matches(item_factory("MONDAY", WEEK_ALL, subs), None)
            )

    def test_subgroup_filter(self):
        sub1 = item_factory("MONDAY", WEEK_ALL, [1])
        full = item_factory("MONDAY", WEEK_ALL)
        self.assertTrue(subgroup_matches(sub1, 1))
        self.assertFalse(subgroup_matches(sub1, 2))
        self.assertTrue(subgroup_matches(full, 1))


class ParseTests(unittest.TestCase):
    def test_parse_payload_scope(self):
        payload = {
            "success": True,
            "data": {
                "entity": {
                    "slug": "iti-31",
                    "name": "ИТИ-31",
                    "course": 3,
                    "studyType": "FULL_TIME",
                    "specialty": {"name": "ИС", "code": "6-05-0611-01"},
                    "subgroups": [{"slug": "iti-31-1", "subgroupNumber": 1}],
                },
                "scheduleItems": [
                    {
                        "dayOfWeek": "TUESDAY",
                        "weekType": "ALL",
                        "lessonNumber": 1,
                        "startTime": "08:20:00",
                        "endTime": "09:45:00",
                        "startDate": "2026-09-08",
                        "endDate": "2026-12-28",
                        "isOneTime": False,
                        "subject": {
                            "name": "Визуальные    средства",
                            "shortName": "ВС",
                        },
                        "lessonType": {
                            "name": "Лабораторная работа",
                            "shortName": "лаб",
                        },
                        "teachers": [{"shortName": "Иванов И.И."}],
                        "classrooms": [{"roomNumber": "2-309"}],
                        "groups": [
                            {
                                "slug": "iti-31",
                                "name": "ИТИ-31",
                                "course": 3,
                                "subgroups": [
                                    {"subgroupNumber": 2, "slug": "iti-31-2"}
                                ],
                            }
                        ],
                    }
                ],
                "metadata": {"totalCount": 1},
            },
        }
        entity, items = parse_payload(payload, "iti-31")
        self.assertEqual(entity.name, "ИТИ-31")
        self.assertEqual(entity.subgroups, [1])
        item = items[0]
        self.assertEqual(item.subgroup_numbers, [2])
        self.assertEqual(item.scope, SCOPE_SUBGROUPS)
        self.assertEqual(item.group_name, "ИТИ-31")
        self.assertEqual(item.subject_name, "Визуальные средства")
        self.assertEqual(item.week_type, WEEK_ALL)


class LessonTypeTests(unittest.TestCase):
    def test_no_filter_shows_all(self):
        lab = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лаб")
        none = item_factory("MONDAY", WEEK_ALL, lesson_type_short=None)
        self.assertTrue(lesson_type_matches(lab, []))
        self.assertTrue(lesson_type_matches(none, []))

    def test_match_by_short_name_case_insensitive(self):
        lab = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лаб")
        self.assertTrue(lesson_type_matches(lab, ["лаб"]))
        self.assertTrue(lesson_type_matches(lab, ["ЛАБ"]))
        self.assertFalse(lesson_type_matches(lab, ["лек"]))

    def test_multiple_types(self):
        item = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лек")
        self.assertTrue(lesson_type_matches(item, ["лаб", "лек"]))
        self.assertFalse(lesson_type_matches(item, ["лаб", "пр"]))

    def test_none_type(self):
        no_type = item_factory("MONDAY", WEEK_ALL, lesson_type_short=None)
        self.assertTrue(lesson_type_matches(no_type, [TYPE_NONE]))
        self.assertFalse(lesson_type_matches(no_type, ["лаб"]))


class LabelTests(unittest.TestCase):
    def test_full_group_shows_group_name(self):
        item = item_factory("MONDAY", WEEK_ALL, scope=SCOPE_FULL)
        self.assertEqual(_subgroup_label(item), "ИТИ-31")

    def test_subgroup_includes_group_name(self):
        item = item_factory(
            "MONDAY", WEEK_ALL, subgroup_numbers=[1], scope=SCOPE_SUBGROUPS
        )
        self.assertEqual(_subgroup_label(item), "ИТИ-31, подгр. 1")

    def test_stream_includes_main_group(self):
        item = item_factory("MONDAY", WEEK_ALL, scope=SCOPE_STREAM)
        item.other_groups = ["ИТП-31", "ИТД-31"]
        self.assertEqual(_subgroup_label(item), "поток: ИТИ-31, ИТП-31, ИТД-31")

    def test_stream_without_main_group_name(self):
        item = item_factory("MONDAY", WEEK_ALL, group_name="", scope=SCOPE_STREAM)
        item.other_groups = ["ИТП-31"]
        self.assertEqual(_subgroup_label(item), "поток: ИТП-31")


class LessonFormatTests(unittest.TestCase):
    def test_lesson_vars_fields(self):
        item = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лаб")
        item.teachers = ["Иванов И.И."]
        item.classrooms = ["2-305"]
        vars_map = lesson_vars(item)
        self.assertEqual(vars_map["time"], "08:20–09:45")
        self.assertEqual(vars_map["subject"], "П")
        self.assertEqual(vars_map["subject_full"], "Предмет")
        self.assertEqual(vars_map["type"], "лаб")
        self.assertEqual(vars_map["groups"], "ИТИ-31")
        self.assertEqual(vars_map["teachers"], "Иванов И.И.")
        self.assertEqual(vars_map["rooms"], "2-305")

    def test_render_lesson(self):
        item = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лек")
        template = "{start}-{end} {subject} [{type}] {groups}"
        self.assertEqual(render_lesson(item, template), "08:20-09:45 П [лек] ИТИ-31")

    def test_validate_template(self):
        self.assertEqual(validate_lesson_template("{time} {subject}"), [])
        self.assertEqual(
            validate_lesson_template("{time} {wat}"),
            ["wat"],
        )
        self.assertEqual(validate_lesson_template(""), [])


class TermStartTests(unittest.TestCase):
    def test_term_start_is_monday(self):
        item = item_factory("MONDAY", WEEK_ALL)
        self.assertEqual(term_start([item]), dt.date(2026, 9, 7))


if __name__ == "__main__":
    unittest.main()
