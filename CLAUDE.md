# CLAUDE.md — Txat_bot

Chatbot personal 100 % local sobre Ollama, con personalidad configurable y orientado a ayudar en labs/CTF autorizados. App de navegador (PWA), totalmente dockerizada.

## Fase actual
**Fase 0 (fundaciones)**: estructura, configs y docs. Sin código de aplicación. Siguiente: Fase 1 (chat mínimo). Detalle en `docs/roadmap.md`. Actualiza esta línea al cambiar de fase.

## Stack
- **Backend**: Python 3.12, FastAPI (async), pydantic-settings, Ruff, pytest. SQLite; ChromaDB solo con RAG.
- **Frontend**: Vite, React, TypeScript (strict), Tailwind, shadcn/ui, Sonner, vite-plugin-pwa, ESLint, Prettier, Vitest.
- **Modelos**: Ollama, servicio aparte. El backend lo alcanza por `OLLAMA_BASE_URL` (nombre Tailscale del host, puerto 11434).
- **Infra**: Docker Compose. Perfil `ollama` para levantar Ollama local con GPU NVIDIA.

## Estructura
- `backend/app/`: `core/` (config, logging, errores), `api/routes/`, `domain/`, `ports/`, `adapters/` (ollama, sqlite, chroma). Hexagonal ligera + repository pattern.
- `frontend/src/`: `lib/api/` (cliente único), `components/ui/` (shadcn, generado), `components/`, `features/`, `pages/`.
- `docs/`: `architecture.md`, `roadmap.md`, `decisions.md` (ADR), `security.md`.
- `data/`: SQLite, uploads y backups. Montado como volumen. Fuera de git.

## Comandos
```bash
docker compose up -d                    # backend + frontend (Ollama remoto)
docker compose --profile ollama up -d   # + Ollama local con GPU
docker compose logs -f backend
docker compose config                   # validar el compose

# backend (desde backend/)
ruff check . && ruff format --check .
pytest

# frontend (desde frontend/)
npm run lint && npm run format:check
npm run test
npm run build
```
Los scripts de npm y el entorno Python se crean en Fase 1.

## Reglas de código
- Backend: todo async; tipado completo; nada de `print`, usar el logger. Config solo vía `core/config.py` (pydantic-settings), nunca `os.environ` suelto.
- El modelo se usa a través del puerto `LLMProvider`. Nada de llamar a Ollama fuera de `adapters/ollama`.
- Frontend: prohibido `fetch` fuera de `src/lib/api` (lo bloquea ESLint). Componentes de `components/ui/` no se editan a mano salvo necesidad.
- Sin `any` en TypeScript. Sin secretos ni URLs fijas en el código.
- Las decisiones de arquitectura nuevas se registran como ADR en `docs/decisions.md`.

## Manejo de errores (convención obligatoria)
- Formato único de error: `{ "error": { "code", "message", "request_id" } }`.
- FastAPI: handler global para `HTTPException`, validación y excepciones no controladas. Nunca se devuelve una traza al cliente.
- Middleware de `request_id` (respeta `X-Request-ID`), presente en logs y cabecera de respuesta.
- `GET /api/health`: estado del backend y de Ollama. Lo usa el healthcheck de Docker.
- Frontend: el cliente API mapea 400/422, 401 (a login), 403, 404, 413, 429 y 5xx/red a errores tipados; los errores genéricos salen en un toast de Sonner con el `request_id`.
- Docker: log rotation `json-file` 10 MB x 3 en todos los servicios (anchor `x-logging`).

## Flujo de trabajo
- Una tarea = una rama = una PR. Nada directo a `main`.
- Antes de abrir PR: lint y tests en verde. Usar la skill `/pre-pr`. La CI (`.github/workflows/ci.yml`) repite lo mismo y escanea secretos con gitleaks.
- Reglas por carpeta en `.claude/rules/` (backend, frontend); se cargan solas al tocar esos ficheros.
- Ramas, commits y títulos de PR en inglés. Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`). Ramas `feat/...`, `fix/...`, `chore/...`, `docs/...`.
- Descripciones de PR en español, siguiendo `.github/pull_request_template.md`.

## Agentes
| Agente | Se encarga de |
| --- | --- |
| `lider` | Divide cada fase en tareas, delega y reporta |
| `backend` | FastAPI, adaptadores (Ollama, SQLite, Chroma), Dockerfile del backend. En este proyecto el stack es Python, no Express/Prisma |
| `frontend` | Vite + React + shadcn/ui, cliente API, PWA. Aquí no hay Next.js ni Zustand salvo que se decida |
| `seguridad-web` | Obligatorio en login/sesión, subida de ficheros y asistente Kali |
| `testing-qa` | Gate antes de cerrar tarea: pytest + Ruff en backend, Vitest + tsc + ESLint en frontend |
| `revisor-pr` | Revisión de PR en solo lectura |
| `sistemas-linux` | Docker, NVIDIA Container Toolkit, Tailscale, problemas de host |

`mobile` y `telefonia-ia` no aplican a este proyecto.

## Límites de hardware
- Host de Ollama ahora: Acer (Kali) con RTX 3060 12 GB. Techo práctico: modelos 7-14B cuantizados (Q4/Q5), un modelo cargado a la vez, contexto moderado.
- X570 (Ubuntu) es la máquina de desarrollo; puede recibir 2x RTX 3060 más adelante.
- No asumir GPU en la máquina que corre backend/frontend.

## Seguridad (trampas activas)
- Repo **público**: nunca commitear `.env`, bases de datos, uploads, modelos, IPs, nombres de host Tailscale reales ni datos personales. Solo `.env.example` con valores vacíos.
- Acceso solo LAN + Tailscale. Puertos publicados en `BIND_ADDR`, nunca `0.0.0.0` por defecto. Sin cambios en el router ni túneles públicos.
- Ollama no tiene auth: jamás exponerlo fuera de Tailscale/localhost.
- Login de un usuario: hash argon2/bcrypt, cookie `httpOnly` + `SameSite=Strict`, nada en `localStorage`.
- Asistente Kali: sugiere comandos, **nunca ejecuta sin confirmación explícita**. Uso solo en entornos propios o autorizados.
- Ficheros subidos: límite de tamaño, lista blanca de MIME, nombre generado en el servidor.
