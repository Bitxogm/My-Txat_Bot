# Arquitectura

## Vista general

```
Navegador (PWA)
   │  HTTP/SSE, LAN de casa (Tailscale opcional)
   ▼
frontend (Vite build servido por nginx)
   │  /api/*
   ▼
backend (FastAPI) ──── SQLite (data/txatbot.db) + uploads (data/uploads/)
   │    │           └── ChromaDB (futuro, RAG)
   │    │  HTTPS (opcional, sale de la red)
   │    └──────────▶ proveedores compatibles con OpenAI (Groq en la nube, LM Studio local…)
   │  HTTP, 127.0.0.1 / host.docker.internal (misma máquina)
   ▼
Ollama (puerto 11434, GPU: todos los modelos locales, ADR-020)
```

- **frontend**: SPA React. Todo acceso a la API pasa por un único cliente (`src/lib/api`).
- **backend**: FastAPI asíncrono. Orquesta conversaciones, personalidades, ficheros y llamadas al modelo.
- **Ollama**: servicio aparte en la misma máquina (instalado en el host, o en el Compose con el perfil `ollama`). Escucha solo en `127.0.0.1`; el backend en Docker llega por `host.docker.internal` (Docker Desktop lo reenvía al loopback del host) o por `ollama:11434`.
- **Un solo motor local (ADR-020)**: todos los modelos locales en Ollama, que comparte la GPU entre ellos cargando y descargando al cambiar de modelo. LM Studio u otro servidor local solo si tiene su propia GPU o máquina.
- **Despliegue previsto**: una sola máquina (torre Acer, RTX 3060 12 GB) con todo dentro. Acceso por la LAN de casa (frontend en `BIND_ADDR`); backend, Ollama y LM Studio solo en `127.0.0.1`. Tailscale es opcional (acceso desde fuera de casa o HTTPS para la PWA).
- **Proveedores compatibles con OpenAI (opcionales, ADR-019)**: los de `PROVIDERS`, cada uno con su `PROVIDER_<NOMBRE>_*`. Remotos (Groq) o locales (`_LOCAL=true`: LM Studio, llama.cpp).
- **Datos**: SQLite en `data/`, montado como volumen. Uploads en `data/uploads/`.

## Backend

Arquitectura hexagonal ligera:

```
backend/app/
  main.py            app FastAPI, middlewares, handlers, wiring (lifespan)
  cli.py             hash-password, session-secret, dev-login
  core/              config (pydantic-settings), logging, errores, request id
  api/routes/        health, auth, chat, models, conversations, attachments,
                     personalities, osint_sources
  domain/            entidades y reglas sin framework: prompts, personalidades, OSINT, adjuntos
  ports/             interfaces (LLMProvider, repositorios, FileStorage)
  adapters/          ollama, openai_compat, routing.py, sqlite (repositorios y migraciones),
                     files (almacenamiento local, proceso aislado, PDF, imágenes)
```

- El modelo no está acoplado: `LLMProvider` define el contrato; `OllamaProvider` (local) y `OpenAICompatibleProvider` (uno por proveedor de `PROVIDERS`) lo implementan, y `RoutingLLMProvider` los junta en una sola lista de modelos (los de cada proveedor con el prefijo `<nombre>/`). La configuración se lee en `core/config.py` (`Settings.provider_list`) y la fábrica está en `adapters/llm_factory.py`.
- Acceso a datos con repository pattern.

## Autenticación

- `POST /api/auth/login` `{ username, password }` → 204 + cookie de sesión. 401 `INVALID_CREDENTIALS`, 429 `TOO_MANY_ATTEMPTS`, 503 `AUTH_NOT_CONFIGURED`.
- `POST /api/auth/logout` (con sesión) → 204, borra la cookie e invalida todas las sesiones emitidas.
- `GET /api/auth/me` → `{ username }` o 401 `UNAUTHORIZED`.
- Detalles de seguridad en [security.md](security.md).

## Personalidades (ADR-013)

Requieren sesión. `system prompt = capa base (domain/prompts.py) + personalidad`.

- `GET /api/personalities` → `{ personalities: [...] }`: las 9 incorporadas (`builtin: true`, ids `builtin-*`) primero, luego las copias.
- `GET/PATCH/DELETE /api/personalities/{id}`: editar o borrar una incorporada → 403 `PERSONALITY_BUILTIN`. `PATCH` es parcial; enviar `null` limpia un parámetro.
- `POST /api/personalities` y `POST /api/personalities/{id}/duplicate` → 201 (siempre `builtin: false`).
- Campos: `name` (1-60), `icon` (nombre de icono lucide), `description` (≤200), `system_prompt` (1-8000), `temperature` (0-2), `top_p` (0-1], `num_ctx` (512-16384: más contexto desborda la GPU de 12 GB con un 14B), `default_model`; los parámetros son opcionales (null = valor del modelo).

## Catálogo OSINT (ADR-014)

Requiere sesión.

- `GET /api/osint-sources?category=` → `{ sources: [...] }`: incorporadas (`builtin: true`, ids `osint-*`) primero.
- `POST /api/osint-sources` → 201 (siempre `builtin: false`; máximo 100 propias → 409 `OSINT_SOURCE_LIMIT`).
- `PUT /api/osint-sources/{id}`: sustitución completa (`is_active` obligatorio) en las propias; en una incorporada solo puede cambiar `is_active` (cualquier otro campo distinto → 403 `OSINT_SOURCE_BUILTIN`).
- `POST /api/osint-sources/{id}/toggle`: activa o desactiva (también incorporadas).
- `DELETE /api/osint-sources/{id}`: solo las propias (incorporada → 403).
- Campos: `name` (1-60, una línea), `url` (`http(s)`, ASCII, dominio DNS público, ≤300, sin credenciales), `category`, `description` (≤200, una línea), `requires_api_key`, `requires_payment`, `is_active`.
- Las fuentes activas se inyectan en el prompt del Auditor de Huella Digital en cada turno.

## Conversaciones

Requieren sesión. Persisten en SQLite (`data/txatbot.db`) vía `ConversationRepository` (`adapters/sqlite`, aiosqlite). Esquema versionado con `PRAGMA user_version` en `adapters/sqlite/database.py`: las migraciones solo se añaden al final de `MIGRATIONS`.

- `GET /api/conversations` → `{ conversations: [{ id, title, model, created_at, updated_at }] }`, por actividad reciente.
- `POST /api/conversations` `{ model?, personality_id? }` → 201 con la conversación (título provisional "Nueva conversación"). Sin `personality_id`, General (ADR-021). Modelo: el enviado, si no el `default_model` de la personalidad, si no `DEFAULT_MODEL`. Las conversaciones devuelven `personality: { id, name, icon } | null` (snapshot, solo lectura).
- `GET /api/conversations/{id}` → conversación + `messages: [{ id, role, content, status, created_at }]`.
- `PATCH /api/conversations/{id}` `{ title?, personality_id? }`: `personality_id` solo mientras sea borrador (sin mensajes del usuario); después, 409 `PERSONALITY_LOCKED` (ADR-022) · `DELETE /api/conversations/{id}` → 204.
- Borradores (ADR-022): las conversaciones sin mensajes del usuario no salen en `GET /api/conversations`; las que no tienen ningún mensaje y pasan de 24 h se borran al arrancar, con sus ficheros.
- `POST /api/conversations/{id}/messages` `{ content, model?, attachment_ids? }` → mismo SSE que `/api/chat`. El servidor guarda el mensaje del usuario, antepone el system prompt compuesto (base + snapshot de la personalidad), construye el historial desde la base de datos y guarda la respuesta como `done`, `stopped` (el cliente cortó) o `error` (con el texto parcial). El primer mensaje da el título.
- Los turnos con error y las respuestas vacías no se reenvían al modelo.
- Si el modelo falla **antes del primer token** (límite 429, servidor caído, modelo inexistente, respuesta vacía), el turno se deshace: se borra el mensaje del usuario, sus adjuntos vuelven a pendientes y la conversación no cambia de modelo ni de título. El cliente devuelve el texto al compositor. Un fallo a mitad de respuesta sí se guarda (`error`, con el texto parcial).
- Ajuste al contexto (ADR-018, `domain/context.py`): antes de guardar nada, el historial se recorta para caber en el contexto del modelo (`num_ctx` de la personalidad, si no `OLLAMA_NUM_CTX`; `PROVIDER_<NOMBRE>_CONTEXT_TOKENS` en los proveedores compatibles con OpenAI), dejando sitio para la respuesta. Se conservan los turnos más nuevos; los antiguos pierden primero las imágenes, luego el contenido de sus ficheros y, al final, desaparecen, y el modelo recibe una nota de cuántos se omitieron. Si ni el mensaje nuevo cabe (con sus ficheros recortados) → 400 `CONTEXT_TOO_LONG`, sin guardarlo. `/api/chat` se ajusta igual.

## Ficheros adjuntos (ADR-015, ADR-016)

Requieren sesión. Tabla `attachments` (migración v4); el fichero en `UPLOAD_DIR` (`data/uploads/`) con nombre uuid.

- `POST /api/conversations/{id}/attachments` (multipart, campo `file`) → 201 `{ id, filename, mime, kind: "text"|"pdf"|"image", size_bytes, truncated, sent, created_at }`. Errores: 411 `LENGTH_REQUIRED` (sin `Content-Length`), 413 `PAYLOAD_TOO_LARGE` (> `UPLOAD_MAX_MB`), 415 `UNSUPPORTED_MEDIA_TYPE`, 422 `UNREADABLE_FILE` (vacío, PDF cifrado, dañado o sin texto, imagen rota o de más de 40 MP), 400 si ya hay 5 pendientes.
- `GET /api/conversations/{id}/attachments` → `{ attachments: [...] }` · `DELETE …/attachments/{attachment_id}` → 204, solo pendientes.
- Envío: `POST /api/conversations/{id}/messages` acepta `attachment_ids` (máx. 5, pendientes de esa conversación; otro → 404 `ATTACHMENT_NOT_FOUND`, ya enviado → 400). Cada mensaje del detalle lleva `attachments: [{ id, filename, kind, size_bytes, truncated }]`.
- El texto de los ficheros va al modelo dentro del mensaje del usuario como bloques `<fichero>` de datos, también en los turnos siguientes del historial.
- Imágenes: se guardan recodificadas (≤1568 px, sin metadatos) y van al modelo como imágenes, solo si tiene visión (si no, 400 `MODEL_WITHOUT_VISION`) y solo las 4 más recientes de la conversación. `GET …/attachments/{attachment_id}/content` devuelve la imagen (solo imágenes) para las miniaturas.
- Frontend: el clip del compositor sube cada fichero al momento (en un chat nuevo crea antes la conversación) y lo muestra como chip; el envío espera a que terminen las subidas. Al abrir una conversación vuelven al compositor sus adjuntos pendientes. Con un modelo en la nube se avisa de que el contenido sale de la red. Las imágenes se ven como miniaturas (en el compositor y en el mensaje, que enlaza a la imagen completa); el selector marca los modelos que «ven imágenes», el envío se bloquea si hay imágenes y el modelo no las ve, y con un modelo remoto con visión se avisa de que las imágenes recientes de la conversación también salen de la red.

## API de chat

Requiere sesión (401 sin cookie válida). `/api/chat` es la variante sin estado (el cliente manda todo el historial y no se guarda nada).

- `GET /api/models`: modelos de Ollama y de cada proveedor de `PROVIDERS` (`name`, `size_bytes`, `family`, `parameter_size`, `quantization`, `remote`, `vision`, `provider`) y `default_model`. `remote` es `false` en Ollama y en los proveedores con `_LOCAL=true`. Si un proveedor falla, se devuelven los demás.
- `POST /api/chat` con `{ "model"?: string, "messages": [{ "role": "system"|"user"|"assistant", "content": string }] }`. Si no se indica `model` se usa `DEFAULT_MODEL`.
- Respuesta `text/event-stream`:
  - `event: token` / `data: {"content": "..."}` por cada fragmento.
  - `event: done` / `data: {"model": "..."}` al terminar.
  - `event: error` / `data: {code, message, request_id}` si falla con el stream ya empezado.
- Los fallos antes del primer token (modelo inexistente → 404 `MODEL_NOT_FOUND`, Ollama caído → 503 `MODEL_UNAVAILABLE`, respuesta sin texto → 502 `EMPTY_REPLY`) devuelven el JSON de error normal.
- Razonamiento de los modelos que lo tienen (qwen3.5, deepseek-r1…) desactivado por defecto (`OLLAMA_THINK=false`): con él, Ollama manda el razonamiento aparte, el backend lo ignora y la primera palabra puede tardar minutos o no llegar si se agota el límite de longitud.
- Si el cliente corta la conexión, el backend cierra la petición a Ollama.

## Evaluación de respuestas

`evals/questions.yaml` es una batería fija de preguntas (comandos, datos comprobables, trampas, inyección de prompt, método del Mentor y límites de OSINT). `uv run python -m app.cli eval --models <modelos> [--think on|off] [--personality <nombre>] [--only <ids>]` (desde `backend/`) las hace con la misma composición de prompt, el mismo ajuste de contexto y el mismo `LLMProvider` que el chat (`app/adapters/llm_factory.py`), y escribe un informe por modelo en `evals/reports/` (fuera de git):
- Comprobaciones automáticas por pregunta: `must_any` (cada grupo de regex debe aparecer) y `must_not` (ninguno), más la global de idioma (en español). `warn` (por pregunta) y los emojis (global) solo salen como avisos en el informe, no suspenden.
- Junto a cada informe `.md` se guarda un `.json` con las respuestas en bruto. `eval --recheck <informe>` las vuelve a corregir con las reglas actuales sin llamar al modelo (los informes antiguos sin JSON se leen del propio `.md`). Con `--personality`, el nombre del informe lleva la personalidad.
- Las que piden juicio (trampas, Mentor, límites) salen como "REVISIÓN MANUAL".
- `--models` acepta modelos de cualquier proveedor (`lmstudio/<id>`, `groq/<id>`…); `--list-models` da los ids exactos. Un modelo no disponible se omite con un aviso. Cada informe registra el proveedor, si es local y la huella de la capa base (`BASE_PROMPT_VERSION`).
- Las tablas resumen se versionan en [evals.md](evals.md), que se actualiza en cada PR que mida.
- No va en la CI (necesita modelos); el corrector tiene tests unitarios.

## Frontend

```
frontend/src/
  lib/api/          cliente API único + mapeo de errores
  components/ui/    componentes shadcn/ui (generados)
  components/       componentes propios (error boundary…)
  features/         auth, chat (mensajes, Markdown, adjuntos), conversations,
                    personalities, osint-sources
```

Entrada al chat: abrir Txat o pulsar "Nueva conversación" lleva directo al chat con el compositor enfocado. En la cabecera, junto al selector de modelo, un desplegable de personalidad (General por defecto) que muestra icono y nombre, y la descripción en el menú. Se puede cambiar hasta el primer mensaje (si ya hay borrador, con `PATCH /api/conversations/{id}` `{ personality_id }`); después queda fijo, con candado y el aviso "La personalidad se fija al empezar la conversación". Las tarjetas de personalidad se usan en la página de gestión, con sus acciones (ver/editar, duplicar, borrar).

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
  - 415 → tipo de fichero no admitido
  - 429 → demasiadas peticiones
  - 5xx / red → error genérico + toast (Sonner) con el `request_id`
- 401 dispara el handler registrado con `setUnauthorizedHandler` (redirección a login).
- `streamChat` lee el SSE con `fetch` + `ReadableStream`; un evento `error` o un corte sin `done` también lanzan `ApiError`. Las cancelaciones (`AbortSignal`) se relanzan tal cual (`isAbortError`).
- `notifyError(error)` (`src/lib/notify-error.ts`) muestra el toast; ignora cancelaciones.
- Fallo antes de la respuesta (error HTTP antes del stream): el backend no guarda el turno (ADR-019) y el chat tampoco lo deja en pantalla; el texto vuelve al compositor tal cual y los adjuntos a pendientes.
- Límite de un proveedor (`MODEL_RATE_LIMITED`, con `provider` y `retry_after` en `ApiError`): en vez de toast, aviso sobre el compositor "Límite de <proveedor> alcanzado. Disponible en N s" con cuenta atrás y, si `DEFAULT_MODEL` está en la lista y es local, el botón "Responder ahora con <modelo>", que reenvía el mismo texto y los mismos adjuntos con ese modelo. El modelo nunca cambia sin esa pulsación.

**PWA (ADR-017)**
- `vite-plugin-pwa` (`frontend/src/pwa/options.ts`): `generateSW`, precache del shell y nada más; `/api` nunca pasa por el service worker.
- Registro desde React (`virtual:pwa-register/react`, sin script inline por la CSP) en `src/pwa/pwa-updater.tsx`: aviso "Nueva versión disponible · Recargar" y búsqueda de versión nueva cada hora.
- `useAuth` distingue `offline` (error de red o 5xx en `/api/auth/me`): pantalla "Sin conexión con el servidor", reintento manual y automático al volver la red.

**Docker**
- Rotación de logs `json-file` (10 MB x 3) en todos los servicios.
- Healthcheck en el backend contra `/api/health`.
- Contenedores sin root, `read_only`, `cap_drop: [ALL]`, `no-new-privileges` y `mem_limit` (detalle en [security.md](security.md)).

## Hardware

| Máquina | GPU | Rol |
| --- | --- | --- |
| Acer (torre) | RTX 3060 12 GB | Despliegue previsto: todo en esta máquina |
| X570 (Ubuntu, Docker Desktop) | Posible 2x RTX 3060 en el futuro | Desarrollo |

Con 12 GB de VRAM el techo práctico son modelos de 7-14B cuantizados (Q4/Q5) con contexto moderado. Modelos más grandes o varios a la vez no caben; el selector debe mostrar solo lo que Ollama tiene cargado o disponible.
