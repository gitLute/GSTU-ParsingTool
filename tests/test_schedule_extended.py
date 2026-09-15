"""Дополнительные тесты: fetcher, config, app и крайние случаи моделей/форматирования."""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from gstu_schedule.app import (
    _date_title,
    _output_name,
    _week_title,
    run,
    search,
    search_hints,
)
from gstu_schedule.config import Config, dump_default_config, load_config
from gstu_schedule.engine import (
    regex_matches,
    scheduled_days,
    term_start,
    week_days,
)
from gstu_schedule.fetcher import (
    USER_AGENT,
    build_api_url,
    fetch_autocomplete,
    fetch_schedule,
    parse_api_url,
)
from gstu_schedule.formatters import (
    _short_time,
    build_days_data,
    format_autocomplete,
    format_autocomplete_hints,
    format_console,
    format_json,
    format_md,
)
from gstu_schedule.models import (
    WEEK_ALL,
    AutocompleteGroup,
    AutocompleteTeacher,
    AutocompleteClassroom,
    Entity,
    ScheduleItem,
    SCOPE_FULL,
    SCOPE_STREAM,
    SCOPE_SUBGROUPS,
    parse_autocomplete,
    parse_entity,
    parse_payload,
    parse_schedule_item,
)
from gstu_schedule.__main__ import main as cli_main


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


class _FakeResponse:
    """Минимальный ответ urllib с поддержкой контекстного менеджера."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BuildApiUrlTests(unittest.TestCase):
    def test_base_without_suffix(self):
        self.assertEqual(
            build_api_url("https://sc.gstu.by", "group", "iti-31"),
            "https://sc.gstu.by/api/schedules/group/iti-31",
        )

    def test_base_with_trailing_slash(self):
        self.assertEqual(
            build_api_url("https://sc.gstu.by/", "group", "iti-31"),
            "https://sc.gstu.by/api/schedules/group/iti-31",
        )

    def test_full_endpoint_passthrough(self):
        self.assertEqual(
            build_api_url("https://sc.gstu.by/api/schedules/group/", "group", "iti-31"),
            "https://sc.gstu.by/api/schedules/group/iti-31",
        )

    def test_teacher_kind(self):
        self.assertEqual(
            build_api_url("https://sc.gstu.by", "teacher", "avakyan-s"),
            "https://sc.gstu.by/api/schedules/teacher/avakyan-s",
        )

    def test_classroom_kind_strips_suffix(self):
        self.assertEqual(
            build_api_url(
                "https://sc.gstu.by/api/schedules/group/", "classroom", "2-306"
            ),
            "https://sc.gstu.by/api/schedules/classroom/2-306",
        )

    def test_unknown_kind_defaults_to_group(self):
        self.assertEqual(
            build_api_url("https://sc.gstu.by", "bogus", "x"),
            "https://sc.gstu.by/api/schedules/group/x",
        )

    def test_parse_api_url_slug_and_kind(self):
        self.assertEqual(
            parse_api_url("https://sc.gstu.by/api/schedules/teacher/avakyan-s"),
            ("avakyan-s", "teacher"),
        )
        self.assertEqual(
            parse_api_url("https://sc.gstu.by/api/schedules/classroom/2-306"),
            ("2-306", "classroom"),
        )
        self.assertEqual(
            parse_api_url("https://sc.gstu.by/api/schedules/group/iti-31"),
            ("iti-31", "group"),
        )
        self.assertEqual(parse_api_url("https://sc.gstu.by/"), ("", None))


class FetchScheduleTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_fetch_ok(self, urlopen):
        payload = {"success": True, "data": {}}
        urlopen.return_value = _FakeResponse(json.dumps(payload).encode("utf-8"))
        self.assertEqual(fetch_schedule("https://sc.gstu.by/api"), payload)

    @mock.patch("urllib.request.urlopen")
    def test_fetch_sends_user_agent(self, urlopen):
        urlopen.return_value = _FakeResponse(b"{}")
        fetch_schedule("https://sc.gstu.by/api")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_header("User-agent"), USER_AGENT)

    @mock.patch("urllib.request.urlopen")
    def test_fetch_http_error(self, urlopen):
        from email.message import Message

        headers = Message()
        urlopen.side_effect = urllib.error.HTTPError(
            "https://sc.gstu.by/api", 404, "Not Found", headers, io.BytesIO(b"")
        )
        with self.assertRaises(RuntimeError) as ctx:
            fetch_schedule("https://sc.gstu.by/api")
        self.assertIn("HTTP 404", str(ctx.exception))

    @mock.patch("urllib.request.urlopen")
    def test_fetch_url_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(RuntimeError) as ctx:
            fetch_schedule("https://sc.gstu.by/api")
        self.assertIn("connection refused", str(ctx.exception))

    @mock.patch("urllib.request.urlopen")
    def test_fetch_invalid_json(self, urlopen):
        urlopen.return_value = _FakeResponse(b"<html>not json</html>")
        with self.assertRaises(RuntimeError):
            fetch_schedule("https://sc.gstu.by/api")


class FetchAutocompleteTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_fetch_ok(self, urlopen):
        payload = {"success": True, "data": {"groups": [], "teachers": []}}
        urlopen.return_value = _FakeResponse(json.dumps(payload).encode("utf-8"))
        self.assertEqual(
            fetch_autocomplete("авакян", "https://sc.gstu.by/api/schedules"), payload
        )

    @mock.patch("urllib.request.urlopen")
    def test_url_encodes_query_with_spaces(self, urlopen):
        urlopen.return_value = _FakeResponse(b"{}")
        fetch_autocomplete("Сергей Левонович", "https://sc.gstu.by/api/schedules")
        url = urlopen.call_args.args[0].full_url
        self.assertTrue(
            url.startswith("https://sc.gstu.by/api/schedules/autocomplete?q=")
        )
        self.assertNotIn(" ", url)
        self.assertIn("Сергей", urllib.parse.unquote(url))

    @mock.patch("urllib.request.urlopen")
    def test_sends_user_agent(self, urlopen):
        urlopen.return_value = _FakeResponse(b"{}")
        fetch_autocomplete("x", "https://sc.gstu.by/api/schedules")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_header("User-agent"), USER_AGENT)

    def test_url_strips_trailing_slash(self):
        def _build(q: str, base: str) -> str:
            return f"{base.rstrip('/')}/autocomplete?q={q}"

        self.assertEqual(
            _build("x", "https://sc.gstu.by/api/schedules/"),
            "https://sc.gstu.by/api/schedules/autocomplete?q=x",
        )

    @mock.patch("urllib.request.urlopen")
    def test_http_error(self, urlopen):
        from email.message import Message

        headers = Message()
        urlopen.side_effect = urllib.error.HTTPError(
            "https://sc.gstu.by/api", 500, "Internal", headers, io.BytesIO(b"")
        )
        with self.assertRaises(RuntimeError) as ctx:
            fetch_autocomplete("q", "https://sc.gstu.by/api/schedules")
        self.assertIn("HTTP 500", str(ctx.exception))


class AutocompleteTests(unittest.TestCase):
    @staticmethod
    def _payload(groups=None, teachers=None, classrooms=None, has_more=False) -> dict:
        return {
            "success": True,
            "data": {
                "groups": groups or [],
                "teachers": teachers or [],
                "classrooms": classrooms or [],
                "hasMore": has_more,
            },
        }

    def test_parse_autocomplete_groups(self):
        raw = self._payload(
            groups=[
                {
                    "slug": "iti-31",
                    "name": "ИТИ-31",
                    "course": 3,
                    "specialtyName": "ИС",
                    "cafedraShortName": "ИТ",
                    "facultyShortName": "ФАИС",
                    "subgroupCount": 2,
                }
            ]
        )
        result = parse_autocomplete(raw)
        self.assertEqual(len(result.groups), 1)
        g = result.groups[0]
        self.assertEqual(g.slug, "iti-31")
        self.assertEqual(g.name, "ИТИ-31")
        self.assertEqual(g.course, 3)
        self.assertEqual(g.subgroup_count, 2)
        self.assertEqual(result.total, 1)

    def test_parse_autocomplete_teachers(self):
        raw = self._payload(
            teachers=[
                {
                    "slug": "avakyan-s",
                    "fullName": "Авакян Сергей Левонович",
                    "shortName": "Авакян С.Л.",
                    "position": {"name": "Доцент", "shortName": "доц."},
                    "cafedra": {"shortName": "ВМ"},
                    "faculty": {"shortName": "ФАИС"},
                }
            ]
        )
        result = parse_autocomplete(raw)
        self.assertEqual(len(result.teachers), 1)
        t = result.teachers[0]
        self.assertEqual(t.slug, "avakyan-s")
        self.assertEqual(t.position, "доц.")
        self.assertEqual(t.cafedra_short, "ВМ")

    def test_parse_autocomplete_classrooms(self):
        raw = self._payload(
            classrooms=[
                {
                    "slug": "2-306",
                    "name": "2-306",
                    "roomNumber": "2-306",
                    "building": "Второй корпус",
                    "floor": 2,
                    "capacity": 52,
                    "type": "LECTURE",
                    "cafedra": {"shortName": "ИТ"},
                    "faculty": {"shortName": "ФАИС"},
                }
            ]
        )
        result = parse_autocomplete(raw)
        self.assertEqual(len(result.classrooms), 1)
        c = result.classrooms[0]
        self.assertEqual(c.building, "Второй корпус")
        self.assertEqual(c.floor, 2)
        self.assertEqual(c.room_type, "LECTURE")
        self.assertTrue(result.has_more is False)

    def test_total(self):
        result = parse_autocomplete(
            self._payload(
                groups=[{"slug": "a"}],
                teachers=[{"slug": "b"}, {"slug": "c"}],
                classrooms=[{"slug": "d"}],
            )
        )
        self.assertEqual(result.total, 4)

    def test_has_more(self):
        result = parse_autocomplete(self._payload(has_more=True))
        self.assertTrue(result.has_more)

    def test_format_autocomplete_teachers(self):
        result = parse_autocomplete(
            self._payload(
                teachers=[
                    {
                        "slug": "avakyan-s",
                        "fullName": "Авакян Сергей Левонович",
                        "shortName": "Авакян С.Л.",
                        "position": {"shortName": "доц."},
                        "cafedra": {"shortName": "ВМ"},
                        "faculty": {},
                    }
                ]
            )
        )
        text = format_autocomplete(result, "авакян")
        self.assertIn("авакян", text)
        self.assertIn("avakyan-s", text)
        self.assertIn("Авакян Сергей Левонович", text)
        self.assertIn("доц.", text)
        self.assertIn("--teacher avakyan-s", text)

    def test_format_autocomplete_groups(self):
        result = parse_autocomplete(
            self._payload(
                groups=[
                    {
                        "slug": "iti-31",
                        "name": "ИТИ-31",
                        "course": 3,
                        "specialtyName": "ИС",
                        "cafedraShortName": "ИТ",
                        "facultyShortName": "ФАИС",
                        "subgroupCount": 2,
                    }
                ]
            )
        )
        text = format_autocomplete(result, "iti")
        self.assertIn("--group iti-31", text)
        self.assertIn("ИТИ-31", text)

    def test_format_autocomplete_has_more(self):
        result = parse_autocomplete(
            self._payload(teachers=[{"slug": "x"}], has_more=True)
        )
        text = format_autocomplete(result, "x")
        self.assertIn("Есть ещё результаты", text)

    def test_format_autocomplete_empty(self):
        result = parse_autocomplete(self._payload())
        text = format_autocomplete(result, "zzz")
        self.assertIn("ничего не найдено", text)

    def test_format_autocomplete_without_hints(self):
        result = parse_autocomplete(
            self._payload(
                teachers=[
                    {
                        "slug": "avakyan-s",
                        "fullName": "Авакян Сергей Левонович",
                        "position": {"shortName": "доц."},
                    }
                ]
            )
        )
        text = format_autocomplete(result, "авакян", show_hints=False)
        self.assertNotIn("Для показа расписания:", text)
        self.assertNotIn("--teacher", text)
        self.assertNotIn("--classroom", text)
        self.assertIn("Преподаватели:", text)

    def test_format_autocomplete_hints(self):
        result = parse_autocomplete(
            self._payload(
                teachers=[
                    {
                        "slug": "avakyan-e",
                        "fullName": "Авакян Елена Зиновьевна",
                        "position": {"shortName": "доц."},
                    },
                    {
                        "slug": "avakyan-s",
                        "fullName": "Авакян Сергей Левонович",
                    },
                ],
                classrooms=[{"slug": "2-306", "name": "2-306", "roomNumber": "2-306"}],
                groups=[{"slug": "iti-31", "name": "ИТИ-31"}],
            )
        )
        text = format_autocomplete_hints(result)
        lines = [line for line in text.splitlines() if line]
        self.assertIn("--teacher avakyan-e   # Авакян Елена Зиновьевна", lines)
        self.assertIn("--teacher avakyan-s   # Авакян Сергей Левонович", lines)
        self.assertTrue(
            any(
                line.startswith("--classroom 2-306")
                and line.rstrip().endswith("# 2-306")
                for line in lines
            )
        )
        self.assertTrue(
            any(
                line.startswith("--group iti-31") and line.rstrip().endswith("# ИТИ-31")
                for line in lines
            )
        )
        self.assertNotIn("Преподаватели:", text)
        self.assertNotIn("Для показа расписания:", text)
        self.assertNotIn("Поиск:", text)

    def test_format_autocomplete_hints_empty(self):
        result = parse_autocomplete(self._payload())
        self.assertEqual(format_autocomplete_hints(result), "")


class ParseEntityTests(unittest.TestCase):
    def test_short_names_and_subgroups(self):
        raw = {
            "slug": "iti-31",
            "name": "ИТИ-31",
            "course": 3,
            "faculty": "Экономический",
            "facultyShort": "ФЭ",
            "cafedra": "Программная инженерия",
            "cafedraShort": "ПИ",
            "specialty": {"name": "ИС", "code": "6-05-0611-01"},
            "subgroups": [{"subgroupNumber": 1}, {"subgroupNumber": 2}],
        }
        entity = parse_entity(raw)
        self.assertEqual(entity.faculty_short, "ФЭ")
        self.assertEqual(entity.cafedra_short, "ПИ")
        self.assertEqual(entity.specialty_name, "ИС")
        self.assertEqual(entity.specialty_code, "6-05-0611-01")
        self.assertEqual(entity.subgroups, [1, 2])

    def test_missing_fields_default(self):
        entity = parse_entity({"slug": "x"})
        self.assertEqual(entity.name, "")
        self.assertEqual(entity.course, 0)
        self.assertEqual(entity.faculty, "")
        self.assertEqual(entity.specialty_code, "")
        self.assertEqual(entity.subgroups, [])


class ScopeParseTests(unittest.TestCase):
    def _base_raw(self) -> dict:
        return {
            "dayOfWeek": "TUESDAY",
            "weekType": "ALL",
            "lessonNumber": 2,
            "startTime": "08:20:00",
            "endTime": "09:45:00",
            "startDate": "2026-09-08",
            "endDate": "2026-12-28",
            "isOneTime": False,
            "subject": {"name": "Предмет", "shortName": "П"},
            "lessonType": {"name": "Лекция", "shortName": "лек"},
            "teachers": [],
            "classrooms": [],
        }

    def test_scope_full_when_groups_missing(self):
        item = parse_schedule_item(self._base_raw(), "iti-31")
        self.assertEqual(item.scope, SCOPE_FULL)
        self.assertEqual(item.subgroup_numbers, [])
        self.assertEqual(item.other_groups, [])

    def test_scope_full_own_group_without_subgroups(self):
        raw = self._base_raw()
        raw["groups"] = [{"slug": "iti-31", "name": "ИТИ-31"}]
        item = parse_schedule_item(raw, "iti-31")
        self.assertEqual(item.scope, SCOPE_FULL)
        self.assertEqual(item.subgroup_numbers, [])

    def test_scope_stream_other_groups_only(self):
        raw = self._base_raw()
        raw["groups"] = [{"slug": "itp-31", "name": "ИТП-31"}]
        item = parse_schedule_item(raw, "iti-31")
        self.assertEqual(item.scope, SCOPE_STREAM)
        self.assertEqual(item.other_groups, ["ИТП-31"])

    def test_scope_subgroups_prefixed_with_own_group(self):
        raw = self._base_raw()
        raw["groups"] = [
            {"slug": "itp-31", "name": "ИТП-31"},
            {
                "slug": "iti-31",
                "name": "ИТИ-31",
                "subgroups": [{"subgroupNumber": 2}, {"subgroupNumber": 1}],
            },
        ]
        item = parse_schedule_item(raw, "iti-31")
        self.assertEqual(item.subgroup_numbers, [1, 2])
        self.assertEqual(item.scope, SCOPE_SUBGROUPS)
        self.assertEqual(item.other_groups, ["ИТП-31"])

    def test_optional_fields_missing(self):
        raw = self._base_raw()
        del raw["teachers"]
        del raw["classrooms"]
        del raw["lessonType"]
        item = parse_schedule_item(raw, "iti-31")
        self.assertEqual(item.teachers, [])
        self.assertEqual(item.classrooms, [])
        self.assertIsNone(item.lesson_type_short)

    def test_teacher_room_fallback(self):
        raw = self._base_raw()
        raw["teachers"] = [{"fullName": "Иванов И.И."}]
        raw["classrooms"] = [{"slug": "2-309"}]
        item = parse_schedule_item(raw, "iti-31")
        self.assertEqual(item.teachers, ["Иванов И.И."])
        self.assertEqual(item.classrooms, ["2-309"])

    def test_parse_payload_empty_items(self):
        payload = {"success": True, "data": {"entity": {"slug": "iti-31"}}}
        entity, items = parse_payload(payload, "iti-31")
        self.assertEqual(entity.slug, "iti-31")
        self.assertEqual(items, [])

    def test_parse_payload_success_false(self):
        with self.assertRaises(ValueError):
            parse_payload({"success": False, "data": {}}, "iti-31")


class ConfigTests(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        cfg = load_config("/nonexistent/path/config.json")
        self.assertEqual(cfg.group, "iti-31")
        self.assertEqual(cfg.view, "week")
        self.assertIsNone(cfg.subgroup)

    def test_unknown_field_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"bogus": 1}\n')
            with self.assertRaises(ValueError):
                load_config(path)

    def test_non_dict_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[1, 2]\n")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_lesson_types_coerced_from_string(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"lesson_types": "лаб,  лек"}\n')
            cfg = load_config(path)
            self.assertEqual(cfg.lesson_types, ["лаб", "лек"])

    def test_lesson_types_from_list(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"lesson_types": ["лаб", "лек"]}\n')
            cfg = load_config(path)
            self.assertEqual(cfg.lesson_types, ["лаб", "лек"])

    def test_regex_filter_from_string(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"regex_filter": "иванов"}\n')
            cfg = load_config(path)
            self.assertEqual(cfg.regex_filter, ["иванов"])

    def test_effective_api_url_default(self):
        cfg = Config()
        self.assertEqual(
            cfg.effective_api_url(),
            "https://sc.gstu.by/api/schedules/group/iti-31",
        )

    def test_effective_api_url_explicit(self):
        cfg = Config(api_url="https://example.com/full")
        self.assertEqual(cfg.effective_api_url(), "https://example.com/full")

    def test_effective_api_url_teacher(self):
        cfg = Config(schedule_type="teacher", teacher="avakyan-s")
        self.assertEqual(
            cfg.effective_api_url(),
            "https://sc.gstu.by/api/schedules/teacher/avakyan-s",
        )

    def test_effective_api_url_classroom(self):
        cfg = Config(schedule_type="classroom", classroom="2-306")
        self.assertEqual(
            cfg.effective_api_url(),
            "https://sc.gstu.by/api/schedules/classroom/2-306",
        )

    def test_active_slug_by_type(self):
        cfg = Config(schedule_type="teacher", teacher="avakyan-s", classroom="2-306")
        self.assertEqual(cfg.active_slug(), "avakyan-s")
        cfg.schedule_type = "classroom"
        self.assertEqual(cfg.active_slug(), "2-306")
        cfg.schedule_type = "group"
        self.assertEqual(cfg.active_slug(), "iti-31")

    def test_invalid_schedule_type_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schedule_type": "bogus"}\n')
            with self.assertRaises(ValueError):
                load_config(path)

    def test_dump_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            dump_default_config(path)
            cfg = load_config(path)
            self.assertEqual(cfg.group, "iti-31")

    def test_dump_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"group": "custom"}\n')
            dump_default_config(path)
            self.assertEqual(load_config(path).group, "custom")


class WeekDaysTests(unittest.TestCase):
    def test_week_days_from_wednesday(self):
        days = week_days(dt.date(2026, 9, 16))  # среда
        self.assertEqual(days[0], dt.date(2026, 9, 14))  # понедельник
        self.assertEqual(days[6], dt.date(2026, 9, 20))  # воскресенье
        self.assertEqual(len(days), 7)

    def test_week_days_from_monday(self):
        monday = dt.date(2026, 9, 14)
        self.assertEqual(week_days(monday)[0], monday)
        self.assertEqual(week_days(monday)[-1], monday + dt.timedelta(days=6))

    def test_term_start_empty_defaults_to_today_monday(self):
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        self.assertEqual(term_start([]), monday)

    def test_term_start_rounds_up_to_monday(self):
        item = item_factory("MONDAY", WEEK_ALL)
        item.start_date = dt.date(2026, 9, 9)  # среда
        self.assertEqual(term_start([item]), dt.date(2026, 9, 7))

    def test_scheduled_days_sunday(self):
        item = item_factory("SUNDAY", WEEK_ALL)
        day = dt.date(2026, 9, 13)  # воскресенье, неделя 2
        result = scheduled_days([item], [day], None, SEMESTER)
        self.assertEqual(result[day], [item])

    def test_scheduled_days_combined_filters(self):
        target = item_factory("MONDAY", WEEK_ALL, subgroup_numbers=[1])
        target.subject_name = "Проектирование ПО"
        wrong_subgroup = item_factory("MONDAY", WEEK_ALL, subgroup_numbers=[2])
        wrong_type = item_factory("MONDAY", WEEK_ALL, lesson_type_short="лек")
        wrong_regex = item_factory("MONDAY", WEEK_ALL, subgroup_numbers=[1])
        wrong_regex.subject_name = "Дискретная математика"
        day = dt.date(2026, 9, 14)  # понедельник, неделя 2
        result = scheduled_days(
            [target, wrong_subgroup, wrong_type, wrong_regex],
            [day],
            1,
            SEMESTER,
            lesson_types=["лаб"],
            regex_filter=["проект"],
        )
        self.assertEqual(result[day], [target])

    def test_regex_matches_stream_group_names(self):
        item = item_factory("MONDAY", WEEK_ALL, scope=SCOPE_STREAM)
        item.other_groups = ["ИТП-31"]
        self.assertTrue(regex_matches(item, ["итп"]))
        self.assertFalse(regex_matches(item, ["мнс-21"]))


class FormatterTests(unittest.TestCase):
    def setUp(self):
        self.entity = Entity(
            slug="iti-31",
            name="ИТИ-31",
            course=3,
            faculty="",
            faculty_short="",
            cafedra="",
            cafedra_short="",
            specialty_name="",
            specialty_code="",
            subgroups=[1, 2],
        )
        self.day = dt.date(2026, 9, 14)
        self.lesson = item_factory("MONDAY", WEEK_ALL, subgroup_numbers=[1])
        self.lesson.teachers = ["Иванов И.И."]
        self.lesson.classrooms = ["2-309"]
        self.scheduled = {self.day: [self.lesson]}
        self.dates = [self.day]

    def test_short_time(self):
        self.assertEqual(_short_time("08:20:00"), "08:20")
        self.assertEqual(_short_time("09:45"), "09:45")
        self.assertEqual(_short_time(""), "")

    def test_format_console(self):
        text = format_console(self.entity, self.dates, self.scheduled, None, [], "Тест")
        self.assertIn("Расписание группы ИТИ-31", text)
        self.assertIn("ПОНЕДЕЛЬНИК", text)
        self.assertIn("Предмет", text)
        self.assertIn("Иванов И.И.", text)

    def test_format_console_with_template(self):
        text = format_console(
            self.entity,
            self.dates,
            self.scheduled,
            1,
            [],
            "Тест",
            "{time} {subject} {groups}",
        )
        self.assertIn("08:20–09:45 П ИТИ-31, подгр. 1", text)

    def test_format_console_schedule_label(self):
        text = format_console(
            self.entity,
            self.dates,
            self.scheduled,
            None,
            [],
            "Тест",
            schedule_label="Расписание преподавателя Авакян С.Л.",
        )
        self.assertIn("Расписание преподавателя Авакян С.Л.", text)

    def test_format_md_schedule_label(self):
        md = format_md(
            self.entity,
            self.dates,
            self.scheduled,
            None,
            [],
            "Тест",
            schedule_label="Расписание аудитории 2-306",
        )
        self.assertIn("# Расписание аудитории 2-306", md)

    def test_format_json_schedule_block(self):
        js = format_json(
            self.entity,
            self.dates,
            self.scheduled,
            None,
            [],
            "Тест",
            schedule_label="Расписание преподавателя Авакян С.Л.",
            schedule_type="teacher",
        )
        data = json.loads(js)
        self.assertEqual(data["schedule"]["type"], "teacher")
        self.assertEqual(
            data["schedule"]["label"], "Расписание преподавателя Авакян С.Л."
        )

    def test_format_md_table(self):
        md = format_md(self.entity, self.dates, self.scheduled, None, [], "Тест")
        self.assertIn("## Понедельник", md)
        self.assertIn("| 1 |", md)
        self.assertIn("Предмет", md)

    def test_format_md_with_template(self):
        md = format_md(
            self.entity,
            self.dates,
            self.scheduled,
            None,
            [],
            "Тест",
            "{subject} [{type}]",
        )
        self.assertNotIn("| № |", md)
        self.assertIn("П [лаб]", md)

    def test_format_md_empty_day(self):
        md = format_md(self.entity, self.dates, {self.day: []}, None, [], "Тест")
        self.assertIn("_Занятий нет_", md)

    def test_format_json_structure(self):
        js = format_json(self.entity, self.dates, self.scheduled, None, [], "Тест")
        data = json.loads(js)
        self.assertEqual(data["group"]["name"], "ИТИ-31")
        self.assertEqual(data["group"]["subgroups"], [1, 2])
        self.assertEqual(len(data["days"]), 1)
        lesson = data["days"][0]["lessons"][0]
        self.assertEqual(lesson["subject"], "П")
        self.assertEqual(lesson["subgroupNumbers"], [1])
        self.assertEqual(lesson["scope"], SCOPE_SUBGROUPS)

    def test_build_days_data_adds_formatted(self):
        data = build_days_data(self.entity, self.dates, self.scheduled, "{subject}")
        lesson = data[0]["lessons"][0]
        self.assertEqual(lesson["formatted"], "П")
        self.assertEqual(data[0]["dayName"], "Понедельник")


class AppHelperTests(unittest.TestCase):
    def test_output_name_default(self):
        cfg = Config(group="iti-31")
        self.assertEqual(
            _output_name(cfg, "week", dt.date(2026, 9, 21)),
            "iti-31_week_2026-09-21",
        )

    def test_output_name_with_subgroup(self):
        cfg = Config(group="iti-31", subgroup=1)
        self.assertEqual(
            _output_name(cfg, "date", dt.date(2026, 9, 16)),
            "iti-31_sub1_date_2026-09-16",
        )

    def test_output_name_custom_file(self):
        cfg = Config(group="iti-31", output_file="myname")
        self.assertEqual(_output_name(cfg, "week", dt.date(2026, 9, 21)), "myname")

    def test_output_name_teacher(self):
        cfg = Config(schedule_type="teacher", teacher="avakyan-s")
        self.assertEqual(
            _output_name(cfg, "week", dt.date(2026, 9, 21)),
            "avakyan-s_week_2026-09-21",
        )

    def test_output_name_classroom(self):
        cfg = Config(schedule_type="classroom", classroom="2-306")
        self.assertEqual(
            _output_name(cfg, "week", dt.date(2026, 9, 21)),
            "2-306_week_2026-09-21",
        )

    def test_output_name_api_url_without_explicit_entity(self):
        cfg = Config(api_url="https://sc.gstu.by/api/schedules/teacher/avakyan-s")
        self.assertEqual(
            _output_name(cfg, "week", dt.date(2026, 9, 15)),
            "avakyan-s_week_2026-09-15",
        )

    def test_output_name_explicit_teacher_overrides_url(self):
        cfg = Config(
            api_url="https://sc.gstu.by/api/schedules/teacher/avakyan-s",
            schedule_type="teacher",
            teacher="other-t",
            _explicit_entity=True,
        )
        self.assertEqual(
            _output_name(cfg, "week", dt.date(2026, 9, 15)),
            "other-t_week_2026-09-15",
        )

    def test_week_title(self):
        title = _week_title(dt.date(2026, 9, 21), SEMESTER)
        self.assertIn("нед. 3", title)
        self.assertIn("нечётная", title)
        self.assertIn("2026-09-21", title)

    def test_date_title(self):
        title = _date_title(dt.date(2026, 9, 16), SEMESTER)
        self.assertIn("нед. 2", title)
        self.assertIn("чётная", title)


class AppRunTests(unittest.TestCase):
    def _run(self, cfg: Config) -> int:
        """Запускает приложение, подавляя его служебный вывод в stdout/stderr."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return run(cfg)

    def _payload(self) -> dict:
        return {
            "success": True,
            "data": {
                "entity": {"slug": "iti-31", "name": "ИТИ-31", "course": 3},
                "scheduleItems": [
                    {
                        "dayOfWeek": "MONDAY",
                        "weekType": "ALL",
                        "lessonNumber": 1,
                        "startTime": "08:20:00",
                        "endTime": "09:45:00",
                        "startDate": "2026-09-07",
                        "endDate": "2026-12-28",
                        "isOneTime": False,
                        "subject": {"name": "Предмет", "shortName": "П"},
                        "lessonType": {"name": "Лекция", "shortName": "лек"},
                        "teachers": [],
                        "classrooms": [],
                    }
                ],
                "metadata": {"totalCount": 1},
            },
        }

    def test_run_success_json(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(
                group="iti-31",
                view="date",
                date="2026-09-07",
                output_format="json",
                output_dir=d,
            )
            with mock.patch(
                "gstu_schedule.app.fetch_schedule", return_value=self._payload()
            ):
                code = self._run(cfg)
            self.assertEqual(code, 0)
            out = os.path.join(d, "iti-31_date_2026-09-07.json")
            self.assertTrue(os.path.isfile(out))
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["group"]["name"], "ИТИ-31")
            self.assertEqual(len(data["days"][0]["lessons"]), 1)

    def test_run_fetch_error(self):
        cfg = Config()
        with mock.patch(
            "gstu_schedule.app.fetch_schedule",
            side_effect=RuntimeError("не удалось соединиться"),
        ):
            self.assertEqual(self._run(cfg), 1)

    def test_run_unknown_template(self):
        cfg = Config(lesson_format="{unknown}")
        with mock.patch(
            "gstu_schedule.app.fetch_schedule", return_value=self._payload()
        ):
            self.assertEqual(self._run(cfg), 1)

    def test_run_bad_regex(self):
        cfg = Config(regex_filter=["("])
        with mock.patch(
            "gstu_schedule.app.fetch_schedule", return_value=self._payload()
        ):
            self.assertEqual(self._run(cfg), 1)


class AutocompleteAppTests(unittest.TestCase):
    @staticmethod
    def _payload(teachers=None) -> dict:
        return {
            "success": True,
            "data": {
                "groups": [],
                "teachers": teachers
                or [
                    {
                        "slug": "avakyan-s",
                        "fullName": "Авакян Сергей Левонович",
                        "shortName": "Авакян С.Л.",
                        "position": {"shortName": "доц."},
                        "cafedra": {"shortName": "ВМ"},
                        "faculty": {"shortName": "ФАИС"},
                    }
                ],
                "classrooms": [],
                "hasMore": False,
            },
        }

    def _capture(self, fn, query, cfg) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = fn(query, cfg)
        return code, out.getvalue()

    def test_search_not_empty(self):
        cfg = Config()
        with mock.patch(
            "gstu_schedule.app.fetch_autocomplete", return_value=self._payload()
        ):
            code, out = self._capture(search, "авакян", cfg)
        self.assertEqual(code, 0)
        self.assertIn("Преподаватели:", out)
        self.assertIn("avakyan-s", out)
        self.assertNotIn("Для показа расписания:", out)
        self.assertNotIn("--teacher", out)

    def test_search_hints_only(self):
        cfg = Config()
        with mock.patch(
            "gstu_schedule.app.fetch_autocomplete", return_value=self._payload()
        ):
            code, out = self._capture(search_hints, "авакян", cfg)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines, ["--teacher avakyan-s   # Авакян Сергей Левонович"])

    def test_search_no_results(self):
        payload = {
            "success": True,
            "data": {"groups": [], "teachers": [], "classrooms": [], "hasMore": False},
        }
        cfg = Config()
        with mock.patch("gstu_schedule.app.fetch_autocomplete", return_value=payload):
            code, out = self._capture(search, "x", cfg)
        self.assertEqual(code, 1)

    def test_search_hints_no_results(self):
        payload = {
            "success": True,
            "data": {"groups": [], "teachers": [], "classrooms": [], "hasMore": False},
        }
        cfg = Config()
        with mock.patch("gstu_schedule.app.fetch_autocomplete", return_value=payload):
            code, out = self._capture(search_hints, "x", cfg)
        self.assertEqual(code, 1)

    def test_search_fetch_error(self):
        cfg = Config()
        with mock.patch(
            "gstu_schedule.app.fetch_autocomplete",
            side_effect=RuntimeError("не удалось соединиться"),
        ):
            code, out = self._capture(search, "x", cfg)
        self.assertEqual(code, 1)

    def test_search_success_false(self):
        cfg = Config()
        with mock.patch(
            "gstu_schedule.app.fetch_autocomplete", return_value={"success": False}
        ):
            code, out = self._capture(search, "x", cfg)
        self.assertEqual(code, 1)


class CliMainConfigErrorTests(unittest.TestCase):
    """main() должен аккуратно сообщать об ошибках конфига, а не кидать traceback."""

    def _write_config(self, d: str, content: str) -> str:
        path = os.path.join(d, "config.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def _run(self, path: str) -> tuple[int, str]:
        err = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["gstu-schedule", "--config", path]),
            mock.patch("sys.stderr", new_callable=lambda: err),
        ):
            code = cli_main()
        return code, err.getvalue()

    def test_unknown_field_reports_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_config(d, '{"bogus": 1}\n')
            code, err = self._run(path)
        self.assertEqual(code, 1)
        self.assertIn("ОШИБКА:", err)
        self.assertIn("неизвестное поле", err)
        self.assertNotIn("Traceback", err)

    def test_malformed_json_reports_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_config(d, "{invalid json\n")
            code, err = self._run(path)
        self.assertEqual(code, 1)
        self.assertIn("ОШИБКА:", err)
        self.assertNotIn("Traceback", err)

    def test_non_dict_config_reports_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_config(d, "[1, 2]\n")
            code, err = self._run(path)
        self.assertEqual(code, 1)
        self.assertIn("ОШИБКА:", err)
        self.assertNotIn("Traceback", err)

    def test_invalid_schedule_type_reports_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_config(d, '{"schedule_type": "bogus"}\n')
            code, err = self._run(path)
        self.assertEqual(code, 1)
        self.assertIn("ОШИБКА:", err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
