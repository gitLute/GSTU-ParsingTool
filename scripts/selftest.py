#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-тест MCP-сервера gstu-schedule через stdio-клиент.

Запускает сервер как дочерний процесс, выполняет эхо-цикл
initialize -> list_tools -> search_entities -> get_schedule
и печатает краткие результаты. Требует доступ в интернет к sc.gstu.by.

Примеры:

    # группа iti-31, расписание на неделю вокруг сегодняшнего дня
    python3 scripts/selftest.py

    # преподаватель на конкретную дату
    python3 scripts/selftest.py --type teacher --slug avakyan-s --date 2026-09-21 --view date

    # профиль студента (env GSTU_STUDENT): get_student_profile + расписание без slug
    python3 scripts/selftest.py --student-profile ~/.config/opencode/.secrets/gstu-student.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Сервер запускается через python -m gstu_schedule_mcp с PYTHONPATH=src,
# что работает и из исходников, и из установленного пакета.
SERVER_CMD = [
    sys.executable,
    "-m",
    "gstu_schedule_mcp",
    "--stdio",
]


def _env(profile_raw: str | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    if profile_raw is not None:
        env["GSTU_STUDENT"] = profile_raw
    return env


def _dump(label: str, obj) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    print(f"--- {label} ---")
    print(text[:2000])
    print()


async def _call_json(session, tool: str, args: dict) -> dict:
    """Вызов инструмента MCP и разбор текстового JSON-ответа."""
    res = await session.call_tool(tool, args)
    text = "".join(c.text or "" for c in res.content if c.type == "text")
    return json.loads(text)


async def main(args: argparse.Namespace) -> int:
    profile_raw = None
    if args.student_profile:
        profile_path = Path(args.student_profile)
        profile_raw = profile_path.read_text(encoding="utf-8").strip()
        print(f"=== профиль студента: {profile_path} ({len(profile_raw)} симв.) ===")

    params = StdioServerParameters(
        command=SERVER_CMD[0], args=SERVER_CMD[1:], env=_env(profile_raw)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("=== сервер инициализирован ===")

            tools_result = await session.list_tools()
            # mcp 1.12: результат может быть объектом ListToolsResult или
            # кортежем (tools, next_cursor) — обрабатываем оба варианта.
            if isinstance(tools_result, tuple):
                tools = tools_result[0]
            elif hasattr(tools_result, "tools"):
                tools = tools_result.tools
            else:
                tools = tools_result
            names = [t.name for t in tools]
            print(f"=== инструменты: {names} ===")
            if "get_schedule" not in names or "search_entities" not in names:
                print(
                    "ОШИБКА: ожидались get_schedule и search_entities", file=sys.stderr
                )
                return 1

            # 1. Автоподбор.
            search_data = await _call_json(
                session, "search_entities", {"query": args.search}
            )
            print(
                f"=== search_entities('{args.search}'): найдено {search_data['total']} ==="
            )
            for kind in ("groups", "teachers", "classrooms"):
                items = search_data.get(kind) or []
                if items:
                    slugs = ", ".join(i["slug"] for i in items[:5])
                    print(f"  {kind}: {slugs}")

            # 2. Расписание.
            tool_args = {
                "schedule_type": args.type,
                "slug": args.slug,
                "view": args.view,
            }
            if args.date:
                tool_args["date"] = args.date
            if args.subgroup:
                tool_args["subgroup"] = args.subgroup
            if args.lesson_types:
                tool_args["lesson_types"] = args.lesson_types
            if args.regex:
                tool_args["regex_filter"] = args.regex
            if args.lesson_format:
                tool_args["lesson_format"] = args.lesson_format

            sched = await _call_json(session, "get_schedule", tool_args)
            entity = sched["entity"]["name"] or sched["entity"]["slug"]
            total = sum(len(d["lessons"]) for d in sched["days"])
            print(
                f"=== get_schedule({args.type} {args.slug}, view={args.view}): "
                f"{entity}, занятий {total} ==="
            )
            print(f"  период: {sched['scope']['title']}")
            for day in sched["days"]:
                if day["lessons"]:
                    first = day["lessons"][0]
                    print(
                        f"  {day['date']} ({day['dayName']}): "
                        f"{len(day['lessons'])} пар, первая: "
                        f"{first['lessonNumber']}. {first['startTime']}-"
                        f"{first['endTime']} {first['subject']}"
                    )
            if total == 0:
                print("  ВНИМАНИЕ: занятий на период не найдено")

            # 3. Профиль студента: get_student_profile и расписание без slug.
            if profile_raw is not None:
                prof = await _call_json(session, "get_student_profile", {})
                print(f"=== get_student_profile: configured={prof['configured']} ===")
                if prof.get("error"):
                    print(f"  ОШИБКА профиля: {prof['error']}", file=sys.stderr)
                    return 1
                if prof["configured"]:
                    p = prof["profile"]
                    print(
                        f"  group={p.get('group')}, subgroup={p.get('subgroup')}, "
                        f"fullName={p.get('fullName')}"
                    )
                    if p.get("notes"):
                        print(f"  notes={p.get('notes')}")
                prof_args = {"schedule_type": "group", "view": args.view}
                if args.date:
                    prof_args["date"] = args.date
                prof_sched = await _call_json(session, "get_schedule", prof_args)
                entity = prof_sched["entity"]["name"] or prof_sched["entity"]["slug"]
                total = sum(len(d["lessons"]) for d in prof_sched["days"])
                print(
                    f"=== get_schedule без slug (группа из профиля): "
                    f"{entity}, занятий {total} ==="
                )
                if total == 0:
                    print("  ВНИМАНИЕ: занятий на период не найдено")
            return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="selftest",
        description="Smoke-тест MCP-сервера gstu-schedule через stdio-клиент.",
    )
    ap.add_argument(
        "--type", choices=("group", "teacher", "classroom"), default="group"
    )
    ap.add_argument(
        "--slug", default="iti-31", help="slug сущности (по умолчанию iti-31)"
    )
    ap.add_argument("--date", help="опорная дата YYYY-MM-DD (по умолчанию сегодня)")
    ap.add_argument("--view", choices=("week", "date"), default="week")
    ap.add_argument("--subgroup", type=int, help="номер подгруппы")
    ap.add_argument("--lesson-types", nargs="+", help="типы занятий (лаб, лек, ...)")
    ap.add_argument("--regex", nargs="+", help="регулярные выражения по тексту занятия")
    ap.add_argument("--format", dest="lesson_format", help="шаблон строки занятия")
    ap.add_argument(
        "--search", default="iti", help="запрос автоподбора (по умолчанию iti)"
    )
    ap.add_argument(
        "--student-profile",
        metavar="FILE",
        help=(
            "путь к JSON-файлу профиля студента: содержимое передаётся серверу "
            "в env GSTU_STUDENT, проверяются get_student_profile и get_schedule "
            "без slug (дефолты из профиля)"
        ),
    )
    return ap


if __name__ == "__main__":
    argv = build_parser().parse_args()
    raise SystemExit(asyncio.run(main(argv)))
