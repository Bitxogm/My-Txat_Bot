# Decisiones (ADR)

Registro corto de decisiones de arquitectura. Formato: contexto, decisión, consecuencias. Las nuevas van al final.

## ADR-001: Todo en local con Ollama
- **Contexto**: privacidad, sin censura, sin coste por uso.
- **Decisión**: modelos servidos por Ollama en hardware propio.
- **Consecuencias**: el tamaño del modelo lo limita la VRAM (12 GB hoy).

## ADR-002: Agnóstico de modelo
- **Decisión**: el backend habla con una interfaz `LLMProvider`. La UI tiene selector de modelo.
- **Consecuencias**: cambiar de modelo no requiere tocar código. Otros proveedores locales se añadirían como adaptadores.

## ADR-003: Ollama como servicio separado
- **Contexto**: la GPU está en otra máquina (Acer) y puede cambiar.
- **Decisión**: Ollama vive en su propio perfil de Compose. El backend usa `OLLAMA_BASE_URL`, apuntando al nombre Tailscale del host en el puerto 11434.
- **Consecuencias**: la app corre en una máquina y el modelo en otra sin cambios de código.

## ADR-004: FastAPI para el backend
- **Decisión**: Python + FastAPI, Ruff para lint y formato.
- **Motivo**: el ecosistema de IA (RAG, whisper, embeddings) es Python. Async y streaming nativos.

## ADR-005: Vite + React para el frontend
- **Decisión**: Vite + React + TS + Tailwind + shadcn/ui + Sonner + vite-plugin-pwa.
- **Motivo**: es una SPA privada sin SEO; no hace falta SSR. Build estático servido por nginx.

## ADR-006: SQLite como base de datos
- **Decisión**: SQLite en `data/`. ChromaDB solo cuando llegue RAG.
- **Motivo**: un solo usuario, cero mantenimiento, backup = copiar un fichero.

## ADR-007: Acceso solo por LAN y Tailscale
- **Decisión**: ningún puerto abierto en el router. Los puertos se publican en la IP indicada en `BIND_ADDR`.
- **Consecuencias**: acceso remoto solo con Tailscale. Ver [security.md](security.md).

## ADR-008: Formato de error único
- **Decisión**: todas las respuestas de error usan `{ "error": { code, message, request_id } }`. El frontend tiene un único cliente API que las interpreta.
