# Decisiones (ADR)

Registro corto de decisiones de arquitectura. Formato: contexto, decisión, consecuencias. Las nuevas van al final.

## ADR-001: Todo en local con Ollama
- **Contexto**: privacidad, sin censura, sin coste por uso.
- **Decisión**: modelos servidos por Ollama en hardware propio.
- **Consecuencias**: el tamaño del modelo lo limita la VRAM (12 GB hoy).

## ADR-002: Agnóstico de modelo
- **Decisión**: el backend habla con una interfaz `LLMProvider`. La UI tiene selector de modelo.
- **Consecuencias**: cambiar de modelo no requiere tocar código. Otros proveedores locales se añadirían como adaptadores.

## ADR-003: Ollama como servicio separado
- **Contexto**: la GPU está en otra máquina (Acer) y puede cambiar.
- **Decisión**: Ollama vive en su propio perfil de Compose. El backend usa `OLLAMA_BASE_URL`, apuntando al nombre Tailscale del host en el puerto 11434.
- **Consecuencias**: la app corre en una máquina y el modelo en otra sin cambios de código.

## ADR-004: FastAPI para el backend
- **Decisión**: Python + FastAPI, Ruff para lint y formato.
- **Motivo**: el ecosistema de IA (RAG, whisper, embeddings) es Python. Async y streaming nativos.

## ADR-005: Vite + React para el frontend
- **Decisión**: Vite + React + TS + Tailwind + shadcn/ui + Sonner + vite-plugin-pwa.
- **Motivo**: es una SPA privada sin SEO; no hace falta SSR. Build estático servido por nginx.

## ADR-006: SQLite como base de datos
- **Decisión**: SQLite en `data/`. ChromaDB solo cuando llegue RAG.
- **Motivo**: un solo usuario, cero mantenimiento, backup = copiar un fichero.

## ADR-007: Acceso solo por LAN y Tailscale
- **Decisión**: ningún puerto abierto en el router. Los puertos se publican en la IP indicada en `BIND_ADDR`.
- **Consecuencias**: acceso remoto solo con Tailscale. Ver [security.md](security.md).

## ADR-008: Formato de error único
- **Decisión**: todas las respuestas de error usan `{ "error": { code, message, request_id } }`. El frontend tiene un único cliente API que las interpreta.

## ADR-009: uv para dependencias Python
- **Decisión**: el backend gestiona dependencias con uv (`pyproject.toml` + `uv.lock` commiteado). La CI instala con `uv sync --locked`.
- **Consecuencias**: entornos reproducibles en local, CI y Docker. Ruff y pytest usan las versiones fijadas en el lock.

## ADR-010: Streaming de chat con SSE sobre POST
- **Decisión**: `POST /api/chat` responde `text/event-stream` con eventos `token`, `done` y `error`. El frontend lo lee con `fetch` + `ReadableStream` (no `EventSource`, que solo admite GET).
- **Motivo**: el historial va en el cuerpo; SSE es más simple que WebSocket y pasa bien por nginx (`X-Accel-Buffering: no`).
- **Consecuencias**: los errores previos al primer token son JSON normales con su status HTTP; los posteriores llegan como evento `error`.

## ADR-011: El servidor es la fuente de verdad de las conversaciones
- **Decisión**: el cliente solo envía el mensaje nuevo (`POST /api/conversations/{id}/messages`); el backend guarda el turno y monta el historial desde SQLite. `/api/chat` se mantiene sin estado.
- **Motivo**: el historial no depende de lo que mande el navegador y la respuesta se guarda aunque el cliente corte (se marca `stopped`).
- **Consecuencias**: una sola conexión aiosqlite en modo WAL (un usuario). Para hacer backup en caliente no basta con copiar `txatbot.db`: hay que copiar también `-wal` o usar `sqlite3 data/txatbot.db ".backup copia.db"`.
