"""Entry point для ``python -m gstu_schedule``."""

from __future__ import annotations

import sys

from .app import run, search
from .cli import apply_args, build_parser
from .config import load_config


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])
    if args.write_default_config:
        from .config import dump_default_config

        dump_default_config(args.config)
        print(f"Создан шаблон: {args.config}")
        return 0
    cfg = load_config(args.config)
    cfg = apply_args(cfg, args)
    if args.search is not None:
        return search(args.search, cfg)
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
