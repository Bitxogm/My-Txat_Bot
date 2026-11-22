# Txat_bot

Chatbot personal para tu red. Usa modelos abiertos servidos por Ollama en local y, si quieres, otros proveedores compatibles con OpenAI: Groq en la nube o LM Studio en tu máquina (opcionales). Tiene personalidades configurables y está pensado como copiloto para laboratorios y CTF autorizados (Kali, HackMyVM, DockerLabs).

> Estado: **Fase 3** (personalización). Ver [docs/roadmap.md](docs/roadmap.md).

## Qué hace

- Chat en el navegador con streaming de respuestas y conversaciones guardadas en SQLite.
- Login de un solo usuario (cookie httpOnly).
- Selector de modelo:
  - Locales: los de Ollama.
  - Otros proveedores compatibles con OpenAI (opcional, varios a la vez): Groq en su plan gratuito, OpenRouter, LM Studio o llama.cpp en local… Lo que se envía a un modelo de la nube sale de tu red.
- 8 personalidades incorporadas (Mentor CTF, Pentester, Auditor de Huella Digital…) más las tuyas, editables. Los límites éticos van en una capa base fija.
- Catálogo de fuentes OSINT para el Auditor de Huella Digital.
- Adjuntos: ficheros de texto (logs, salidas de nmap, código…), PDF e imágenes. Las imágenes solo se envían a modelos con visión.
- Respuestas en Markdown seguro, con resaltado de código y botón de copiar.
- Modo día/noche.
- PWA instalable (con HTTPS, p. ej. `tailscale serve`), con pantalla de "sin conexión" en lugar de datos viejos.

Próximas fases:
- Memoria y valoraciones para personalizar el modelo.
- RAG con tus notas y writeups.
- Búsqueda web con SearXNG.
- Asistente de Kali que **nunca ejecuta comandos sin confirmación**.
- Fine-tuning de un modelo propio.

## Stack

| Capa | Tecnología |
| --- | --- |
| Modelos | Ollama (GPU NVIDIA); opcional Groq u otro proveedor compatible con OpenAI |
| Backend | Python 3.12, FastAPI, SQLite (aiosqlite), pypdf, Pillow, uv, Ruff, pytest |
| Frontend | Vite, React, TypeScript, Tailwind, shadcn/ui, Sonner, vite-plugin-pwa, ESLint, Prettier, Vitest |
| Infra | Docker Compose (contenedores sin root y de solo lectura), NVIDIA Container Toolkit, Tailscale |

## Estructura

```
backend/     API FastAPI (app/, tests/, pyproject.toml, uv.lock)
frontend/    SPA React + Vite, servida por nginx en Docker
docs/        Arquitectura, roadmap, decisiones (ADR) y seguridad
evals/       Batería de preguntas para medir las respuestas de los modelos
data/        SQLite, uploads y backups locales (fuera de git)
docker-compose.yml
```

## Puesta en marcha

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Rellena `backend/.env`:
- `AUTH_USERNAME`.
- `AUTH_PASSWORD_HASH`, entre comillas simples. Se genera con `uv run python -m app.cli hash-password` desde `backend/`.
- `SESSION_SECRET`, que se genera con `uv run python -m app.cli session-secret`.
- `OLLAMA_BASE_URL`.
- `PROVIDERS` y `PROVIDER_<NOMBRE>_*`, solo si quieres Groq, LM Studio u otros proveedores (ver `backend/.env.example`).

Después:

```bash
docker compose up -d
```

Ollama corre en la máquina con GPU y el backend lo alcanza por Tailscale (`OLLAMA_BASE_URL`). Para levantarlo en la misma máquina:

```bash
docker compose --profile ollama up -d
```

Desarrollo sin Docker:
- Backend: `uv sync --extra dev` y luego `uv run uvicorn app.main:app --reload`.
- Frontend: `npm install` y luego `npm run dev` (puerto 5173).
- Más comandos en [CLAUDE.md](CLAUDE.md).

## Seguridad

Solo para uso personal. Accesible únicamente desde la red de casa y Tailscale; nada se expone a internet. Detalles en [docs/security.md](docs/security.md).

Con un modelo `groq/...` el contenido de la conversación (mensajes, ficheros e imágenes) sale a un tercero: nada de datos reales ni de clientes; para eso, modelos locales.

La ayuda en hacking está pensada para entornos propios o con autorización explícita (labs, CTF).

## Documentación

- [Arquitectura](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Decisiones (ADR)](docs/decisions.md)
- [Seguridad](docs/security.md)
