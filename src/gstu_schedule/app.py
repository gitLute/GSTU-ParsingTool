"""Оркестрация: загрузка, фильтрация, форматирование, вывод/сохранение."""

from __future__ import annotations

import datetime as dt
import os
import sys

from .config import Config
from .engine import (
    merge_duplicate_lessons,
    scheduled_days,
    term_start,
    validate_regex_filters,
    week_days,
    week_number,
)
from .fetcher import fetch_autocomplete, fetch_schedule, parse_api_url
from .formatters import (
    format_autocomplete,
    format_autocomplete_hints,
    format_console,
    format_json,
    format_md,
    validate_lesson_template,
)
from .models import (
    AutocompleteResult,
    Entity,
    ScheduleItem,
    parse_autocomplete,
    parse_payload,
)

_KIND_NOUN = {
    "group": "группы",
    "teacher": "преподавателя",
    "classroom": "аудитории",
}


def _ref_date(cfg: Config) -> dt.date:
    if cfg.date:
        return dt.date.fromisoformat(cfg.date)
    return dt.date.today()


def _output_name(cfg: Config, view_tag: str, date: dt.date) -> str:
    if cfg.output_file:
        return cfg.output_file
    if cfg.api_url and not cfg._explicit_entity:
        slug = parse_api_url(cfg.api_url)[0]
    else:
        slug = cfg.active_slug() or ""
    parts = [slug or "unknown"]
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


def _schedule_kind(cfg: Config) -> str:
    """Тип расписания с учётом полного URL (дважды не переопределяем)."""
    if cfg.api_url and not cfg._explicit_type:
        _url_slug, url_kind = parse_api_url(cfg.api_url)
        if url_kind:
            return url_kind
    return cfg.schedule_type


def _schedule_label(kind: str, display_name: str) -> str:
    noun = _KIND_NOUN.get(kind, "группы")
    return f"Расписание {noun} {display_name}".rstrip()


def _autocomplete_result(query: str, cfg: Config) -> AutocompleteResult | None:
    """Запрос автоподбора. Возвращает ``None`` при ошибке."""
    try:
        payload = fetch_autocomplete(query, cfg.api_base_url)
    except RuntimeError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return None
    if not payload.get("success", True):
        print("ОШИБКА: API вернул success=false", file=sys.stderr)
        return None
    return parse_autocomplete(payload)


def search(query: str, cfg: Config) -> int:
    """Автоподбор: ищет группы/преподавателей/аудитории по ``autocomplete``."""
    query = query.strip()
    result = _autocomplete_result(query, cfg)
    if result is None:
        return 1
    if not result.total:
        print(f"По запросу «{query}» ничего не найдено.", file=sys.stderr)
        return 1
    print(format_autocomplete(result, query, show_hints=False))
    return 0


def search_hints(query: str, cfg: Config) -> int:
    """Автоподбор: выводит только готовые команды ``--kind slug``."""
    query = query.strip()
    result = _autocomplete_result(query, cfg)
    if result is None:
        return 1
    text = format_autocomplete_hints(result)
    if not text:
        print(f"По запросу «{query}» ничего не найдено.", file=sys.stderr)
        return 1
    print(text)
    return 0


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

    kind = _schedule_kind(cfg)
    schedule_label = _schedule_label(kind, entity.display_name)

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

    regex_errors = validate_regex_filters(cfg.regex_filter)
    if regex_errors:
        print(
            "ОШИБКА: некорректные регулярные выражения: " + "; ".join(regex_errors),
            file=sys.stderr,
        )
        return 1

    if cfg.view == "week":
        dates = week_days(ref)
        title = _week_title(ref, t_start)
    else:
        dates = [ref]
        title = _date_title(ref, t_start)

    scheduled = scheduled_days(
        items,
        dates,
        cfg.subgroup,
        t_start,
        cfg.lesson_types,
        cfg.regex_filter,
    )
    scheduled = merge_duplicate_lessons(scheduled)

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
                cfg.regex_filter,
                schedule_label,
                kind,
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
                    cfg.regex_filter,
                    schedule_label,
                    kind,
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
                    cfg.regex_filter,
                    schedule_label,
                    kind,
                )
            else:
                continue
            out_path = os.path.join(cfg.output_dir, f"{base_name}.{ext}")
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"Сохранено: {out_path}", file=sys.stderr)
    return 0
