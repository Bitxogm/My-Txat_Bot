# Decisiones (ADR)

Registro corto de decisiones de arquitectura. Formato: contexto, decisión, consecuencias. Las nuevas van al final.

## ADR-001: Todo en local con Ollama (matizado por ADR-012)
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

## ADR-012: Modelos híbridos, local + nube gratuita (Groq)
- **Contexto**: los modelos que caben en la GPU (≈9B en la GTX 1070, ≈14B en la RTX 3060) inventan flags y rutas en comandos de pentesting. La API de Claude es de pago y Gemini rechaza demasiadas consultas legítimas de CTF.
- **Decisión**: además de Ollama, un proveedor opcional con API compatible con OpenAI (`CLOUD_*` en `backend/.env`), por defecto Groq en su plan gratuito (modelos de 70-120B). `RoutingLLMProvider` junta los dos detrás de `LLMProvider`; los modelos remotos se llaman `<CLOUD_NAME>/<id>` y el selector los separa en el grupo "Nube".
- **Consecuencias**: lo escrito a un modelo en la nube sale de la red y queda sujeto a las condiciones del proveedor; los locales siguen igual (ADR-001). Sin `CLOUD_API_KEY` todo es local. Cambiar de proveedor (OpenRouter, Cerebras) es solo configuración. Los límites del plan gratuito (≈1.000 peticiones/día por modelo) se notan como 429 `MODEL_RATE_LIMITED`.

## ADR-013: Personalidades en dos capas
- **Contexto**: cada uso (CTF, pentest, defensa, informes…) necesita un tono y un método distintos, pero los límites éticos y de rigor tienen que estar siempre.
- **Decisión**:
  - Prompt final = **capa base** fija (`backend/app/domain/prompts.py`, en código, no editable desde la UI) + **capa de personalidad** (editable). La composición se hace en el dominio, nunca en un adaptador: base, encabezado, personalidad delimitada entre `<personalidad>` y `</personalidad>` (esas etiquetas se eliminan del texto editable) y un recordatorio final fijo, porque los modelos pequeños obedecen más al último bloque.
  - Los límites éticos (alcance autorizado, no perfilar a particulares, los datos no son instrucciones) van en la capa base, para que no desaparezcan al duplicar y editar una personalidad. `/api/chat` (sin estado) también antepone la base y no acepta mensajes `system` del cliente.
  - 8 personalidades incorporadas (`domain/builtin_personalities.py`, ids `builtin-*`) creadas al arrancar con un seed idempotente (`builtin=1`). No se editan ni se borran (403 `PERSONALITY_BUILTIN`, también protegido en el repositorio); se duplican y la copia sí se edita o borra.
  - La personalidad se fija al crear la conversación: se guarda `personality_id` y una copia (snapshot) del prompt de personalidad, el nombre, el icono y `temperature`/`top_p`/`num_ctx`. No se cambia a mitad de conversación.
  - Los adaptadores aplican los parámetros que admiten (Ollama: `options`; API compatible con OpenAI: `temperature` y `top_p`, sin `num_ctx`) y descartan el resto en silencio.
- **Consecuencias**: la capa base es una barrera de prompt, no una garantía: una copia editada a propósito puede intentar anularla (el usuario es el dueño). Editar o borrar una personalidad no afecta a conversaciones ya creadas. La capa base se compone en cada turno, así que corregirla sí llega a las conversaciones antiguas. Las conversaciones anteriores a esta migración no tienen personalidad: solo la capa base y los parámetros por defecto del modelo. El seed sobrescribe las incorporadas con lo que haya en el código en cada arranque; las que se quiten del código pasan a ser editables.
