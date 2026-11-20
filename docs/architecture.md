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
- Un solo cliente API que mapea códigos HTTP a errores tipados:
  - 400/422 → validación (mensaje en el formulario)
  - 401 → sesión caducada (redirige a login)
  - 403 → sin permiso
  - 404 → no encontrado
  - 413 → fichero demasiado grande
  - 429 → demasiadas peticiones
  - 5xx / red → error genérico + toast (Sonner) con el `request_id`

**Docker**
- Rotación de logs `json-file` (10 MB x 3) en todos los servicios.
- Healthcheck en el backend contra `/api/health`.

## Hardware

| Máquina | GPU | Rol |
| --- | --- | --- |
| Acer (Kali) | RTX 3060 12 GB | Host de Ollama ahora |
| X570 (Ubuntu) | Posible 2x RTX 3060 en el futuro | Desarrollo |

Con 12 GB de VRAM el techo práctico son modelos de 7-14B cuantizados (Q4/Q5) con contexto moderado. Modelos más grandes o varios a la vez no caben; el selector debe mostrar solo lo que Ollama tiene cargado o disponible.
