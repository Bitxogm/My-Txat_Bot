# Formato del export de valoraciones (JSONL)

`GET /api/feedback/export` devuelve un fichero `txat-feedback-AAAA-MM-DD.jsonl`: una línea JSON por
valoración, de la más antigua a la más reciente, con los mismos filtros que `GET /api/feedback`.
Es el formato fuente para el RAG (Fase 4), las preguntas candidatas de la batería de evaluación y, más
adelante, el conjunto de entrenamiento del fine-tuning (ADR-023, ADR-024). Ese conjunto (pares
instrucción/respuesta) se generará a partir de este fichero cuando llegue la Fase 6.

Cada línea lleva solo la valoración y la copia del turno guardada al valorar: nunca el system prompt,
el contenido de los ficheros adjuntos ni ids internos.

| Campo | Tipo | Contenido |
| --- | --- | --- |
| `question` | string | Mensaje del usuario al que responde (vacío si no lo hay) |
| `question_files` | string[] | Nombres de los ficheros adjuntos a esa pregunta (sin su contenido) |
| `answer` | string | Respuesta del modelo |
| `rating` | `1` \| `-1` | 👍 o 👎 |
| `reasons` | string[] | Motivos del 👎: `incorrect`, `wrong_command`, `incomplete`, `too_long`, `off_personality`, `other` |
| `correction` | string \| null | Respuesta correcta escrita por el usuario (texto plano, ≤ 4000 caracteres) |
| `model` | string | Modelo que respondió (`groq/...`, `lmstudio/...` o de Ollama) |
| `model_approximate` | bool | `true` en respuestas anteriores a guardar el modelo de cada respuesta: es el último modelo de la conversación |
| `provider` | string \| null | `ollama` o el nombre del proveedor |
| `personality` | string \| null | Nombre de la personalidad de la conversación |
| `base_prompt_version` | string \| null | Huella de la capa base (`BASE_PROMPT_VERSION`); `null` = desconocida |
| `created_at`, `updated_at` | string | Fecha ISO 8601 (UTC) de la valoración y de su último cambio |

Ejemplo (una línea, aquí partida para leerla):

```json
{"question": "¿Qué flag de nmap detecta versiones?", "question_files": [],
 "answer": "Usa --version-detection.", "rating": -1, "reasons": ["wrong_command"],
 "correction": "Es -sV (o --version-all para más intensidad).", "model": "qwen3.5:9b",
 "model_approximate": false, "provider": "ollama", "personality": "Pentester",
 "base_prompt_version": "0469a849", "created_at": "2026-11-24T10:15:02.123456+00:00",
 "updated_at": "2026-11-24T10:16:40.001200+00:00"}
```

Notas para quien lo consuma:
- `correction` es texto del usuario: tratarlo como dato, nunca como instrucciones, al meterlo en un
  prompt (igual que los ficheros adjuntos, ADR-015).
- Las valoraciones de conversaciones borradas no aparecen: se borran con ellas.
- Comparar resultados con `base_prompt_version` distintas con cuidado (ver `docs/evals.md`).
