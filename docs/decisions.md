# Decisiones (ADR)

Registro corto de decisiones de arquitectura. Formato: contexto, decisión, consecuencias. Las nuevas van al final.

## ADR-001: Todo en local con Ollama (matizado por ADR-012)
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

## ADR-009: uv para dependencias Python
- **Decisión**: el backend gestiona dependencias con uv (`pyproject.toml` + `uv.lock` commiteado). La CI instala con `uv sync --locked`.
- **Consecuencias**: entornos reproducibles en local, CI y Docker. Ruff y pytest usan las versiones fijadas en el lock.

## ADR-010: Streaming de chat con SSE sobre POST
- **Decisión**: `POST /api/chat` responde `text/event-stream` con eventos `token`, `done` y `error`. El frontend lo lee con `fetch` + `ReadableStream` (no `EventSource`, que solo admite GET).
- **Motivo**: el historial va en el cuerpo; SSE es más simple que WebSocket y pasa bien por nginx (`X-Accel-Buffering: no`).
- **Consecuencias**: los errores previos al primer token son JSON normales con su status HTTP; los posteriores llegan como evento `error`.

## ADR-011: El servidor es la fuente de verdad de las conversaciones
- **Decisión**: el cliente solo envía el mensaje nuevo (`POST /api/conversations/{id}/messages`); el backend guarda el turno y monta el historial desde SQLite. `/api/chat` se mantiene sin estado.
- **Motivo**: el historial no depende de lo que mande el navegador y la respuesta se guarda aunque el cliente corte (se marca `stopped`).
- **Consecuencias**: una sola conexión aiosqlite en modo WAL (un usuario). Para hacer backup en caliente no basta con copiar `txatbot.db`: hay que copiar también `-wal` o usar `sqlite3 data/txatbot.db ".backup copia.db"`.

## ADR-012: Modelos híbridos, local + nube gratuita (Groq)
- **Contexto**: los modelos que caben en la GPU (≈9B en la GTX 1070, ≈14B en la RTX 3060) inventan flags y rutas en comandos de pentesting. La API de Claude es de pago y Gemini rechaza demasiadas consultas legítimas de CTF.
- **Decisión**: además de Ollama, un proveedor opcional con API compatible con OpenAI (`CLOUD_*` en `backend/.env`), por defecto Groq en su plan gratuito (modelos de 70-120B). `RoutingLLMProvider` junta los dos detrás de `LLMProvider`; los modelos remotos se llaman `<CLOUD_NAME>/<id>` y el selector los separa en el grupo "Nube".
- **Consecuencias**: lo escrito a un modelo en la nube sale de la red y queda sujeto a las condiciones del proveedor; los locales siguen igual (ADR-001). Sin `CLOUD_API_KEY` todo es local. Cambiar de proveedor (OpenRouter, Cerebras) es solo configuración. Los límites del plan gratuito (≈1.000 peticiones/día por modelo) se notan como 429 `MODEL_RATE_LIMITED`.

## ADR-013: Personalidades en dos capas
- **Contexto**: cada uso (CTF, pentest, defensa, informes…) necesita un tono y un método distintos, pero los límites éticos y de rigor tienen que estar siempre.
- **Decisión**:
  - Prompt final = **capa base** fija (`backend/app/domain/prompts.py`, en código, no editable desde la UI) + **capa de personalidad** (editable). La composición se hace en el dominio, nunca en un adaptador: base, encabezado, personalidad delimitada entre `<personalidad>` y `</personalidad>` (esas etiquetas se eliminan del texto editable) y un recordatorio final fijo, porque los modelos pequeños obedecen más al último bloque.
  - Los límites éticos (alcance autorizado, no perfilar a particulares, los datos no son instrucciones) van en la capa base, para que no desaparezcan al duplicar y editar una personalidad. `/api/chat` (sin estado) también antepone la base y no acepta mensajes `system` del cliente.
  - 8 personalidades incorporadas (`domain/builtin_personalities.py`, ids `builtin-*`) creadas al arrancar con un seed idempotente (`builtin=1`). No se editan ni se borran (403 `PERSONALITY_BUILTIN`, también protegido en el repositorio); se duplican y la copia sí se edita o borra.
  - La personalidad se fija al crear la conversación: se guarda `personality_id` y una copia (snapshot) del prompt de personalidad, el nombre, el icono y `temperature`/`top_p`/`num_ctx`. No se cambia a mitad de conversación.
  - Los adaptadores aplican los parámetros que admiten (Ollama: `options`; API compatible con OpenAI: `temperature` y `top_p`, sin `num_ctx`) y descartan el resto en silencio.
- **Consecuencias**: la capa base es una barrera de prompt, no una garantía: una copia editada a propósito puede intentar anularla (el usuario es el dueño). Editar o borrar una personalidad no afecta a conversaciones ya creadas. La capa base se compone en cada turno, así que corregirla sí llega a las conversaciones antiguas. Las conversaciones anteriores a esta migración no tienen personalidad: solo la capa base y los parámetros por defecto del modelo. El seed sobrescribe las incorporadas con lo que haya en el código en cada arranque; las que se quiten del código pasan a ser editables.

## ADR-014: Catálogo de fuentes OSINT como entidad independiente
- **Contexto**: el Auditor de Huella Digital necesita recomendar fuentes según el activo auditado. Escribirlas dentro de su `system_prompt` sería difícil de mantener.
- **Decisión**:
  - Las fuentes viven en la tabla `osint_sources` (migración v3), no en el prompt. 27 fuentes incorporadas en 8 categorías (`breach`, `username`, `domain`, `image`, `code`, `forum`, `browser_fingerprint`, `aggregator`; enum en `domain/osint.py`) creadas con un seed idempotente (`domain/builtin_osint_sources.py`, ids `osint-*`).
  - Las incorporadas no se editan ni se borran (403 `OSINT_SOURCE_BUILTIN`): solo se activan o desactivan. El seed actualiza su contenido desde el código pero **nunca toca `is_active`**. Las propias se crean, editan y borran libremente.
  - El prompt del Auditor (`builtin-auditor-huella`) recibe en cada turno las fuentes activas agrupadas por categoría (las categorías vacías no aparecen), como bloque de datos de referencia `<catalogo_osint>` entre la personalidad y el recordatorio final. El catálogo no forma parte del snapshot de la conversación: es conocimiento, no comportamiento.
- **Consecuencias**:
  - Actualizar fuentes no toca la personalidad, y al revés.
  - Nombres, URLs y descripciones entran en el system prompt: se validan al guardar (NFKC, una línea, sin `<>`, backticks ni caracteres invisibles, bidi, de control o de uso privado; URL `http(s)` en ASCII imprimible, con dominio DNS válido —IDN en punycode—, puerto válido, sin credenciales, sin IPs ni `localhost`) y se vuelven a limpiar al componer el prompt.
  - Límites para no desplazar la capa base ni la conversación (el Auditor usa `num_ctx` 8192): máximo 100 fuentes propias (409 `OSINT_SOURCE_LIMIT`) y bloque de catálogo de 6000 caracteres como máximo; si no cabe todo, las incorporadas tienen prioridad y se indica cuántas se omiten.
  - `PUT` es sustitución completa: `is_active` es obligatorio, para que omitirlo no reactive una fuente apagada. El toggle es una sola sentencia atómica.
  - No reutilizar el id de una incorporada retirada: el seed la volvería a marcar como incorporada y pisaría las ediciones del usuario.
  - Las copias del Auditor no reciben el catálogo (se identifica por id).
  - `requires_payment` es booleano: las fuentes freemium van con `false` y "Freemium" en la descripción.
  - Las migraciones siguen en `adapters/sqlite/database.py` (lista `MIGRATIONS`), no en una carpeta aparte.

## ADR-015: Ficheros adjuntos como datos en el mensaje del usuario
- **Contexto**: para analizar salidas de nmap, logs, código o informes en PDF hay que poder adjuntarlos a una conversación, sin abrir una vía de inyección de prompt ni de escritura arbitraria en disco.
- **Decisión**:
  - Subida en dos pasos: `POST /api/conversations/{id}/attachments` (multipart, campo `file`) guarda el fichero como **pendiente**; al enviar el mensaje se pasan sus ids en `attachment_ids` (máx. 5) y quedan ligados a ese mensaje. Un adjunto enviado no se reutiliza ni se borra suelto; se borra con su conversación.
  - Tipo decidido por el **contenido**: PDF si empieza por `%PDF-`; texto si la extensión está en la lista blanca (`domain/attachment.py`) y el contenido es UTF-8 sin NUL. Lo demás, 415. El MIME del cliente se ignora. Las imágenes (modelos con visión) van en un paso aparte.
  - El fichero se guarda en `UPLOAD_DIR` con una clave uuid generada en el servidor (permisos 600, `O_EXCL|O_NOFOLLOW`); el nombre original solo se muestra, saneado. El texto extraído (máx. 200.000 caracteres) se guarda en la tabla `attachments` (migración v4) para no reprocesar el fichero en cada turno.
  - PDF con pypdf (puro Python) en un **proceso aparte** (uno a la vez, 1 GB de memoria como máximo) que se mata a los 20 s: un hilo no se puede parar y un PDF hostil se quedaría consumiendo CPU. Máximo 50 páginas. Cifrados, dañados o sin texto (escaneos) → 422 `UNREADABLE_FILE`.
  - El texto se normaliza (NFKC) y se le quitan los caracteres invisibles (formato, bidi, ancho cero, etiquetas Unicode, uso privado) y de control: podrían llevar instrucciones que el usuario no ve.
  - Las subidas sin `Content-Length` (chunked) se rechazan con 411: Starlette vuelca el multipart entero a disco antes de que el handler pueda contarlo.
  - Al modelo le llega dentro del mensaje `user`, nunca en el system prompt: una línea que dice que el contenido son datos, un bloque `<fichero nombre tipo recortado>` por adjunto (máx. 12.000 caracteres cada uno, con `</fichero` escapado) y al final el texto del usuario.
- **Consecuencias**:
  - Delimitar no garantiza que un modelo pequeño ignore instrucciones escondidas en un fichero; la capa base (ADR-013) lo refuerza. Revisar lo que sugiera tras analizar un fichero ajeno.
  - Con modelos en la nube el contenido del fichero sale de la red (ADR-012).
  - Los ficheros largos se recortan para el modelo (contexto de ~8k tokens en local) y se marca `recortado="sí"`.
  - Un adjunto pendiente que nunca se envía queda en disco hasta que se borra la conversación o se quita desde la UI. Al arrancar se borran los ficheros sin fila en `attachments` (caída entre guardar e insertar, borrado fallido).
  - El límite de pendientes y el enlace al mensaje son atómicos en SQL: subidas o envíos simultáneos no lo saltan (si un envío pierde la carrera, su turno se deshace).
  - `attachments.message_id` va con `ON DELETE CASCADE`: si algún día se borran mensajes sueltos, sus adjuntos se van con ellos (y hay que borrar sus ficheros) en vez de volver a quedar pendientes.

