# Roadmap

Cada fase se divide en tareas pequeñas. Una tarea = una rama = una PR.

## Fase 0: Fundaciones (cerrada)
- [x] Estructura de carpetas
- [x] Ficheros base: .gitignore, .editorconfig, .env.example, configs de lint/format
- [x] Esqueleto de Docker Compose (log rotation, perfil ollama con GPU)
- [x] README, CLAUDE.md y docs (arquitectura, roadmap, decisiones, seguridad)

## Fase 1: Chat mínimo (cerrada)
- [x] Backend FastAPI: config, logging, request id, handler global de errores, `/api/health`
- [x] Dockerfile del backend
- [x] Proveedor Ollama: listar modelos y chat con streaming (SSE)
- [x] Scaffold frontend (Vite + React + TS + Tailwind + shadcn/ui + Sonner)
- [x] Cliente API único con mapeo de errores
- [x] Pantalla de chat con selector de modelo
- [x] Dockerfile del frontend (build + nginx)
- [x] Login de un solo usuario (cookie httpOnly)
- [x] Persistencia de conversaciones en SQLite

## Fase 2: Personalidad y ficheros (cerrada)
- [x] Personalidades editables (system prompt + parámetros)
- [x] Catálogo de fuentes OSINT para el Auditor de Huella Digital (ADR-014)
- [x] Ficheros adjuntos de texto y PDF (ADR-015)
- [x] Imágenes para modelos con visión (ADR-016)
- [x] PWA instalable con shell offline (ADR-017)

## Fase 3: Personalización (memoria y valoraciones) (actual)
Objetivo: un modelo que "aprende" de Void con el uso. Orden acordado: memoria → conocimiento → entrenamiento.
- [ ] Memoria persistente: datos sobre el usuario, su entorno y preferencias que se inyectan en cada conversación. El modelo propone recuerdos y el usuario los aprueba, edita o borra (nada se guarda sin visto bueno)
- [ ] Valoraciones 👍/👎 y corrección de respuestas en el chat
- [ ] Exportación del dataset (respuestas buenas y corregidas) para el fine-tuning

### Pendientes de UX
- [ ] Barra lateral colapsable
- [ ] Revisión de contraste de colores WCAG AA, en modo claro y oscuro

## Fase 4: Conocimiento
- [ ] RAG con ChromaDB: HackTricks, man pages, writeups y notas propias
- [ ] Indexar conversaciones marcadas como útiles
- [ ] Búsqueda web con SearXNG (servicio propio en Compose)

## Fase 5: Asistente Kali
- [ ] Sugerencia de comandos con explicación
- [ ] Ejecución solo tras confirmación explícita, en entorno aislado, con registro

## Fase 6: Modelo propio (fine-tuning)
Cuando haya unos cientos de ejemplos valorados.
- [ ] QLoRA con Unsloth en el host de la RTX 3060 (modelo base 7-8B)
- [ ] Importación a Ollama como modelo propio versionado (`txat-void:vN`), comparable con el original y reversible

## Fase 7: Extras
- [ ] Voz: faster-whisper (STT) + Piper (TTS)
- [ ] Backups automáticos de `data/`
