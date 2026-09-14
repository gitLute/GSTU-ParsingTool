"""CLI-интерфейс: параметры командной строки перекрывают конфиг."""

from __future__ import annotations

import argparse
import datetime as dt

from .config import DEFAULT_CONFIG_PATH, Config


def _iso_date(value: str) -> str:
    dt.date.fromisoformat(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gstu-schedule",
        description="Консольная утилита показа/сохранения расписания групп ГГТУ.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"путь к JSON-конфигу (по умолчанию: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("--group", help="slug группы, например iti-31")
    parser.add_argument(
        "--api-url", help="полный URL API (перекрывает api_base_url+group)"
    )
    parser.add_argument(
        "--subgroup",
        type=int,
        help="номер подгруппы; если не указан — показываются обе",
    )
    parser.add_argument(
        "--view",
        choices=("week", "date"),
        help="формат показа: week — неделя, date — конкретная дата",
    )
    parser.add_argument(
        "--date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="опорная дата (по умолчанию сегодня)",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("console", "md", "json", "all"),
        help="формат вывода",
    )
    parser.add_argument("--output-dir", help="каталог для файлов вывода")
    parser.add_argument("--output-file", help="имя файла вывода без расширения")
    parser.add_argument(
        "--write-default-config",
        action="store_true",
        help="создать config.json по умолчанию и завершиться",
    )
    return parser


def apply_args(cfg: Config, args: argparse.Namespace) -> Config:
    if args.group is not None:
        cfg.group = args.group
    if args.api_url is not None:
        cfg.api_url = args.api_url
    if args.subgroup is not None:
        cfg.subgroup = args.subgroup
    if args.view is not None:
        cfg.view = args.view
    if args.date is not None:
        cfg.date = args.date
    if args.output_format is not None:
        cfg.output_format = args.output_format
    if args.output_dir is not None:
        cfg.output_dir = args.output_dir
    if args.output_file is not None:
        cfg.output_file = args.output_file
    return cfg
