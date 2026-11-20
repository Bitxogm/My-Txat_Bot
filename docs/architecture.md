# Arquitectura

## Vista general

```
Navegador (PWA)
   │  HTTP/SSE, solo LAN o Tailscale
   ▼
frontend (Vite build servido por nginx)
   │  /api/*
   ▼
backend (FastAPI) ──── SQLite (data/txatbot.db)
   │                └── ChromaDB (opcional, RAG)
   │  HTTP, Tailscale
   ▼
Ollama (máquina con GPU, puerto 11434)
```

- **frontend**: SPA React. Todo acceso a la API pasa por un único cliente (`src/lib/api`).
- **backend**: FastAPI asíncrono. Orquesta conversaciones, personalidades, ficheros y llamadas al modelo.
- **Ollama**: servicio aparte. Por defecto remoto (Acer con RTX 3060 vía Tailscale). Opcionalmente en el mismo Compose con el perfil `ollama`.
- **Datos**: SQLite en `data/`, montado como volumen. Uploads en `data/uploads/`.

## Backend (estructura prevista)

Arquitectura hexagonal ligera:

```
backend/app/
  main.py            app FastAPI, middlewares, handlers
  core/              config (pydantic-settings), logging, errores, request id
  api/routes/        routers HTTP (health, auth, chat, models, files, personas)
  domain/            entidades y casos de uso, sin dependencias de framework
  ports/             interfaces (LLMProvider, ConversationRepository, ...)
  adapters/          implementaciones (ollama, sqlite, chroma)
```

- El modelo no está acoplado: `LLMProvider` define el contrato y `OllamaProvider` lo implementa.
- Acceso a datos con repository pattern.

## Autenticación

- `POST /api/auth/login` `{ username, password }` → 204 + cookie de sesión. 401 `INVALID_CREDENTIALS`, 429 `TOO_MANY_ATTEMPTS`, 503 `AUTH_NOT_CONFIGURED`.
- `POST /api/auth/logout` (con sesión) → 204, borra la cookie e invalida todas las sesiones emitidas.
- `GET /api/auth/me` → `{ username }` o 401 `UNAUTHORIZED`.
- Detalles de seguridad en [security.md](security.md).

## Conversaciones

Requieren sesión. Persisten en SQLite (`data/txatbot.db`) vía `ConversationRepository` (`adapters/sqlite`, aiosqlite). Esquema versionado con `PRAGMA user_version` en `adapters/sqlite/database.py`: las migraciones solo se añaden al final de `MIGRATIONS`.

- `GET /api/conversations` → `{ conversations: [{ id, title, model, created_at, updated_at }] }`, por actividad reciente.
- `POST /api/conversations` `{ model? }` → 201 con la conversación (título provisional "Nueva conversación").
- `GET /api/conversations/{id}` → conversación + `messages: [{ id, role, content, status, created_at }]`.
- `PATCH /api/conversations/{id}` `{ title }` · `DELETE /api/conversations/{id}` → 204.
- `POST /api/conversations/{id}/messages` `{ content, model? }` → mismo SSE que `/api/chat`. El servidor guarda el mensaje del usuario, construye el historial desde la base de datos y guarda la respuesta como `done`, `stopped` (el cliente cortó) o `error` (con el texto parcial). El primer mensaje da el título.
- Los turnos con error y las respuestas vacías no se reenvían al modelo.

## API de chat

Requiere sesión (401 sin cookie válida). `/api/chat` es la variante sin estado (el cliente manda todo el historial y no se guarda nada).

- `GET /api/models`: modelos disponibles en Ollama (`name`, `size_bytes`, `family`, `parameter_size`, `quantization`) y `default_model`.
- `POST /api/chat` con `{ "model"?: string, "messages": [{ "role": "system"|"user"|"assistant", "content": string }] }`. Si no se indica `model` se usa `DEFAULT_MODEL`.
- Respuesta `text/event-stream`:
  - `event: token` / `data: {"content": "..."}` por cada fragmento.
  - `event: done` / `data: {"model": "..."}` al terminar.
  - `event: error` / `data: {code, message, request_id}` si falla con el stream ya empezado.
- Los fallos antes del primer token (modelo inexistente → 404 `MODEL_NOT_FOUND`, Ollama caído → 503 `MODEL_UNAVAILABLE`) devuelven el JSON de error normal.
- Si el cliente corta la conexión, el backend cierra la petición a Ollama.

## Frontend (estructura prevista)

```
frontend/src/
  lib/api/          cliente API único + mapeo de errores
  components/ui/    componentes shadcn/ui (generados)
  components/       componentes propios
  features/         chat, models, personas, files, settings
  pages/
```

## Manejo de errores

**Backend**
- Handler global que devuelve siempre el mismo formato JSON:

  ```json
  { "error": { "code": "MODEL_UNAVAILABLE", "message": "Texto legible", "request_id": "..." } }
  ```
- Middleware de `request_id`: lo genera (o lo toma de `X-Request-ID`), lo añade a cada log y a la cabecera de respuesta.
- Nunca se devuelven trazas ni detalles internos al cliente; se loguean en el servidor.
- `GET /api/health` responde 200 si el backend está vivo e informa en el cuerpo si Ollama responde (Ollama caído no marca el contenedor como unhealthy).

**Frontend**
- Un solo cliente API (`src/lib/api`: `request`, `getHealth`, `listModels`, `streamChat`) que lanza `ApiError` con `kind`, `status`, `code`, `message` y `requestId`. Mapea códigos HTTP a `kind`:
  - 400/422 → validación (mensaje en el formulario)
  - 401 → sesión caducada (redirige a login)
  - 403 → sin permiso
  - 404 → no encontrado
  - 413 → fichero demasiado grande
  - 429 → demasiadas peticiones
  - 5xx / red → error genérico + toast (Sonner) con el `request_id`
- 401 dispara el handler registrado con `setUnauthorizedHandler` (redirección a login).
- `streamChat` lee el SSE con `fetch` + `ReadableStream`; un evento `error` o un corte sin `done` también lanzan `ApiError`. Las cancelaciones (`AbortSignal`) se relanzan tal cual (`isAbortError`).
- `notifyError(error)` (`src/lib/notify-error.ts`) muestra el toast; ignora cancelaciones.

**Docker**
- Rotación de logs `json-file` (10 MB x 3) en todos los servicios.
- Healthcheck en el backend contra `/api/health`.

## Hardware

| Máquina | GPU | Rol |
| --- | --- | --- |
| Acer (Kali) | RTX 3060 12 GB | Host de Ollama ahora |
| X570 (Ubuntu) | Posible 2x RTX 3060 en el futuro | Desarrollo |

Con 12 GB de VRAM el techo práctico son modelos de 7-14B cuantizados (Q4/Q5) con contexto moderado. Modelos más grandes o varios a la vez no caben; el selector debe mostrar solo lo que Ollama tiene cargado o disponible.
