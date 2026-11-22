# CLAUDE.md — Txat_bot

Chatbot personal sobre Ollama (local), con proveedores compatibles con OpenAI opcionales (Groq en la nube, LM Studio en local; ADR-012, ADR-019), personalidad configurable y orientado a ayudar en labs/CTF autorizados. App de navegador (PWA), totalmente dockerizada.

## Fase actual
**Fase 3 (personalización)**: memoria persistente aprobada por el usuario, valoraciones 👍/👎 y exportación del dataset para el fine-tuning. Fases 0-2 cerradas (chat, login, conversaciones, personalidades, catálogo OSINT, adjuntos de texto/PDF/imágenes y PWA). Después: Conocimiento (RAG), Kali y modelo propio. Detalle en `docs/roadmap.md`. Actualiza esta línea al cambiar de fase.

## Stack
- **Backend**: Python 3.12, FastAPI (async), pydantic-settings, Ruff, pytest. SQLite (aiosqlite); ChromaDB solo con RAG. pypdf y Pillow para adjuntos, siempre en el proceso aislado.
- **Frontend**: Vite, React, TypeScript (strict), Tailwind, shadcn/ui, Sonner, vite-plugin-pwa, ESLint, Prettier, Vitest.
- **Modelos**: Ollama, servicio aparte. El backend lo alcanza por `OLLAMA_BASE_URL` (puerto 11434; en la misma máquina: `127.0.0.1` en desarrollo, `host.docker.internal` o `ollama` desde Docker). Opcional: varios proveedores compatibles con OpenAI (`PROVIDERS` + `PROVIDER_<NOMBRE>_*`, ADR-019), p. ej. Groq gratuito y LM Studio local (`_LOCAL=true`). `CLOUD_*` está obsoleto.
- **Infra**: Docker Compose. Perfil `ollama` para levantar Ollama local con GPU NVIDIA.

## Estructura
- `backend/app/`: `core/` (config, logging, errores), `api/routes/`, `domain/`, `ports/`, `adapters/` (`ollama`, `openai_compat`, `routing.py`, `sqlite`, `files`). Hexagonal ligera + repository pattern.
- `frontend/src/`: `lib/api/` (cliente único), `components/ui/` (shadcn, generado), `components/`, `features/` (auth, chat, conversations, personalities, osint-sources).
- `docs/`: `architecture.md`, `roadmap.md`, `decisions.md` (ADR), `security.md`.
- `data/`: SQLite, uploads y backups. Montado como volumen. Fuera de git.

## Comandos
```bash
docker compose up -d                    # backend + frontend (Ollama remoto)
docker compose --profile ollama up -d   # + Ollama local con GPU
docker compose logs -f backend
docker compose config                   # validar el compose

# backend (desde backend/)
uv sync --extra dev                     # entorno en backend/.venv desde uv.lock
uv run uvicorn app.main:app --reload    # desarrollo local (reiniciar cierra las sesiones)
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run python -m app.cli hash-password  # AUTH_PASSWORD_HASH para backend/.env
uv run python -m app.cli session-secret # SESSION_SECRET
uv run python -m app.cli dev-login      # solo local: credenciales aleatorias + tarjeta de acceso rápido
uv run python -m app.cli eval --models qwen3.5:9b [--think on|off] [--personality Pentester]  # batería evals/questions.yaml -> evals/reports/ (no va en CI)
uv run python -m app.cli eval --recheck ../evals/reports/<informe>.md   # re-corrige sin llamar al modelo

# frontend (desde frontend/)
npm run dev                             # :5173, proxy /api -> VITE_DEV_BACKEND_URL (def. :8000)
npm run lint && npm run format:check && npx tsc -b
npm run test -- --run
npm run build
```
Dependencias Python con uv (`uv add`), siempre con `uv.lock` commiteado.

## Reglas de código
- Backend: todo async; tipado completo; nada de `print`, usar el logger. Config solo vía `core/config.py` (pydantic-settings), nunca `os.environ` suelto.
- El modelo se usa a través del puerto `LLMProvider` (`RoutingLLMProvider` reparte entre Ollama y los proveedores por el prefijo `<nombre>/`). Nada de llamar a Ollama fuera de `adapters/ollama` ni a un proveedor fuera de `adapters/openai_compat`.
- Frontend: prohibido `fetch` fuera de `src/lib/api` (lo bloquea ESLint). Componentes de `components/ui/` no se editan a mano salvo necesidad.
- Sin `any` en TypeScript. Sin secretos ni URLs fijas en el código.
- Las decisiones de arquitectura nuevas se registran como ADR en `docs/decisions.md`.
- Prompts (ADR-013): la capa base (`domain/prompts.py`) lleva los límites éticos y no es editable desde la UI. No mover esos límites a una personalidad.

## Manejo de errores (convención obligatoria)
- Formato único de error: `{ "error": { "code", "message", "request_id" } }`.
- FastAPI: handler global para `HTTPException`, validación y excepciones no controladas. Nunca se devuelve una traza al cliente.
- Middleware de `request_id` (respeta `X-Request-ID`), presente en logs y cabecera de respuesta.
- `GET /api/health`: estado del backend y de Ollama. Lo usa el healthcheck de Docker.
- Frontend: el cliente API mapea 400/422, 401 (a login), 403, 404, 413, 415, 429 y 5xx/red a errores tipados; los errores genéricos salen en un toast de Sonner con el `request_id`.
- Docker: log rotation `json-file` 10 MB x 3 en todos los servicios (anchor `x-logging`).

## Flujo de trabajo
- Una tarea = una rama = una PR. Nada directo a `main`.
- Antes de abrir PR: lint y tests en verde. Usar la skill `/pre-pr`. La CI (`.github/workflows/ci.yml`) repite lo mismo y escanea secretos con gitleaks.
- Reglas por carpeta en `.claude/rules/` (backend, frontend); se cargan solas al tocar esos ficheros.
- Ramas, commits y títulos de PR en inglés. Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`). Ramas `feat/...`, `fix/...`, `chore/...`, `docs/...`.
- Descripciones de PR en español, siguiendo `.github/pull_request_template.md`.

### Ciclo de tarea (automático)
Claude hace ramas, commits, push y PRs sin pedir permiso. Void revisa y mergea; Claude **nunca** mergea.
1. `git switch main && git pull`
2. Crear rama `feat/|fix/|chore/|docs/...` en inglés.
3. Implementar con commits pequeños (Conventional Commits, en inglés).
4. Ejecutar `/pre-pr`. Si algo falla, corregir y volver a ejecutarlo.
5. `git push -u origin <rama>`
6. `gh pr create` con título en inglés y descripción en español según `.github/pull_request_template.md`.
7. `gh run watch` hasta que termine la CI. Si falla, corregir, push y repetir.
8. Avisar a Void con el enlace de la PR y el estado de la CI.
9. Cuando Void diga que ha mergeado: `git switch main && git pull`, borrar la rama local (`git branch -D <rama>`: con squash merge git no la ve como mergeada; comprobar antes que la PR está en `MERGED`) y actualizar "Fase actual" si aplica.

`main` está protegida en GitHub (PR obligatoria, checks "Secret scan" y "Backend (Ruff + pytest)", historial lineal, solo squash merge).

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

## Despliegue y hardware
- Despliegue previsto: una sola máquina, la torre Acer (RTX 3060 12 GB), con todo dentro (frontend, backend, Ollama, LM Studio). Los servicios se hablan por `127.0.0.1` / `host.docker.internal`. Techo práctico de la GPU: modelos 7-14B cuantizados (Q4/Q5), un modelo cargado a la vez, contexto moderado (los MoE grandes, a medias con CPU).
- X570 (Ubuntu) es la máquina de desarrollo (Docker Desktop); puede recibir 2x RTX 3060 más adelante.
- Acceso: la LAN de casa (`BIND_ADDR` = IP de LAN). Tailscale es opcional y se decide al desplegar: solo si se quiere acceso desde fuera de casa o HTTPS fácil para instalar la PWA en el móvil.

## Seguridad (trampas activas)
- Repo **público**: nunca commitear `.env`, bases de datos, uploads, modelos, IPs, nombres de host Tailscale reales ni datos personales. Solo `.env.example` con valores vacíos.
- Acceso por la LAN de casa: el frontend se publica en `BIND_ADDR` (IP de LAN), nunca `0.0.0.0` sin decidirlo. Backend y Ollama solo en `127.0.0.1`. Tailscale opcional. Sin puertos abiertos en el router ni túneles públicos en ningún caso.
- Ollama y LM Studio no tienen auth: escuchan solo en `127.0.0.1` (Docker Desktop los alcanza por `host.docker.internal`); nunca en `0.0.0.0` ni con "Serve on Local Network".
- Con un modelo `groq/...` el contenido (mensajes, ficheros, imágenes) sale a un tercero: nada de datos reales ni de clientes; para eso, modelos locales.
- PWA (ADR-017): el service worker nunca maneja `/api` (sin `runtimeCaching`, `/api` fuera del `navigateFallback`). Solo funciona con HTTPS (p. ej. `tailscale serve` si se adopta Tailscale; nunca `funnel`). La API responde `Cache-Control: no-store` por defecto.
- Login de un usuario: hash argon2/bcrypt, cookie `httpOnly` + `SameSite=Strict`, nada en `localStorage`.
- Asistente Kali: sugiere comandos, **nunca ejecuta sin confirmación explícita**. Uso solo en entornos propios o autorizados.
- Ficheros subidos: límite de tamaño, tipo por contenido (no por el MIME del cliente), nombre generado en el servidor. PDF e imágenes se parsean solo en el proceso aislado (`adapters/files/isolated.py`); las imágenes se recodifican sin metadatos. Su contenido va al modelo como datos en el mensaje del usuario, nunca en el system prompt.
- Contenedores `read_only`, sin capacidades y con `mem_limit` (`docker-compose.yml`): si algo necesita escribir fuera de `/app/data` y `/tmp`, se añade un tmpfs concreto, nunca se quita `read_only`.
