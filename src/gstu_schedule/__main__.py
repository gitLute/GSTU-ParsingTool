"""Entry point для ``python -m gstu_schedule``."""

from __future__ import annotations

import sys

from .app import run, search, search_hints
from .cli import apply_args, build_parser
from .config import Config, load_config


def _load_config(path: str) -> "Config | None":
    """Читает конфиг, превращая ошибки файла в аккуратный вывод в stderr."""
    try:
        return load_config(path)
    except (ValueError, OSError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])
    if args.write_default_config:
        from .config import dump_default_config

        dump_default_config(args.config)
        print(f"Создан шаблон: {args.config}")
        return 0
    cfg = _load_config(args.config)
    if cfg is None:
        return 1
    cfg = apply_args(cfg, args)
    if args.search_hints is not None:
        return search_hints(args.search_hints, cfg)
    if args.search is not None:
        return search(args.search, cfg)
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
