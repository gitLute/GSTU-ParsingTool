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


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _dump(label: str, obj) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    print(f"--- {label} ---")
    print(text[:2000])
    print()


async def main(args: argparse.Namespace) -> int:
    params = StdioServerParameters(
        command=SERVER_CMD[0], args=SERVER_CMD[1:], env=_env()
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
            search_res = await session.call_tool(
                "search_entities", {"query": args.search}
            )
            search_text = "".join(
                c.text or "" for c in search_res.content if c.type == "text"
            )
            search_data = json.loads(search_text)
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

            sched_res = await session.call_tool("get_schedule", tool_args)
            sched_text = "".join(
                c.text or "" for c in sched_res.content if c.type == "text"
            )
            sched = json.loads(sched_text)
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
    return ap


if __name__ == "__main__":
    argv = build_parser().parse_args()
    raise SystemExit(asyncio.run(main(argv)))
