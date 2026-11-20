---
paths:
  - "backend/**"
---

# Reglas backend

- FastAPI async en todo. Nada de llamadas bloqueantes (requests, time.sleep) dentro de endpoints: usar httpx.AsyncClient y asyncio.
- Config solo desde `app/core/config.py` (pydantic-settings). Nunca `os.environ` directo.
- Errores: lanzar excepciones de dominio (`app/core/errors.py`) y dejar que el handler global las convierta a `{ "error": { code, message, request_id } }`. No construir respuestas de error a mano en las rutas.
- Ollama solo desde `app/adapters/ollama`, detrás del puerto `LLMProvider`.
- Acceso a SQLite solo vía repositorios (`app/adapters/sqlite`), nunca SQL en las rutas.
- Cada ruta nueva lleva test en `backend/tests/` (httpx + pytest-asyncio). Ollama se mockea en tests.
- Antes de dar algo por terminado: `uv sync --extra dev` (si cambió el lock) y `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
