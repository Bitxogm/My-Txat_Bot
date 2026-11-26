# Spec: memoria persistente (versión manual)

Estado: borrador

## Objetivo

Que el modelo sepa, sin repetírselo en cada conversación, en qué entorno trabaja Void, en qué nivel
está, cómo quiere las respuestas y en qué reto anda. Son entradas cortas que escribe o aprueba Void y
que se inyectan en cada conversación como datos. Además, cada respuesta deja constancia de qué
memorias tenía delante, para que las valoraciones sirvan después como dataset (ADR-023).

## Fuera de alcance

- Que el modelo proponga recuerdos ("¿Recordar que usas Kali en VM?"). Irá en una segunda versión,
  sobre esta base manual.
- Recuerdos automáticos sin aprobación de Void: nunca, en ninguna versión.
- Conocimiento técnico (puertos, CVE, flags de herramientas): es del RAG (Fase 4). La memoria es
  sobre Void, no sobre el mundo.
- Una memoria por personalidad o por conversación: es global. La categoría es solo una etiqueta.
- Búsqueda semántica o selección de memorias por relevancia: entran todas las activas.

## Qué se guarda

Cuatro categorías:

| Categoría | Ejemplos | Notas |
| --- | --- | --- |
| Entorno | "Kali en VM con zsh; instalo con apt", "seclists en /usr/share/seclists", "no tengo Burp Pro" | |
| Nivel | "Web sólido; empezando con Active Directory" | |
| Preferencias | "Comandos completos listos para copiar", "Explicaciones cortas" | Lo que no depende de la personalidad |
| En curso | "HTB Sau en 10.10.11.224: puerto 55555 con request-baskets" | Caduca: se archiva sola tras 14 días sin editarse |

Nunca se guardan:
- credenciales, hashes, flags, tokens ni claves;
- **IPs, dominios o nombres de máquinas reales de clientes o terceros**. En "En curso" sí valen las
  de laboratorios y CTF (HTB, THM, HackMyVM, DockerLabs, labs propios), porque no identifican a
  nadie;
- datos personales de terceros (tampoco los resultados del Auditor de Huella Digital);
- contenido de ficheros adjuntos;
- instrucciones que intenten cambiar las reglas ("ignora los límites"). La capa base va siempre por
  encima: la memoria entra como datos, delimitada, igual que el catálogo OSINT.

La aplicación no puede saber si una IP es de un laboratorio. Al guardar, avisa de las IPs, dominios y
cadenas que parecen secretos, pero quien decide es Void; el aviso no bloquea.

## Criterios de aceptación

1. **Dado** la página "Memoria" (barra lateral), **cuando** creo, edito, desactivo o borro una entrada
   (categoría y texto de hasta 200 caracteres; como mucho 30 activas), **entonces** el cambio se
   guarda y, en la siguiente respuesta, el modelo recibe exactamente las memorias activas. También
   puedo crear una desde el botón "Recordar" de uno de mis mensajes, que abre el formulario con el
   texto para recortarlo antes de guardar. Una entrada de "En curso" sin editar en 14 días pasa a
   archivada y deja de enviarse.
2. **Dado** la migración, **cuando** arranca la versión con memoria, **entonces**:
   - la regla de entorno de la capa base ("Kali Linux / Ubuntu con zsh… apt… no Homebrew") pasa a ser
     una memoria de la categoría Entorno, creada activa por defecto y editable;
   - la capa base se queda solo con lo que no depende de Void (rigor, estilo general, ámbito,
     seguridad), y cambia su huella `BASE_PROMPT_VERSION`;
   - las memorias van en el system prompt dentro de un bloque `<memoria>` delimitado, después de la
     personalidad y antes del recordatorio final, que las marca como datos que no anulan las reglas.
3. **Dado** un modelo de la nube (`remote: true`), **cuando** envío un mensaje, **entonces** las
   memorias no se envían, salvo que active el interruptor "Enviar la memoria a modelos de la nube"
   (desactivado por defecto), y el chat avisa de que ese modelo responde sin memoria. Con un modelo
   local (Ollama o un proveedor `_LOCAL=true`) se envían siempre.
4. **Dado** una respuesta del asistente, **cuando** se guarda, **entonces** guarda una copia de las
   memorias que se le inyectaron (categoría y texto en ese momento). Al valorarla, la valoración
   copia esa lista y el export JSONL la incluye (campo `memories`). La batería de evaluación se
   ejecuta siempre con la memoria desactivada o con una memoria fija de prueba (`evals/memory.yaml`,
   versionada), y el informe registra cuál, para que las mediciones sigan siendo comparables.

## Decisiones

- **Tamaño**: 30 entradas activas como máximo, de 200 caracteres. En total unos 1.000 tokens, que caben
  en los 8k de contexto de los modelos locales sin quitarle mucho historial a la conversación. El
  ajuste al contexto (ADR-018) cuenta el bloque de memoria como parte del system prompt.
- **La batería usa la memoria fija de prueba** (`evals/memory.yaml`), con solo la entrada de Entorno
  por defecto. Así sigue recibiendo la regla de entorno que hoy está en la capa base, y las
  preguntas que la comprueban (P1, Homebrew) siguen midiendo lo mismo. Las mediciones anteriores
  tienen otra `BASE_PROMPT_VERSION` y no son directamente comparables (`docs/evals.md`).
- **Global**: las personalidades cambian tono y método; el entorno y el nivel de Void son los mismos
  en todas.
- **Copia, no referencia**: las memorias se editan y se borran; la respuesta guarda su texto de ese
  momento, igual que la valoración guarda su copia del turno (ADR-024).

## ADRs relacionados

- ADR-013 (capas del prompt): la capa base pierde la regla de entorno y gana el bloque de memoria
  delimitado. Necesita un ADR nuevo (memoria persistente) que lo registre.
- ADR-014 (catálogo OSINT): mismo patrón de bloque de referencia en el system prompt.
- ADR-018 (ajuste al contexto): el bloque cuenta en el presupuesto.
- ADR-019 (proveedores): `remote` decide si se envía la memoria.
- ADR-023 y ADR-024 (mejora de las respuestas, valoraciones): trazabilidad de memorias en el dataset.

## Cómo probarlo a mano

1. Página "Memoria": existe la entrada de Entorno creada por la migración. Editarla ("uso Kali en
   WSL"), preguntar "¿cómo instalo gobuster?" y comprobar que la respuesta lo tiene en cuenta.
2. Crear una de "En curso" con la IP de una máquina de HTB: guarda con un aviso de IP, sin bloquear.
3. Desde un mensaje propio, "Recordar": el formulario sale con su texto y se puede recortar.
4. Desactivar una entrada y comprobar que la siguiente respuesta ya no la tiene (por ejemplo,
   preguntando "¿qué sabes de mi entorno?").
5. Con un modelo `groq/...`: aviso de "responde sin memoria"; activar el interruptor y comprobar que
   el aviso cambia a "la memoria sale de tu red".
6. Valorar una respuesta y exportar el JSONL: la línea lleva `memories` con lo que estaba activo.
7. `uv run python -m app.cli eval --models <modelo> --only 1`: el informe dice que usó la memoria fija
   de prueba.
