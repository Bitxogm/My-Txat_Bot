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

**Mejora de las respuestas** (ADR-023): los pesos del modelo no cambian con el uso; lo que mejora es el sistema alrededor. Orden: RAG → correcciones → verificación de comandos → fine-tuning. Las tareas marcadas *(mejora)* en esta fase y las siguientes forman esta línea.

- [x] Aviso de límite de uso (429) de un proveedor, con el tiempo de espera y la opción de seguir con el modelo local (probado a mano con Groq)
- [ ] Memoria persistente ([spec](specs/persistent-memory.md)): datos sobre el usuario, su entorno, nivel, preferencias y reto en curso que se inyectan en cada conversación. Primera versión manual (página "Memoria" y botón "Recordar"); después, el modelo propone recuerdos y el usuario los aprueba, edita o borra (nada se guarda sin visto bueno)
- [x] *(mejora)* Valoraciones 👍/👎 por respuesta; en 👎, motivos y la corrección escrita, con la página "Correcciones" y el export JSONL ([formato](feedback-export.md), ADR-024). Se guardan desde ya; se aprovechan en la Fase 4
- [ ] Exportación del dataset (respuestas buenas y corregidas) para el fine-tuning: el formato de entrenamiento (pares instrucción/respuesta) se derivará del JSONL de las valoraciones

### Pendientes de UX
Spec: [ux-sidebar-contrast](specs/ux-sidebar-contrast.md).
- [x] Barra lateral colapsable (botón y Ctrl+B en escritorio, se recuerda; panel superpuesto en móvil)
- [x] Revisión de contraste de colores WCAG AA, en modo claro y oscuro (comprobada en CI por `theme-contrast.test.ts`)

## Fase 4: Conocimiento
- [ ] *(mejora)* RAG con ChromaDB y el modelo de embeddings local: HackTricks, OWASP MASTG/WSTG, man pages, writeups y notas propias. Las respuestas citan el fragmento usado
- [ ] *(mejora)* Las correcciones de la Fase 3 entran en el RAG como notas del usuario y se convierten en preguntas candidatas para la batería de evaluación
- [ ] Indexar conversaciones marcadas como útiles
- [ ] Búsqueda web con SearXNG (servicio propio en Compose)

## Fase 5: Asistente Kali
- [ ] Sugerencia de comandos con explicación
- [ ] *(mejora)* Verificación de comandos: antes de sugerir uno, comprobar en el entorno aislado con `--help`/`man` que la herramienta y sus flags existen; si no, avisar en vez de inventar
- [ ] Ejecución solo tras confirmación explícita, en entorno aislado, con registro

## Fase 6: Modelo propio (fine-tuning)
Cuando haya unos cientos de ejemplos valorados.
- [ ] *(mejora)* QLoRA con Unsloth en el Acer (RTX 3060) de un modelo base de 7-9B, con las preguntas y correcciones acumuladas (Fases 3 y 4). Solo cuando haya datos suficientes
- [ ] Importación a Ollama como modelo propio versionado (`txat-void:vN`), comparable con el original y reversible
- [ ] Si Ollama añade Qwen3.8-Flash-Next u otro MoE mayor a su biblioteca, probarlo con `ollama pull` y la batería frente a `qwen3.6:35b-a3b`, sin cambiar de motor ([Plan B](research/moe-offload.md#plan-b))

## Fase 7: Extras
- [ ] Voz: faster-whisper (STT) + Piper (TTS)
- [ ] Backups automáticos de `data/`

## Despliegue en el Acer
- [ ] Ampliar el Acer a 32 GB de RAM es requisito para el despliegue: con 16 GB, `qwen3.6:35b-a3b` (22 GB, expertos en RAM) no cabe con holgura junto al sistema y Docker (`docs/research/moe-offload.md`)
