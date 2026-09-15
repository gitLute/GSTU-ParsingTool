"""Загрузка расписания с сервера ГГТУ по API-ссылке."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional
from urllib.parse import quote, urlparse

API_TIMEOUT_SECONDS = 30
USER_AGENT = "GSTU-ParsingTool/0.1"

# Поддерживаемые типы расписаний: .../api/schedules/{kind}/{slug}.
SCHEDULE_KINDS = ("group", "teacher", "classroom")

DEFAULT_API_BASE_URL = "https://sc.gstu.by/api/schedules/"


def build_api_url(base_url: str, kind: str, slug: str) -> str:
    """Собирает полный URL вида ``.../api/schedules/{kind}/{slug}``.

    ``base_url`` может быть как корнем домена, так и уже содержать
    ``/api/schedules`` (в том числе с указанием типа, например
    ``.../api/schedules/group/``) — лишний суффикс будет срезан.
    """
    base = base_url.rstrip("/")
    for k in SCHEDULE_KINDS:
        suffix = f"/api/schedules/{k}"
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if not base.endswith("/api/schedules"):
        base += "/api/schedules"
    if kind not in SCHEDULE_KINDS:
        kind = SCHEDULE_KINDS[0]
    return f"{base}/{kind}/{slug}"


def parse_api_url(api_url: str) -> tuple[str, Optional[str]]:
    """Разбирает URL ``.../api/schedules/{kind}/{slug}``.

    Возвращает пару ``(slug, kind)``; ``kind`` — ``None``, если в пути
    нет известного типа расписания.
    """
    path = urlparse(api_url).path.rstrip("/")
    segments = path.split("/")
    candidate = segments[-2] if len(segments) >= 2 else ""
    kind = candidate if candidate in SCHEDULE_KINDS else None
    slug = segments[-1] if segments else ""
    return slug, kind


def fetch_schedule(api_url: str, timeout: int = API_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Выполняет GET-запрос и возвращает распарсенный JSON."""
    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} при запросе {api_url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось соединиться с {api_url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Некорректный JSON от {api_url}: {exc}") from exc


def fetch_autocomplete(
    query: str, base_url: str = DEFAULT_API_BASE_URL, timeout: int = API_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Выполняет запрос автоподбора ``/autocomplete?q=...``."""
    base = base_url.rstrip("/")
    url = f"{base}/autocomplete?q={quote(query)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} при запросе {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось соединиться с {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Некорректный JSON от {url}: {exc}") from exc
