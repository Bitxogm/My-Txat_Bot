# Seguridad

## Exposición
- La app solo es accesible desde la red de casa y desde Tailscale.
- Nada se expone a internet: sin port forwarding, sin túneles públicos, sin cambios en el router.
- Los puertos de Compose se publican en `BIND_ADDR` (por defecto `127.0.0.1`), nunca en `0.0.0.0` por defecto.
- Ollama (11434) no tiene autenticación: solo debe ser alcanzable por Tailscale o localhost.

## Autenticación
- Login de un solo usuario (`AUTH_USERNAME`). La contraseña se guarda como hash argon2id en `backend/.env` (`AUTH_PASSWORD_HASH`, **entre comillas simples**: sin ellas Compose expande los `$` y el hash se rompe). Se genera con `uv run python -m app.cli hash-password`.
- Sesión: cookie `txat_session` firmada con `SESSION_SECRET` (itsdangerous, HMAC-SHA256), `httpOnly`, `SameSite=Strict`, `Path=/api`, caducidad `SESSION_TTL_HOURS` (72 h por defecto). `Secure` solo con `COOKIE_SECURE=true` (HTTPS). Nada de tokens en `localStorage`.
- Revocación: el logout invalida todas las sesiones emitidas hasta ese momento (un solo usuario, logout global). Reiniciar el backend también las cierra, igual que cambiar la contraseña o `SESSION_SECRET`.
- Fail closed: sin usuario, un hash argon2id válido y un secreto de ≥ 32 caracteres, el login y la API protegida responden 503 (y se avisa en el log al arrancar).
- `/api/health` es público (healthcheck de Docker); `/api/models`, `/api/chat` y `/api/auth/logout` exigen sesión.
- Rate limit global en el login: `LOGIN_MAX_FAILURES` intentos en `LOGIN_WINDOW_SECONDS` → 429 con `Retry-After`. Cada intento se reserva antes de verificar, así que las peticiones en paralelo no se lo saltan, y la verificación argon2 se hace de una en una (acota memoria y CPU).
- Frontend: el estado de sesión sale siempre de `/api/auth/me`; cualquier 401 devuelve al login. Si el logout falla por red o 5xx, la app sigue autenticada y avisa (la cookie es httpOnly y no se puede borrar desde JS). Al cerrar sesión se corta el stream en curso.
- Acceso rápido de desarrollo: `uv run python -m app.cli dev-login` genera una contraseña aleatoria, guarda su hash en `backend/.env` (con la marca `DEV_LOGIN=1`) y la contraseña en `frontend/.env.local` (`DEV_LOGIN_USER`/`DEV_LOGIN_PASSWORD`, sin prefijo `VITE_`). Ficheros fuera de git, escritos de forma atómica con permisos 600.
  - Ojo: `backend/.env` es el mismo fichero que usa `docker compose`. Por eso `dev-login` se niega con `APP_ENV=production` y no sustituye una contraseña que no creó él salvo con `--force`.
  - La tarjeta del login solo recibe las credenciales con `vite serve` en localhost (`define` en `vite.config.ts`). En `build`, en los tests y con `npm run dev -- --host` vale `null`: con `--host`, cualquiera en la red podría leer el módulo servido. `.dockerignore` deja fuera `.env.*`.
  - En una instancia accesible por otras personas, usa `hash-password`, no `dev-login`.
- Usuario y contraseña incorrectos devuelven el mismo error y tardan lo mismo (el hash se verifica siempre). La contraseña nunca se loguea.

### Riesgos aceptados
- **Bloqueo global**: es global y no por IP porque el puerto del backend es accesible directamente y `X-Forwarded-For` no es fiable. Cualquiera en la LAN o el tailnet puede mantener el login bloqueado mientras siga fallando.
- **HTTP en la LAN**: por Tailscale el tráfico va cifrado (WireGuard), pero por la LAN física con `BIND_ADDR` en la IP local la contraseña y la cookie viajan en claro. Recomendado: acceder solo por Tailscale y servir HTTPS con `tailscale serve`; entonces poner `COOKIE_SECURE=true` y añadir HSTS en nginx.
- **Cookies por host, no por puerto**: otra app del mismo host bajo `/api` recibiría la cookie. Usar un nombre de host propio (MagicDNS) lo evita.
- **Docs de la API**: con `APP_ENV=development` `/api/docs` y `/api/openapi.json` son públicos. En el despliegue real, `APP_ENV=production`.

## Repositorio público
- Nunca se suben secretos, `.env`, bases de datos, uploads, modelos ni datos personales.
- Solo se versionan los `.env.example` con valores vacíos o de ejemplo.
- Nada de IPs, nombres de host reales de Tailscale ni usuarios en el código o la documentación.

## Ficheros subidos
- Límite de tamaño (`UPLOAD_MAX_MB`) y lista blanca de tipos MIME.
- Se guardan con nombre generado, nunca con la ruta que manda el cliente.

## Asistente de Kali
- El modelo puede sugerir comandos, pero **nunca se ejecuta nada sin confirmación explícita** del usuario.
- Pensado solo para máquinas propias o con autorización (labs, CTF).
- Toda ejecución queda registrada.
