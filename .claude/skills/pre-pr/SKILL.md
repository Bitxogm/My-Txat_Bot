---
name: pre-pr
description: Comprobaciones antes de abrir una PR en Txat_bot. Úsala antes de proponer o abrir cualquier PR, o cuando se pida "pasar el check", "dejarlo listo para PR" o similar.
---

# Checklist pre-PR

Ejecuta en orden y para en el primer fallo, mostrando el error.

1. **Rama**: `git branch --show-current` no puede ser `main`. Nombre `feat/`, `fix/`, `chore/`, `docs/`, `refactor/` o `test/` en inglés.
2. **Secretos** (repo público): revisa `git diff main...HEAD` buscando `.env`, tokens, contraseñas, IPs reales, nombres de host Tailscale, rutas con el usuario local, ficheros `.db`/`.sqlite`, modelos. Si `gitleaks` está instalado: `gitleaks git --log-opts="main..HEAD"`.
3. **Backend** (si hay cambios en `backend/`): desde `backend/`, `uvx ruff check . && uvx ruff format --check .` y `uv run pytest`.
4. **Frontend** (si hay cambios en `frontend/` y existe `package.json`): desde `frontend/`, `npm run lint && npm run format:check && npx tsc --noEmit && npm run test -- --run && npm run build`.
5. **Compose** (si cambió `docker-compose.yml`): `docker compose config -q`.
6. **Docs**: si cambió arquitectura, comandos o fase, comprueba que `CLAUDE.md`, `docs/` y el roadmap lo reflejan. Decisiones nuevas → ADR en `docs/decisions.md`.
7. **Commits**: Conventional Commits en inglés.

Resume el resultado en una tabla corta (paso, estado). Si algo falla, corrígelo y vuelve a ejecutar el checklist; no abras la PR con nada en rojo.

## Si todo está en verde, continúa sin parar

8. **Push**: `git push -u origin <rama>`.
9. **PR**: si no existe, `gh pr create --base main` con título en inglés (Conventional Commits) y descripción en español siguiendo `.github/pull_request_template.md`. Si ya existe, basta con el push.
10. **CI**: `gh run watch` sobre el run de la rama hasta que termine. Si falla, revisa con `gh run view --log-failed`, corrige, haz push y repite.
11. **Aviso**: entrega el enlace de la PR y el estado de la CI. **Nunca** mergees: el merge lo hace Void.
