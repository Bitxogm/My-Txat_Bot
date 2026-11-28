# Stack previsto para el fine-tuning (Fase 6)

Nota breve, no una spec: qué herramientas se usarán cuando haya datos suficientes (ADR-023). La spec
se escribirá al empezar la Fase 6.

## Entrenamiento

- **PyTorch** como base, con **Transformers** (Hugging Face) para cargar el modelo base de 7-9B.
- **PEFT** (LoRA): solo se entrenan adaptadores pequeños, no los pesos del modelo.
- **bitsandbytes** en 4 bits (QLoRA): el modelo base cuantizado cabe en los 12 GB de la RTX 3060 del
  Acer.
- **TRL** (`SFTTrainer`): ajuste supervisado sobre pares pregunta/respuesta derivados del JSONL de
  valoraciones (`docs/feedback-export.md`): la pregunta, y como respuesta la corrección (si la hay)
  o la respuesta con 👍.
- **Unsloth** como primera opción en la RTX 3060: envuelve lo anterior con kernels propios que gastan
  menos VRAM y entrenan más rápido en GPUs de 12 GB. Si da problemas con el modelo base elegido, se
  vuelve a la combinación estándar Transformers + PEFT + bitsandbytes + TRL.

## Salida

- Fusionar el adaptador con el modelo base, **exportar a GGUF** y crear en Ollama un modelo
  versionado `txat-void:vN` (`Modelfile` + `ollama create`, como en ADR-020).
- **Comparar con el modelo base en la batería** (`docs/evals.md`), con la misma memoria fija y la misma
  huella de la capa base. Si sale peor, se descarta: el modelo base sigue disponible y nada cambia en
  la app.

## Descartados

- **TensorFlow**: Transformers v5 es solo PyTorch, y todo el ecosistema de LoRA/QLoRA (PEFT,
  bitsandbytes, TRL, Unsloth) también.
- **scikit-learn para entrenar**: es aprendizaje automático clásico (clasificadores, regresión,
  clustering), no sirve para ajustar un modelo de lenguaje.

## scikit-learn, para analizar el dataset

Sí tiene sitio fuera del entrenamiento:
- **Clustering de correcciones por tema** (TF-IDF o embeddings + k-means), para ver en qué falla más el
  modelo y qué preguntas candidatas añadir a la batería.
- **Métricas de la batería**: aciertos por categoría de pregunta y por modelo, y comparación entre
  `txat-void:vN` y el modelo base.
