# Txat_bot

Chatbot personal que corre 100 % en local. Usa modelos abiertos servidos por Ollama, tiene una personalidad configurable y está pensado como copiloto para laboratorios y CTF autorizados (Kali, HackMyVM, DockerLabs).

> Estado: **Fase 0** (estructura y documentación). Todavía no hay código de aplicación. Ver [docs/roadmap.md](docs/roadmap.md).

## Qué hace (objetivo)

- Chat en el navegador, instalable como PWA, con streaming de respuestas.
- Selector de modelo: funciona con cualquier modelo que tenga Ollama.
- Subida de imágenes y ficheros para analizarlos en la conversación.
- Personalidades editables.
- Más adelante: RAG sobre documentación (HackTricks, man pages, notas propias), búsqueda web con SearXNG, voz (faster-whisper + Piper), memoria a largo plazo y un asistente de Kali que **nunca ejecuta comandos sin confirmación**.

## Stack

| Capa | Tecnología |
| --- | --- |
| Modelos | Ollama (GPU NVIDIA) |
| Backend | Python 3.12, FastAPI, Ruff, pytest |
| Frontend | Vite, React, TypeScript, Tailwind, shadcn/ui, Sonner, vite-plugin-pwa, ESLint, Prettier |
| Datos | SQLite (ChromaDB opcional para RAG) |
| Infra | Docker Compose, NVIDIA Container Toolkit, Tailscale |

## Estructura

```
backend/     API FastAPI (app/, tests/, pyproject.toml)
frontend/    App React + Vite
docs/        Arquitectura, roadmap, decisiones y seguridad
data/        SQLite, uploads y backups locales (fuera de git)
docker-compose.yml
```

## Puesta en marcha (a partir de Fase 1)

```bash
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up -d
```

Ollama corre en la máquina con GPU y el backend lo alcanza por Tailscale (`OLLAMA_BASE_URL`). Para levantar Ollama en la misma máquina:

```bash
docker compose --profile ollama up -d
```

## Seguridad

Solo para uso personal. Accesible únicamente desde la red de casa y Tailscale; nada se expone a internet. Detalles en [docs/security.md](docs/security.md).

La ayuda en hacking está pensada para entornos propios o con autorización explícita (labs, CTF).

## Documentación

- [Arquitectura](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Decisiones](docs/decisions.md)
- [Seguridad](docs/security.md)
