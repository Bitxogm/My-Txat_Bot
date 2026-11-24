# Seguridad

## Exposición
- Despliegue previsto: una sola máquina con todo dentro. La app se usa desde la red de casa.
- Nada se expone a internet: sin port forwarding, sin túneles públicos, sin cambios en el router, en ningún caso.
- Solo el frontend se publica en `BIND_ADDR` (la IP de LAN para usarla desde casa; `127.0.0.1` por defecto). Nunca `0.0.0.0` sin decidirlo. El backend y Ollama (perfil `ollama`) se publican siempre en `127.0.0.1`: el navegador llega a la API por el nginx del frontend.
- Ollama (11434) y LM Studio (1234) no tienen autenticación: escuchan solo en `127.0.0.1` ("Serve on Local Network" de LM Studio desactivado).
  - El backend en Docker los alcanza por `host.docker.internal` (`extra_hosts` en el compose): Docker Desktop reenvía ese nombre al loopback del host. Consecuencia: cualquier contenedor de esta máquina puede llegar a los servicios del host en `127.0.0.1`; no ejecutar contenedores de terceros no confiables junto a ellos.
  - Con Docker Engine nativo (sin Docker Desktop) ese reenvío no existe: ligar LM Studio a la IP de `docker0` (`lms server start --bind 172.17.0.1`), **nunca a `0.0.0.0`**.
- Tailscale es opcional, a decidir al desplegar: solo para acceso desde fuera de casa o HTTPS fácil para instalar la PWA en el móvil. Si se usa, solo `tailscale serve`, nunca `tailscale funnel`.

## Autenticación
- Login de un solo usuario (`AUTH_USERNAME`). La contraseña se guarda como hash argon2id en `backend/.env` (`AUTH_PASSWORD_HASH`, **entre comillas simples**: sin ellas Compose expande los `$` y el hash se rompe). Se genera con `uv run python -m app.cli hash-password`.
- Sesión: cookie `txat_session` firmada con `SESSION_SECRET` (itsdangerous, HMAC-SHA256), `httpOnly`, `SameSite=Strict`, `Path=/api`, caducidad `SESSION_TTL_HOURS` (72 h por defecto). `Secure` solo con `COOKIE_SECURE=true` (HTTPS). Nada de tokens en `localStorage`.
- `localStorage` solo guarda preferencias de interfaz (`txat-theme`, `txat-sidebar`): nunca tokens, sesión ni datos de las conversaciones.
- Revocación: el logout invalida todas las sesiones emitidas hasta ese momento (un solo usuario, logout global). Reiniciar el backend también las cierra, igual que cambiar la contraseña o `SESSION_SECRET`.
- Fail closed: sin usuario, un hash argon2id válido y un secreto de ≥ 32 caracteres, el login y la API protegida responden 503 (y se avisa en el log al arrancar).
- `/api/health` y `/api/auth/login` son públicos (healthcheck de Docker y login); el resto de la API exige sesión.
- Rate limit global en el login: `LOGIN_MAX_FAILURES` intentos en `LOGIN_WINDOW_SECONDS` → 429 con `Retry-After`. Cada intento se reserva antes de verificar, así que las peticiones en paralelo no se lo saltan, y la verificación argon2 se hace de una en una (acota memoria y CPU).
- Frontend: el estado de sesión sale siempre de `/api/auth/me`; cualquier 401 devuelve al login. Si el logout falla por red o 5xx, la app sigue autenticada y avisa (la cookie es httpOnly y no se puede borrar desde JS). Al cerrar sesión se corta el stream en curso.
- Acceso rápido de desarrollo: `uv run python -m app.cli dev-login` genera una contraseña aleatoria, guarda su hash en `backend/.env` (con la marca `DEV_LOGIN=1`) y la contraseña en `frontend/.env.local` (`DEV_LOGIN_USER`/`DEV_LOGIN_PASSWORD`, sin prefijo `VITE_`). Ficheros fuera de git, escritos de forma atómica con permisos 600.
  - Ojo: `backend/.env` es el mismo fichero que usa `docker compose`. Por eso `dev-login` se niega con `APP_ENV=production` y no sustituye una contraseña que no creó él salvo con `--force`.
  - La tarjeta del login solo recibe las credenciales con `vite serve` en localhost (`define` en `vite.config.ts`). En `build`, en los tests y con `npm run dev -- --host` vale `null`: con `--host`, cualquiera en la red podría leer el módulo servido. `.dockerignore` deja fuera `.env.*`.
  - En una instancia accesible por otras personas, usa `hash-password`, no `dev-login`.
- Usuario y contraseña incorrectos devuelven el mismo error y tardan lo mismo (el hash se verifica siempre). La contraseña nunca se loguea.

### Riesgos aceptados
- **Bloqueo global**: es global y no por IP porque `X-Forwarded-For` no es fiable. Cualquiera en la LAN (o el tailnet, si se usa) puede mantener el login bloqueado mientras siga fallando.
- **HTTP en la LAN**: por la LAN de casa la contraseña y la cookie viajan en claro (cualquiera en la misma red podría verlas). Si eso preocupa, servir HTTPS (p. ej. `tailscale serve`, que además cifra con WireGuard), poner `COOKIE_SECURE=true` y añadir HSTS en nginx.
- **Cookies por host, no por puerto**: otra app del mismo host bajo `/api` recibiría la cookie. Usar un nombre de host propio (MagicDNS) lo evita.
- **Docs de la API**: con `APP_ENV=development` `/api/docs` y `/api/openapi.json` son públicos. En Docker, `docker-compose.yml` fija `APP_ENV=production` y no se sirven.

## Prompts y personalidades (ADR-013)
- Los límites éticos y de alcance están en la capa base (`backend/app/domain/prompts.py`), fija en código. Las personalidades solo añaden tono y método, delimitadas y seguidas de un recordatorio de la base.
- Es una barrera de prompt, no una garantía técnica: un modelo puede desobedecer, y una personalidad editada a propósito puede intentar anularla. Revisar siempre lo que sugiere el modelo.
- `/api/chat` no acepta mensajes `system` del cliente. Las personalidades incorporadas no se pueden editar ni borrar (403, también en el repositorio), y el snapshot de una conversación no se puede cambiar por ninguna ruta.
- Ficheros adjuntos (ADR-015): su contenido va en el mensaje `user` delimitado como datos, nunca dentro del `system`.
- Catálogo OSINT (ADR-014): sus textos entran en el system prompt del Auditor, así que se validan al guardar (una línea, sin `<>`, backticks ni caracteres de control; URL `http(s)` sin credenciales) y se limpian otra vez al componer el prompt, dentro de un bloque marcado como datos de referencia.

## Modelos en la nube y otros proveedores
- Opcionales (`PROVIDERS` + `PROVIDER_<NOMBRE>_*` en `backend/.env`, ADR-019; `CLOUD_*` obsoleto). Lo que se escribe en una conversación con un modelo del grupo "Nube" sale de la red hacia el proveedor (p. ej. Groq); los modelos locales no.
- `PROVIDER_<NOMBRE>_LOCAL=true` solo para servidores en esta misma máquina o la red propia (LM Studio, llama.cpp): quita los avisos de "sale de tu red". El backend no arranca si la URL de un proveedor `_LOCAL` es un host público, ni si una clave iría por `http` a internet.
- Cada proveedor tiene su propia clave (`PROVIDER_<NOMBRE>_API_KEY`, `SecretStr`), solo en la cabecera `Authorization` de su cliente; sin clave no se envía la cabecera. Nunca se loguea ni sale en los mensajes de error (solo el nombre de la variable que hay que revisar).
- La clave va como `SecretStr`, solo en la cabecera `Authorization` del cliente HTTP del adaptador, y nunca se loguea (los errores del proveedor se registran sin cabeceras).
- No usar modelos en la nube para datos sensibles de un cliente o de un pentest real: para eso, modelos locales.

## Repositorio público
- Nunca se suben secretos, `.env`, bases de datos, uploads, modelos ni datos personales.
- Solo se versionan los `.env.example` con valores vacíos o de ejemplo.
- Nada de IPs, nombres de host reales de Tailscale ni usuarios en el código o la documentación.

## Ficheros subidos
- Límite de tamaño (`UPLOAD_MAX_MB`): `Content-Length` obligatorio (sin él, 411) y comprobado antes de leer; además se corta al leer por trozos. nginx admite 21 MB por el sobre multipart. Un fichero por petición, máximo 5 pendientes por conversación.
- Tipo por contenido, no por el MIME del cliente: PDF (`%PDF-`), imagen PNG/JPEG/GIF/WebP (magic number) o texto UTF-8 con extensión de la lista blanca. Ejecutables, comprimidos y otros binarios → 415.
- Se guardan en `UPLOAD_DIR` con nombre uuid generado en el servidor (permisos 600, sin seguir enlaces), nunca con la ruta que manda el cliente. El nombre original se sanea (sin rutas, caracteres invisibles, bidi, comillas ni `<>`) y solo se muestra.
- PDF (pypdf) e imágenes (Pillow) se procesan en un proceso aparte (uno a la vez, 1 GB de memoria máx.) que se mata a los 20 s. PDF: máximo 50 páginas; cifrados o dañados → 422. Imágenes: más de 40 MP o rotas → 422; se recodifican sin metadatos (EXIF/GPS) y nunca se guarda ni se reenvía el fichero original.
- Las imágenes solo se vuelven a servir (miniaturas) ya recodificadas, con tipo fijo, `nosniff` y CSP `sandbox`. El texto que se vea en una imagen puede llevar instrucciones: solo lo frenan el aviso de datos y la capa base.
- Al texto se le quitan los caracteres invisibles y de control (incluidas las etiquetas Unicode U+E0000, usadas para esconder órdenes) y se normaliza con NFKC.
- El contenido llega al modelo como datos delimitados en el mensaje del usuario; un fichero no puede cerrar su propio bloque. Sigue siendo una barrera de prompt: un fichero ajeno puede llevar instrucciones escondidas.
- Los ficheros se borran del disco al borrar su conversación; los huérfanos, al arrancar. Carpeta 700, ficheros 600.

## Valoraciones (ADR-024)
- Los cuatro endpoints (`/api/messages/{id}/feedback`, `/api/feedback`, `/api/feedback/export`) requieren sesión.
- La corrección es texto del usuario: ≤ 4000 caracteres, sin caracteres de control ni invisibles (bidi, ancho cero, separadores de línea Unicode, uso privado) salvo saltos de línea y tabuladores, porque acabará en el RAG o en un conjunto de entrenamiento, y el frontend la pinta siempre como texto plano (nunca Markdown ni HTML).
- El export solo saca la valoración y su copia del turno: ni el system prompt, ni el contenido de los adjuntos (solo sus nombres), ni ids internos. Se descarga con `no-store`. U+2028, U+2029 y U+0085 van escapados para que cada valoración sea una sola línea también para lectores que parten por ellos.
- Con un modelo de la nube, la pregunta y la respuesta ya salieron de la red al generarse; la valoración y la corrección no salen nunca (no llegan al modelo).

## PWA (ADR-017)
- El service worker solo precachea el shell estático (HTML, JS, CSS, fuentes, iconos). **Nunca maneja `/api`**: no hay ninguna ruta de `runtimeCaching` y `/api/` está fuera del `navigateFallback`. Conversaciones, adjuntos, miniaturas y sesión siempre vienen de la red.
- La API responde `Cache-Control: no-store` por defecto (middleware), también las miniaturas y el SSE: nada de la sesión queda en la caché HTTP del navegador. El logout añade `Clear-Site-Data: "cache"`, que solo actúa con HTTPS. Al cerrar sesión o caducar, el frontend borra cualquier caché que no sea el precache del shell.
- Sin servidor no se muestran datos viejos: la app enseña "Sin conexión con el servidor". Ese estado no da acceso a nada; el chat solo aparece tras un `/api/auth/me` correcto.
- Actualizaciones: `sw.js` y el manifest se sirven con `no-cache`; la app busca versión nueva cada hora y pide permiso antes de recargar.
- Desinstalar un service worker defectuoso: publicar un build con `selfDestroying: true` en las opciones de `VitePWA` (`frontend/src/pwa/options.ts`) y volver a desplegar.
- **Requiere HTTPS**: por `http://IP` el navegador no registra el service worker y no se puede instalar. La app sigue funcionando como web normal. Despliegue con HTTPS (opcional, con Tailscale):
  1. `tailscale serve` hacia el puerto del frontend. **Nunca `tailscale funnel`**, que lo publica en internet.
  2. `COOKIE_SECURE=true` en `backend/.env`.
  3. HSTS en `frontend/nginx-security-headers.conf`, solo en ese despliegue, empezando con un `max-age` corto y sin `includeSubDomains`.
- El certificado de Tailscale aparece en los registros públicos de Certificate Transparency: el nombre de la máquina y del tailnet se vuelven públicos (no la app). Usar un nombre de máquina neutro y no escribirlo en el repo.

## Contenedores
El proceso que parsea PDF e imágenes comparte usuario y sistema de ficheros con el backend, así que el contenedor es la siguiente barrera (`docker-compose.yml`):
- `backend` y `frontend` corren sin root, con `cap_drop: [ALL]` y `no-new-privileges` (un binario setuid no da privilegios).
- Sistema de ficheros raíz de solo lectura (`read_only`): un fichero malicioso no puede tocar el código ni la configuración. Solo se escribe en `/app/data` (volumen: SQLite y uploads) y en `/tmp`, un tmpfs de 128 MB con `noexec,nosuid,nodev` (Starlette vuelca ahí las subidas de más de 1 MB; nginx, su pid y sus búferes).
- `mem_limit` (2 GB backend, 256 MB frontend) y `pids_limit`: segunda barrera sobre el `RLIMIT_AS` de 1 GB del proceso aislado. El tmpfs cuenta dentro del límite de memoria.
- Si una dependencia nueva necesita escribir fuera de esas rutas, falla con `Read-only file system`: añadir un tmpfs concreto, no quitar `read_only`.

## Asistente de Kali
- El modelo puede sugerir comandos, pero **nunca se ejecuta nada sin confirmación explícita** del usuario.
- Pensado solo para máquinas propias o con autorización (labs, CTF).
- Toda ejecución queda registrada.
