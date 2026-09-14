"""Оркестрация: загрузка, фильтрация, форматирование, вывод/сохранение."""

from __future__ import annotations

import datetime as dt
import os
import sys

from .config import Config
from .engine import scheduled_days, term_start, week_days, week_number
from .fetcher import fetch_schedule
from .formatters import format_console, format_json, format_md, validate_lesson_template
from .models import Entity, ScheduleItem, parse_payload


def _ref_date(cfg: Config) -> dt.date:
    if cfg.date:
        return dt.date.fromisoformat(cfg.date)
    return dt.date.today()


def _output_name(cfg: Config, view_tag: str, date: dt.date) -> str:
    if cfg.output_file:
        return cfg.output_file
    parts = [cfg.group]
    if cfg.subgroup is not None:
        parts.append(f"sub{cfg.subgroup}")
    parts.append(view_tag)
    parts.append(date.isoformat())
    return "_".join(parts)


def _ensure_dir(path: str) -> None:
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def _week_title(d: dt.date, start: dt.date) -> str:
    wn = week_number(d, start)
    parity = "нечётная" if wn % 2 else "чётная"
    monday = d - dt.timedelta(days=d.weekday())
    sunday = monday + dt.timedelta(days=6)
    return f"Неделя: {monday.isoformat()} – {sunday.isoformat()} (нед. {wn}, {parity})"


def _date_title(d: dt.date, start: dt.date) -> str:
    wn = week_number(d, start)
    parity = "нечётная" if wn % 2 else "чётная"
    return f"Дата: {d.isoformat()} (нед. {wn}, {parity})"


def run(cfg: Config) -> int:
    api_url = cfg.effective_api_url()
    try:
        payload = fetch_schedule(api_url)
    except RuntimeError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1

    try:
        entity, items = parse_payload(payload, cfg.group)
    except (ValueError, KeyError) as exc:
        print(f"ОШИБКА: некорректный ответ API: {exc}", file=sys.stderr)
        return 1

    if not items:
        print("Расписание пустое.", file=sys.stderr)
        return 1

    ref = _ref_date(cfg)
    t_start = (
        dt.date.fromisoformat(cfg.semester_start)
        if cfg.semester_start
        else term_start(items)
    )

    unknown_placeholders = validate_lesson_template(cfg.lesson_format)
    if unknown_placeholders:
        print(
            "ОШИБКА: неизвестные плейсхолдеры в lesson_format: "
            + ", ".join(unknown_placeholders),
            file=sys.stderr,
        )
        return 1

    if cfg.view == "week":
        dates = week_days(ref)
        title = _week_title(ref, t_start)
    else:
        dates = [ref]
        title = _date_title(ref, t_start)

    scheduled = scheduled_days(items, dates, cfg.subgroup, t_start, cfg.lesson_types)

    formats = (
        ["console", "md", "json"] if cfg.output_format == "all" else [cfg.output_format]
    )

    for fmt in formats:
        if fmt == "console":
            text = format_console(
                entity,
                dates,
                scheduled,
                cfg.subgroup,
                cfg.lesson_types,
                title,
                cfg.lesson_format,
            )
            print(text)
        else:
            _ensure_dir(cfg.output_dir)
            base_name = _output_name(cfg, cfg.view, ref)
            if fmt == "md":
                ext = "md"
                content = format_md(
                    entity,
                    dates,
                    scheduled,
                    cfg.subgroup,
                    cfg.lesson_types,
                    title,
                    cfg.lesson_format,
                )
            elif fmt == "json":
                ext = "json"
                content = format_json(
                    entity,
                    dates,
                    scheduled,
                    cfg.subgroup,
                    cfg.lesson_types,
                    title,
                    cfg.lesson_format,
                )
            else:
                continue
            out_path = os.path.join(cfg.output_dir, f"{base_name}.{ext}")
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"Сохранено: {out_path}", file=sys.stderr)
    return 0
