# Despliegue en la torre Acer

Guía para montar Txat en la torre Acer (Kali, RTX 3060 12 GB, 16 GB de RAM) como **instancia de uso**:
la que se usa de verdad y donde se acumulan las valoraciones, la memoria y el dataset. La X570 (Ubuntu)
queda solo para desarrollo, con datos de prueba (`app.cli dev-login`).

Todo corre en el Acer en Docker: frontend, backend y Ollama (perfil `ollama` del Compose). Ollama va
en Docker y no instalado en el host porque, con Docker Engine nativo (no Docker Desktop),
`host.docker.internal` apunta a `docker0` y no al `127.0.0.1` del host. Con Ollama en el Compose, el
backend lo alcanza por la red interna (`http://ollama:11434`) y Ollama solo se publica en
`127.0.0.1`.

Los comandos con `sudo` los ejecuta Void en el Acer. Se dan desde la carpeta del repo
(`~/My-Txat_Bot`) salvo que se diga otra cosa.

## 1. Comprobaciones previas

1. Driver NVIDIA y GPU visibles. Debe salir la RTX 3060 con 12 GB y la versión del driver:
   ```bash
   nvidia-smi
   ```
   Si falla, ver [Problemas habituales](#problemas-habituales).
2. Docker instalado y el usuario en el grupo `docker`. Debe responder sin `sudo`:
   ```bash
   docker version
   ```
   Si no está: `sudo apt install -y docker.io` y `sudo usermod -aG docker $USER` (cerrar sesión y
   volver a entrar).
3. Compose v2 (subcomando `docker compose`, con espacio):
   ```bash
   docker compose version
   ```
   Si no existe, instalar el plugin: `sudo apt install -y docker-compose-plugin` (o `docker-compose`
   en Kali, según la versión de sus repos; lo que importa es que `docker compose version` responda).
4. NVIDIA Container Toolkit, para que Ollama use la GPU dentro de Docker. Prueba directa:
   ```bash
   docker run --rm --gpus all ubuntu nvidia-smi
   ```
   Si da `could not select device driver "nvidia"`, instalar el toolkit siguiendo la guía oficial de
   NVIDIA ("Installing the NVIDIA Container Toolkit", repositorio apt), configurarlo para Docker con
   `sudo nvidia-ctk runtime configure --runtime=docker`, reiniciar Docker y repetir la prueba.
5. Espacio en disco. Hacen falta unos 25 GB libres (imágenes ~3 GB, modelos ~15 GB, datos y copias):
   ```bash
   df -h ~
   ```

## 2. Clonar el repo

1. Clonar en el home del usuario:
   ```bash
   git clone https://github.com/Bitxogm/My-Txat_Bot.git ~/My-Txat_Bot && cd ~/My-Txat_Bot
   ```

## 3. Configuración

Secretos **nuevos** en el Acer: no se copian el hash de la contraseña ni el `SESSION_SECRET` de la X570.
La clave de Groq sí puede ser la misma.

1. Variables de Compose:
   ```bash
   cp .env.example .env
   ```
2. Variables del backend:
   ```bash
   cp backend/.env.example backend/.env
   ```
3. UID/GID del usuario del Acer, para que el contenedor pueda escribir en `data/`. Apuntar los dos
   números:
   ```bash
   id -u && id -g
   ```
   Y ponerlos en `.env` como `APP_UID=` y `APP_GID=` (en Kali el primer usuario suele ser 1000).
4. Crear `data/` con el usuario actual antes del primer arranque. Si no existe, Docker la crea como
   `root` y el backend no puede escribir en ella:
   ```bash
   mkdir -p data
   ```
5. Construir la imagen del backend (la usan los dos comandos siguientes):
   ```bash
   docker compose build backend
   ```
6. Hash de la contraseña (pide la contraseña dos veces, mínimo 12 caracteres). Copiar la salida a
   `AUTH_PASSWORD_HASH` en `backend/.env`, entre comillas simples:
   ```bash
   docker compose run --rm --no-deps backend python -m app.cli hash-password
   ```
7. Secreto de sesión. Copiar la salida a `SESSION_SECRET`:
   ```bash
   docker compose run --rm --no-deps backend python -m app.cli session-secret
   ```
8. Editar `backend/.env` y dejar al menos esto:
   ```bash
   nano backend/.env
   ```
   ```ini
   APP_ENV=production
   AUTH_USERNAME=void
   AUTH_PASSWORD_HASH='$argon2id$…'          # paso 6
   SESSION_SECRET=…                           # paso 7
   OLLAMA_BASE_URL=http://ollama:11434        # Ollama del Compose
   DEFAULT_MODEL=qwen3.5:9b
   OLLAMA_KEEP_ALIVE=30m                       # el modelo sigue cargado 30 min tras responder
   OLLAMA_NUM_CTX=8192                         # 16384 cabe en 12 GB con un 9B, a costa de VRAM
   COOKIE_SECURE=false                         # true solo con HTTPS
   # Groq (opcional; la clave puede ser la de la X570)
   PROVIDERS=groq
   PROVIDER_GROQ_BASE_URL=https://api.groq.com/openai/v1
   PROVIDER_GROQ_API_KEY=gsk_…
   PROVIDER_GROQ_CONTEXT_TOKENS=6000
   ```
   `APP_ENV=production` desactiva `/api/docs` y la tarjeta de acceso rápido de desarrollo (en Docker,
   el Compose lo fuerza de todas formas). `CORS_ORIGINS` no hace falta tocarlo: el navegador habla
   con el nginx del frontend, que pasa `/api` al backend en el mismo origen.

## 4. Publicar en la LAN

1. IP de LAN del Acer (la de la interfaz con `UP`, p. ej. `192.168.1.x`):
   ```bash
   ip -br addr
   ```
2. Ponerla en `.env` como `BIND_ADDR=<IP de LAN>`. Nunca `0.0.0.0` sin decidirlo: publicaría la app
   en todas las interfaces (incluidas VPN o Docker). El backend y Ollama siguen solo en `127.0.0.1`.
   Conviene fijar esa IP en el router (reserva DHCP), si no puede cambiar.
3. Levantar todo, Ollama incluido:
   ```bash
   docker compose --profile ollama up -d --build
   ```
4. Estado de los servicios: `backend` y `frontend` deben salir `healthy` al cabo de unos segundos:
   ```bash
   docker compose --profile ollama ps
   ```
5. Desde otro equipo de casa (portátil, móvil en la misma Wi-Fi), abrir `http://<IP de LAN>:5173`.
   Desde un terminal de otro equipo:
   ```bash
   curl -sI http://<IP de LAN>:5173 | head -1
   ```
   Debe responder `HTTP/1.1 200 OK`. El puerto no se abre en el router: la app es solo para la red de
   casa (Tailscale es opcional, si algún día se quiere acceso desde fuera o HTTPS para la PWA).

## 5. Modelos

Con 12 GB de VRAM caben enteros `qwen3.5:9b` (~6,6 GB) y `gemma4:12b` (~8 GB), uno cargado a la vez.
El Qwen3.6 MoE (`qwen3.6:35b-a3b`, 22 GB) deja los expertos en la RAM: con 16 GB no cabe con holgura
junto al sistema y Docker. Solo tras ampliar a 32 GB (`docs/roadmap.md`, "Despliegue en el Acer").

1. Descargar el modelo por defecto:
   ```bash
   docker compose --profile ollama exec ollama ollama pull qwen3.5:9b
   ```
2. Descargar el segundo:
   ```bash
   docker compose --profile ollama exec ollama ollama pull gemma4:12b
   ```
3. Comprobar que están y que el backend los ve (debe responder `"ollama":"up"`):
   ```bash
   curl -s http://127.0.0.1:8000/api/health
   ```
4. Con una pregunta ya enviada desde la app, comprobar que el modelo está en la GPU (columna
   `PROCESSOR`: `100% GPU`) y cuánto tiempo seguirá cargado (`UNTIL`, por `OLLAMA_KEEP_ALIVE`):
   ```bash
   docker compose --profile ollama exec ollama ollama ps
   ```

## 6. Traer los datos de la X570 (opcional, una sola vez)

Solo si se quieren conservar en el Acer las conversaciones, valoraciones y ficheros de la X570. Si no,
el Acer empieza limpio. Después de esto, la X570 vuelve a datos de prueba.

1. En la **X570**, parar el backend para que SQLite no esté escribiendo mientras se copia (Ctrl+C en el
   `uvicorn` de desarrollo, o esto si corre en Docker):
   ```bash
   docker compose stop backend
   ```
2. En el **Acer**, parar el backend también:
   ```bash
   docker compose --profile ollama stop backend
   ```
3. Desde la **X570**, copiar `data/` al Acer. Es la carpeta `data/` de la raíz del repo; si el
   `backend/.env` de la X570 apunta `DATABASE_URL` a otra ruta, usar esa (`acer` = nombre o IP del Acer en la LAN, usuario el del
   Acer):
   ```bash
   rsync -av --delete ~/Desktop/My-Txat_Bot/data/ <usuario>@<acer>:~/My-Txat_Bot/data/
   ```
   `--delete` deja `data/` del Acer igual que el de la X570: solo sirve si el Acer no tiene datos
   propios todavía.
4. En el **Acer**, que el dueño de `data/` sea el usuario de `APP_UID`/`APP_GID`:
   ```bash
   ls -ln data data/uploads | head
   ```
   Si no coincide: `sudo chown -R $(id -u):$(id -g) data`.
5. Arrancar y comprobar en el log que aplica las migraciones pendientes (si las hay) y arranca sin
   errores:
   ```bash
   docker compose --profile ollama up -d backend && docker compose logs --tail 30 backend
   ```
   Después, abrir la app: las conversaciones de la X570 están en la barra lateral y la página
   "Correcciones" muestra sus valoraciones.

## 7. Copias de seguridad de `data/`

`data/` es el dataset (conversaciones, valoraciones, memoria, ficheros): no está en git, ni debe
estarlo. La base se copia con `.backup` de SQLite, nunca copiando el fichero en caliente (con WAL, una
copia directa puede salir incompleta). Las copias van fuera del repo y, mejor, a otro disco.

1. Instalar el cliente de SQLite en el host:
   ```bash
   sudo apt install -y sqlite3
   ```
2. Crear el script de copia en `~/bin/txat-backup.sh`:
   ```bash
   mkdir -p ~/bin ~/txat-backups && nano ~/bin/txat-backup.sh
   ```
   ```bash
   #!/usr/bin/env bash
   # Copia diaria de Txat: base SQLite consistente (.backup) + uploads; guarda las 14 últimas.
   set -euo pipefail
   repo="$HOME/My-Txat_Bot"
   dest="$HOME/txat-backups/$(date +%F)"
   mkdir -p "$dest"
   sqlite3 "$repo/data/txatbot.db" ".backup '$dest/txatbot.db'"
   sqlite3 "$dest/txatbot.db" "PRAGMA integrity_check;" | grep -qx ok
   if [ -d "$repo/data/uploads" ]; then tar -C "$repo/data" -czf "$dest/uploads.tar.gz" uploads; fi
   ls -1d "$HOME"/txat-backups/????-??-?? | head -n -14 | xargs -r rm -r
   ```
3. Hacerlo ejecutable:
   ```bash
   chmod +x ~/bin/txat-backup.sh
   ```
4. Probarlo una vez a mano y ver que crea la carpeta del día con `txatbot.db` (y `uploads.tar.gz` si
   ya hay ficheros subidos):
   ```bash
   ~/bin/txat-backup.sh && ls -l ~/txat-backups/$(date +%F)
   ```
5. Programarlo cada día a las 04:00 (añadir la línea `0 4 * * * $HOME/bin/txat-backup.sh` al editor
   que se abre):
   ```bash
   crontab -e
   ```
6. Llevar `~/txat-backups` a otro disco o equipo de vez en cuando (un disco USB, la X570): una copia en
   el mismo disco no sirve si el disco falla.

**Restaurar una copia** (p. ej. la del 2026-12-01):

1. Parar el backend:
   ```bash
   docker compose --profile ollama stop backend
   ```
2. Sustituir la base y quitar los ficheros WAL de la anterior:
   ```bash
   cp ~/txat-backups/2026-12-01/txatbot.db data/txatbot.db && rm -f data/txatbot.db-wal data/txatbot.db-shm
   ```
3. Restaurar los ficheros subidos:
   ```bash
   rm -rf data/uploads && tar -C data -xzf ~/txat-backups/2026-12-01/uploads.tar.gz
   ```
4. Arrancar y comprobar en la app:
   ```bash
   docker compose --profile ollama up -d backend
   ```

## 8. Actualizar

1. Copia de seguridad antes de cualquier actualización (las migraciones solo avanzan):
   ```bash
   ~/bin/txat-backup.sh
   ```
2. Traer los cambios:
   ```bash
   git pull
   ```
3. Revisar si cambiaron los ejemplos de configuración (variables nuevas que haya que añadir a mano a
   `.env` o `backend/.env`):
   ```bash
   git diff HEAD@{1} -- .env.example backend/.env.example
   ```
4. Reconstruir y reiniciar:
   ```bash
   docker compose --profile ollama up -d --build
   ```
5. Las migraciones de SQLite se aplican solas al arrancar el backend (`PRAGMA user_version`). Ver que
   arrancó bien:
   ```bash
   docker compose logs --tail 30 backend
   ```
   Si el backend no arranca tras una migración, restaurar la copia del paso 1 (sección 7) y volver a
   la versión anterior con `git checkout <commit anterior>` antes de reconstruir.
6. De vez en cuando, actualizar la imagen de Ollama:
   ```bash
   docker compose --profile ollama pull ollama && docker compose --profile ollama up -d ollama
   ```

## 9. Lista de verificación final

Desde otro equipo de casa, en `http://<IP de LAN>:5173`:

- [ ] Login con el usuario y la contraseña nuevos (no aparece la tarjeta de acceso rápido).
- [ ] Chat con `qwen3.5:9b`: la primera respuesta tarda un poco (carga en GPU) y la segunda no.
- [ ] Chat con un modelo `groq/...`: responde y avisa de que el contenido sale de la red.
- [ ] Subir una imagen a un modelo con visión (o comprobar que con uno sin visión se bloquea el envío).
- [ ] 👍 y 👎 con corrección en una respuesta; aparecen en "Correcciones".
- [ ] "Exportar JSONL" en "Correcciones" descarga el fichero.
- [ ] `docker compose --profile ollama ps`: los tres servicios `Up`, backend y frontend `healthy`.
- [ ] La primera copia de seguridad existe en `~/txat-backups/`.

## Problemas habituales

- **`nvidia-smi` no existe o falla en Kali.** Falta el driver propietario:
  `sudo apt install -y nvidia-driver nvidia-cuda-toolkit` y reiniciar. Con Secure Boot activado el
  módulo no carga: desactivarlo en la BIOS o firmar el módulo (MOK). Si tras instalar sigue cargando
  `nouveau`, `lsmod | grep -E 'nvidia|nouveau'` lo muestra; el paquete lo bloquea, pero hace falta
  reiniciar.
- **Ollama corre en la CPU** (`ollama ps` dice `CPU`, respuestas muy lentas). El contenedor no ve la
  GPU: repetir la prueba `docker run --rm --gpus all ubuntu nvidia-smi` del paso 1.4. Otra causa: un
  modelo que no cabe en 12 GB, o `OLLAMA_NUM_CTX` muy alto.
- **El backend no arranca: `unable to open database file` o `readonly database`.** `data/` no es del
  usuario de `APP_UID`/`APP_GID`. Ver con `ls -ln data` y corregir con
  `sudo chown -R $(id -u):$(id -g) data`; luego `docker compose --profile ollama up -d backend`.
- **`MODEL_UNAVAILABLE` / `"ollama":"down"`.** `OLLAMA_BASE_URL` no es `http://ollama:11434`, o se
  levantó el Compose sin `--profile ollama`.
- **`port is already allocated` al levantar.** Otro proceso usa el puerto (5173, 8000 u 11434). Ver
  cuál con `ss -ltnp | grep -E ':(5173|8000|11434)'`. Si es un Ollama instalado en el host, pararlo
  (o cambiar `OLLAMA_PORT` en `.env`); para la app, cambiar `FRONTEND_PORT`.
- **No carga desde otro equipo, pero sí en el Acer.** `BIND_ADDR` sigue en `127.0.0.1`, la IP de LAN
  cambió (fijarla en el router) o hay un cortafuegos en el Acer (`sudo ufw status` si se usa ufw).
- **El login funciona pero vuelve a pedirlo enseguida.** `COOKIE_SECURE=true` con HTTP: el navegador
  descarta la cookie. Dejarlo en `false` mientras no haya HTTPS.
- **Groq responde `MODEL_RATE_LIMITED`.** Es el límite del plan gratuito; la app ofrece seguir con el
  modelo local. No es un fallo del despliegue.
