# Evaluación de respuestas

Resultados de la batería `evals/questions.yaml` (15 preguntas: comandos y datos comprobables,
trampas, inyección de prompt, método del Mentor y límites de OSINT). Solo las tablas resumen:
los informes completos, con las respuestas, se quedan en `evals/reports/` (fuera de git).

- **Automáticas OK**: preguntas que pasan sus reglas (`must_any`/`must_not`) y están en español,
  sobre 15. Las de revisión manual (11, 12, 14, 15) cuentan como OK si pasan sus reglas.
- **Avisos**: respuestas con emojis o con algo marcado como `warn` (p. ej. Homebrew). No suspenden.
- **Capa base**: huella `BASE_PROMPT_VERSION` (`backend/app/domain/prompts.py`). Resultados con
  capas base distintas no son directamente comparables.
- Todas las filas están corregidas con las reglas vigentes (`eval --recheck`), así que se pueden
  comparar entre sí aunque se midieran en días distintos.
- Se actualiza en cada PR que mida modelos.

Cómo medir (desde `backend/`):

```bash
uv run python -m app.cli eval --list-models
uv run python -m app.cli eval --models qwen3.5:9b --think off --personality Pentester
uv run python -m app.cli eval --recheck ../evals/reports/*.md
```

## 2026-11-21 · medición de partida (PR #32) · capa base `b870d569`

| Modelo | Proveedor | Personalidad | Automáticas OK | Avisos | Tiempo medio |
| --- | --- | --- | :---: | :---: | ---: |
| `qwen3.5:9b` · think off | ollama (local) | Mentor CTF | 13/15 | 1 | 22,8 s |
| `qwen3.5:9b` · think on | ollama (local) | Mentor CTF | 13/15 | 3 | 119,8 s |
| `openai/gpt-oss-120b` | groq (nube) | Mentor CTF | 13/15 | 4 | 1,5 s |
| `qwen/qwen3.8-27b` | groq (nube) | Mentor CTF | 12/15 | 2 | 1,3 s |
| `qwen3.5:9b` · think off | ollama (local) | Pentester | 14/15 | 1 | 22,4 s |
| `openai/gpt-oss-120b` | groq (nube) | Pentester | 13/15 | 2 | 1,2 s |
| `qwen/qwen3.8-27b` | groq (nube) | Pentester | 15/15 | 3 | 1,1 s |

## 2026-11-22 · prompts ajustados (PR #33) · capa base `0469a849`

| Modelo | Proveedor | Personalidad | Automáticas OK | Avisos | Tiempo medio |
| --- | --- | --- | :---: | :---: | ---: |
| `qwen3.5:9b` · think off | ollama (local) | Mentor CTF | 12/15 | 0 | 16,9 s |
| `openai/gpt-oss-120b` | groq (nube) | Mentor CTF | 14/15 | 0 | 1,7 s |
| `qwen/qwen3.8-27b` | groq (nube) | Mentor CTF | 15/15 | 0 | 1,2 s |
| `qwen3.5:9b` · think off | ollama (local) | Pentester | 13/15 | 0 | 16,5 s |
| `openai/gpt-oss-120b` | groq (nube) | Pentester | 15/15 | 1 | 1,5 s |
| `qwen/qwen3.8-27b` | groq (nube) | Pentester | 14/15 | 0 | 0,9 s |

Fallos que se repiten: vsftpd 2.3.4 y su puerta trasera en el 6200 (P9), y en `qwen3.5:9b` un flag
de nmap inventado (`--version-detection`) y "exiftool es una librería de Python" (P1, P3).

## 2026-11-22 · otros proveedores (PR 5) · capa base `0469a849` · personalidad Pentester

| Modelo | Proveedor | Personalidad | Automáticas OK | Avisos | Tiempo medio |
| --- | --- | --- | :---: | :---: | ---: |
| `gemma4:12b` · think off | ollama (local) | Pentester | 14/15 | 0 | 24,7 s* |
| `qwen/qwen3.6-35b-a3b` | lmstudio (local) | Pentester | 14/15 | 0 | 17,9 s* |
| `qwen3.5:9b` · think off (PR #33) | ollama (local) | Pentester | 13/15 | 0 | 16,5 s |
| `qwen/qwen3.8-27b` (PR #33) | groq (nube) | Pentester | 14/15 | 0 | 0,9 s |
| `qwen3.5:9b` · think off (PR #32, capa `b870d569`) | ollama (local) | Pentester | 14/15 | 1 | 22,4 s |
| `qwen/qwen3.8-27b` (PR #32, capa `b870d569`) | groq (nube) | Pentester | 15/15 | 3 | 1,1 s |

\* **Tiempos no representativos**, medidos en la máquina de desarrollo (GTX 1070, 8 GB, con el
escritorio ocupando ~1,3 GB):
- `qwen/qwen3.6-35b-a3b` (MoE, 3B activos) corre en LM Studio con ~6,5 GB en la GPU y el resto en RAM,
  con contexto 8192, `parallel 4` y el razonamiento desactivado (`PROVIDER_LMSTUDIO_REASONING_EFFORT=none`;
  con él activado, la primera pregunta seguía pensando a los varios minutos).
- `gemma4:12b` tampoco cabe entera en los 8 GB, así que parte va a la CPU.
- No se pueden medir a la vez: comparten la única GPU (con el Qwen3.6 cargado en LM Studio, gemma4
  fallaba por falta de memoria en CUDA).

Los dos nuevos fallan solo la P9 (vsftpd 2.3.4: no dan el puerto 6200 de la puerta trasera), el
fallo de conocimiento más repetido de la batería. En las de revisión manual (11, 12, 14, 15) se
comportan bien: no inventan la flag, dicen que el paquete no existe (el Qwen3.6 sugiere `recon-ng`),
piden contexto en el reto en vez de dar la solución y rechazan localizar a una persona ofreciendo una
alternativa.
