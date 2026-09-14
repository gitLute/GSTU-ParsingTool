"""Загрузка расписания с сервера ГГТУ по API-ссылке."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

API_TIMEOUT_SECONDS = 30
USER_AGENT = "GSTU-ParsingTool/0.1"

DEFAULT_API_BASE_URL = "https://sc.gstu.by/api/schedules/group/"


def build_api_url(base_url: str, group_slug: str) -> str:
    """Собирает полный URL вида .../api/schedules/group/{slug}."""
    base = base_url.rstrip("/")
    if not base.endswith("/api/schedules/group"):
        base += "/api/schedules/group"
    return f"{base}/{group_slug}"


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
