"""Тесты MCP-сервера: построение данных расписания и автоподбора (без сети)."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError

import gstu_schedule_mcp.server as server
from gstu_schedule_mcp.server import build_schedule_data, build_search_data

PAYLOAD = {
    "success": True,
    "data": {
        "entity": {
            "slug": "iti-31",
            "name": "ИТИ-31",
            "course": 3,
            "faculty": "Факультет",
            "cafedra": "Кафедра",
            "specialty": {"name": "Информационные системы", "code": "6-05-0611-01"},
            "subgroups": [
                {"slug": "iti-31-1", "subgroupNumber": 1},
                {"slug": "iti-31-2", "subgroupNumber": 2},
            ],
        },
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
                "lessonType": {"name": "Лабораторная работа", "shortName": "лаб"},
                "teachers": [{"shortName": "Иванов И.И."}],
                "classrooms": [{"roomNumber": "2-306"}],
                "groups": [
                    {
                        "slug": "iti-31",
                        "name": "ИТИ-31",
                        "subgroups": [{"subgroupNumber": 1, "slug": "iti-31-1"}],
                    }
                ],
            }
        ],
        "metadata": {"totalCount": 1},
    },
}

SEARCH_PAYLOAD = {
    "success": True,
    "data": {
        "groups": [
            {
                "slug": "iti-31",
                "name": "ИТИ-31",
                "course": 3,
                "specialtyName": "Информационные системы и технологии",
                "cafedraShortName": "ИТ",
                "facultyShortName": "ФАИС",
                "subgroupCount": 2,
            }
        ],
        "teachers": [
            {
                "slug": "avakyan-s",
                "fullName": "Авакян Сергей Левонович",
                "shortName": "Авакян С.Л.",
                "position": {"shortName": "доцент"},
                "cafedra": {"shortName": "ИТ"},
                "faculty": {"shortName": "ФАИС"},
            }
        ],
        "classrooms": [
            {
                "slug": "2-306",
                "name": "2-306",
                "roomNumber": "2-306",
                "building": "2",
                "floor": 3,
                "capacity": 30,
                "type": "лек",
                "cafedra": {"shortName": "ИТ"},
                "faculty": {"shortName": "ФАИС"},
            }
        ],
        "hasMore": False,
    },
}


class BuildScheduleDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = PAYLOAD["data"]["scheduleItems"][0]

    @patch("gstu_schedule_mcp.server.fetch_schedule", return_value=PAYLOAD)
    def test_group_day(self, mock_fetch) -> None:
        """Расписание на конкретную дату с одним занятием подгруппы 1."""
        data = build_schedule_data("group", "iti-31", date="2026-09-21", view="date")
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual(data["days"][0]["date"], "2026-09-21")
        self.assertEqual(data["entity"]["name"], "ИТИ-31")
        lessons = data["days"][0]["lessons"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["subject"], "П")
        self.assertEqual(lessons[0]["subjectFull"], "Предмет")
        self.assertEqual(lessons[0]["scope"], "subgroups")
        self.assertEqual(lessons[0]["subgroupNumbers"], [1])
        mock_fetch.assert_called_once()

    @patch("gstu_schedule_mcp.server.fetch_schedule", return_value=PAYLOAD)
    def test_subgroup_filter_excludes(self, mock_fetch) -> None:
        """Занятие подгруппы 1 не видно при выборе подгруппы 2."""
        data = build_schedule_data(
            "group", "iti-31", date="2026-09-21", view="date", subgroup=2
        )
        total = sum(len(d["lessons"]) for d in data["days"])
        self.assertEqual(total, 0)

    @patch("gstu_schedule_mcp.server.fetch_schedule", return_value=PAYLOAD)
    def test_week_view(self, mock_fetch) -> None:
        """Неделя вокруг даты: 7 дней, занятие только в понедельник."""
        data = build_schedule_data("group", "iti-31", date="2026-09-21", view="week")
        self.assertEqual(len(data["days"]), 7)
        total = sum(len(d["lessons"]) for d in data["days"])
        self.assertEqual(total, 1)
        self.assertIn("(нед. 3", data["scope"]["title"])

    def test_bad_schedule_type(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("faculty", "iti-31")

    def test_bad_view(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("group", "iti-31", view="month")

    def test_empty_slug(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("group", "  ", view="date")

    def test_bad_date(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("group", "iti-31", date="2026-13-99", view="date")

    def test_bad_semester_start(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data(
                "group", "iti-31", view="date", semester_start="not-a-date"
            )

    def test_bad_subgroup(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("group", "iti-31", view="date", subgroup=0)

    def test_bad_regex(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data("group", "iti-31", view="date", regex_filter=["("])

    def test_bad_lesson_format(self) -> None:
        with self.assertRaises(ToolError):
            build_schedule_data(
                "group", "iti-31", view="date", lesson_format="{unknown}"
            )

    @patch("gstu_schedule_mcp.server.fetch_schedule", return_value=PAYLOAD)
    def test_teacher_uses_empty_group_slug(self, mock_fetch) -> None:
        """Для преподавателя/аудитории группа для scope не подставляется."""
        build_schedule_data("teacher", "avakyan-s", date="2026-09-21", view="date")
        url = mock_fetch.call_args.args[0]
        self.assertIn("/teacher/avakyan-s", url)


class BuildSearchDataTests(unittest.TestCase):
    @patch("gstu_schedule_mcp.server.fetch_autocomplete", return_value=SEARCH_PAYLOAD)
    def test_search(self, mock_fetch) -> None:
        data = build_search_data("iti")
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["groups"]), 1)
        self.assertEqual(data["groups"][0]["slug"], "iti-31")
        self.assertEqual(data["groups"][0]["subgroupCount"], 2)
        self.assertEqual(data["teachers"][0]["position"], "доцент")
        self.assertEqual(data["classrooms"][0]["floor"], 3)
        self.assertEqual(data["classrooms"][0]["roomNumber"], "2-306")
        mock_fetch.assert_called_once_with("iti")

    @patch("gstu_schedule_mcp.server.fetch_autocomplete", return_value=SEARCH_PAYLOAD)
    def test_query_stripped(self, mock_fetch) -> None:
        build_search_data("  iti  ")
        mock_fetch.assert_called_once_with("iti")

    def test_empty_query(self) -> None:
        with self.assertRaises(ToolError):
            build_search_data("   ")

    @patch(
        "gstu_schedule_mcp.server.fetch_autocomplete",
        return_value={"success": False, "data": {}},
    )
    def test_api_failure(self, mock_fetch) -> None:
        with self.assertRaises(ToolError):
            build_search_data("iti")


class WatchdogTests(unittest.TestCase):
    """Сторож родителя: завершает процесс при смене PPID, не трогает ручной запуск."""

    def test_watchdog_exits_on_parent_change(self) -> None:
        """При смене PPID сторож вызывает os._exit(0) (завершение процесса)."""
        with (
            patch.object(server, "_INIT_PPID", 123),
            patch.object(server.os, "getppid", return_value=124),
            patch.object(server.os, "_exit") as mock_exit,
        ):
            server.spawn_parent_watchdog(interval=0.05)
            time.sleep(0.3)
            # os._exit в тесте замокан и не убивает процесс, поэтому поток
            # отрабатывает несколько итераций — важен сам факт вызова с кодом 0.
            self.assertGreaterEqual(mock_exit.call_count, 1)
            mock_exit.assert_called_with(0)

    def test_watchdog_skipped_for_manual_launch(self) -> None:
        """При ручном запуске (PPID <= 1) поток не создаётся."""
        with (
            patch.object(server, "_INIT_PPID", 0),
            patch.object(server.threading, "Thread") as mock_thread,
        ):
            server.spawn_parent_watchdog(interval=0.05)
            mock_thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
