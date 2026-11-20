# Roadmap

Cada fase se divide en tareas pequeñas. Una tarea = una rama = una PR.

## Fase 0: Fundaciones (cerrada)
- [x] Estructura de carpetas
- [x] Ficheros base: .gitignore, .editorconfig, .env.example, configs de lint/format
- [x] Esqueleto de Docker Compose (log rotation, perfil ollama con GPU)
- [x] README, CLAUDE.md y docs (arquitectura, roadmap, decisiones, seguridad)

## Fase 1: Chat mínimo (actual)
- [x] Backend FastAPI: config, logging, request id, handler global de errores, `/api/health`
- [x] Dockerfile del backend
- [x] Proveedor Ollama: listar modelos y chat con streaming (SSE)
- [x] Scaffold frontend (Vite + React + TS + Tailwind + shadcn/ui + Sonner)
- [x] Cliente API único con mapeo de errores
- [ ] Pantalla de chat con selector de modelo
- [ ] Dockerfile del frontend (build + nginx)
- [ ] Login de un solo usuario (cookie httpOnly)
- [ ] Persistencia de conversaciones en SQLite

## Fase 2: Personalidad y ficheros
- [ ] Personalidades editables (system prompt + parámetros)
- [ ] Subida de imágenes (modelos con visión) y ficheros de texto/PDF
- [ ] PWA (instalable, offline shell)

## Fase 3: Conocimiento
- [ ] RAG con ChromaDB: HackTricks, man pages, notas propias
- [ ] Búsqueda web con SearXNG (servicio propio en Compose)

## Fase 4: Asistente Kali
- [ ] Sugerencia de comandos con explicación
- [ ] Ejecución solo tras confirmación explícita, en entorno aislado, con registro

## Fase 5: Extras
- [ ] Voz: faster-whisper (STT) + Piper (TTS)
- [ ] Memoria a largo plazo
- [ ] Backups automáticos de `data/`
