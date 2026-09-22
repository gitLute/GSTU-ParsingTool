# Changelog

## [Unreleased]
### Добавлено
- MCP-сервер `gstu_schedule_mcp`: инструменты `get_schedule` и
  `search_entities` (FastMCP, переиспользуют парсер `gstu_schedule`).
- Установочный `pyproject.toml` (hatchling) и консольный скрипт
  `gstu-schedule-mcp-server`.
- Smoke-тест MCP-сервера `scripts/selftest.py` и юнит-тесты
  `tests/test_mcp_server.py` (без сети).

## [1.0.0] - 2026-09-22
### Добавлено
- Инструкция по сборке проекта в бинарный файл (PyInstaller) в README.
### Изменено
- Запуск и примеры использования в README переведены на бинарный файл
  (`./dist/gstu-parsing-tool`) вместо запуска из исходников.
- Релиз `1.0.0-rc.1` переведён в стабильный статус `1.0.0`.

## [1.0.0-rc.1] - 2026-09-22
### Добавлено
- Интеграция CI/CD.
- Парсинг Release Notes.
