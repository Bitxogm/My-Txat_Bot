# Seguridad

## Exposición
- La app solo es accesible desde la red de casa y desde Tailscale.
- Nada se expone a internet: sin port forwarding, sin túneles públicos, sin cambios en el router.
- Los puertos de Compose se publican en `BIND_ADDR` (por defecto `127.0.0.1`), nunca en `0.0.0.0` por defecto.
- Ollama (11434) no tiene autenticación: solo debe ser alcanzable por Tailscale o localhost.

## Autenticación
- Login de un solo usuario. La contraseña se guarda como hash (argon2 o bcrypt) en `backend/.env`.
- Sesión en cookie `httpOnly`, `SameSite=Strict`, `Secure` cuando haya HTTPS. Nada de tokens en `localStorage`.
- Rate limit en el endpoint de login.

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
