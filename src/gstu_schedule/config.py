"""Загрузка конфигурации из JSON-файла и задание значений по умолчанию."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Optional

from .fetcher import DEFAULT_API_BASE_URL

DEFAULT_CONFIG_PATH = "config.json"


@dataclass
class Config:
    """Параметры запуска (совместимо с config.json)."""

    # Группа (slug), например "iti-31".
    group: str = "iti-31"
    # Базовый URL API. Полный URL строится как {api_base_url}/{group}.
    api_base_url: str = DEFAULT_API_BASE_URL
    # Полный URL API; если задан, используется как есть.
    api_url: Optional[str] = None
    # Номер подгруппы (1, 2, ...). null — показывать обе.
    subgroup: Optional[int] = None
    # Фильтр по типу занятия: ["лаб", "лек", ...]. Пустой список — все.
    # Значение "none" соответствует занятиям без типа.
    lesson_types: list = field(default_factory=list)
    # Фильтр по регулярным выражениям: список шаблонов; занятие подходит,
    # если его текст совпал хотя бы с одним. None — без фильтра.
    regex_filter: Optional[list[str]] = None
    # Формат показа: "date" — конкретная дата, "week" — неделя.
    view: str = "week"
    # Опорная дата (YYYY-MM-DD), по умолчанию сегодня.
    date: Optional[str] = None
    # Начало первой недели семестра (YYYY-MM-DD); null — вычисляется из API.
    semester_start: Optional[str] = None
    # Формат вывода: console | md | json | all.
    output_format: str = "console"
    # Шаблон строки одного занятия (см. lesson_format в README).
    # null — встроенные форматы по умолчанию.
    lesson_format: Optional[str] = None
    # Каталог для файлов при output_format md/json/all.
    output_dir: str = "out"
    # Имя файла вывода (без расширения); по умолчанию генерируется.
    output_file: Optional[str] = None

    def effective_api_url(self) -> str:
        if self.api_url:
            return self.api_url
        base = self.api_base_url.rstrip("/")
        if not base.endswith("/api/schedules/group"):
            base += "/api/schedules/group"
        return f"{base}/{self.group}"


def _coerce_lesson_types(value) -> list[str]:
    """Принимает список или строку с типами, разделёнными запятыми."""
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return [str(t) for t in value]


def _coerce_regex_filter(value) -> Optional[list[str]]:
    """Принимает одну строку-шаблон или список шаблонов."""
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(t) for t in value]


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    """Читает конфиг из JSON, дополняя отсутствующие поля значениями по умолчанию."""
    cfg = Config()
    if not os.path.exists(path):
        return cfg
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Конфиг {path}: ожидается JSON-объект")
    known = {f.name: f for f in fields(Config)}
    for key, value in raw.items():
        if key not in known:
            raise ValueError(f"Конфиг {path}: неизвестное поле '{key}'")
        if key == "lesson_types":
            value = _coerce_lesson_types(value)
        elif key == "regex_filter":
            value = _coerce_regex_filter(value)
        setattr(cfg, key, value)
    return cfg


def dump_default_config(path: str = DEFAULT_CONFIG_PATH) -> None:
    """Записывает конфиг по умолчанию (если файла ещё нет)."""
    if os.path.exists(path):
        return
    cfg = Config()
    data = {
        "group": cfg.group,
        "api_base_url": cfg.api_base_url,
        "api_url": cfg.api_url,
        "subgroup": cfg.subgroup,
        "lesson_types": cfg.lesson_types,
        "regex_filter": cfg.regex_filter,
        "view": cfg.view,
        "date": cfg.date,
        "semester_start": cfg.semester_start,
        "output_format": cfg.output_format,
        "lesson_format": cfg.lesson_format,
        "output_dir": cfg.output_dir,
        "output_file": cfg.output_file,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
