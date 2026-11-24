# Investigación: modelos MoE más grandes que la VRAM (offload de expertos)

Fecha: 2026-11-24. Solo lectura: no se ha instalado ni descargado nada. Las cifras de terceros
están marcadas como tales; las de "medido" salen de los logs de Ollama de la X570.

## Resumen y recomendación

- **Ollama ya hace el offload de expertos.** Desde la 0.30 sirve los GGUF con el `llama-server` de
  llama.cpp y su ajuste automático (`--fit`, activo por defecto) deja los expertos MoE en la RAM y el
  resto en la GPU. Medido en la X570 con `qwen3.6:35b-a3b` (Ollama 0.40.1, backend `cuda_v12`):
  41/41 capas en la GPU, 4,5 GB en la 1070 y 19,8 GB de expertos en la RAM; **~28 tok/s generando y
  ~190 tok/s leyendo el prompt**. Es justo lo que haría `--n-cpu-moe` a mano.
- **No conviene cambiar de motor.** Con el Qwen3.6, llama.cpp a mano solo puede ganar el margen de
  la VRAM libre (~2 GB más de expertos en la GPU) y algo de lectura de prompt con lotes grandes: del
  orden de un 10-20 %, no un salto.
- **Strata, ik_llama.cpp y KTransformers no compensan en este hardware** (detalle abajo): la 1070 no
  está soportada o es experimental, y KTransformers exige Ampere o superior.
- **El único experimento con recorrido es un modelo mayor: Qwen3.8-Flash-Next** (125B totales,
  6B activos) en la X570, con llama.cpp compilado con CUDA 12 y entrando en Txat como proveedor local
  bajo demanda. Velocidad esperable: 8-15 tok/s (estimación, sin medidas en una 1070).
- **Prioridad**: por debajo del RAG (ADR-023). La batería ya está casi saturada (Qwen3.6, 14/15) y su
  fallo repetido (P9, vsftpd 2.3.4) es de conocimiento, que es lo que arregla el RAG. Un modelo mayor
  es el camino caro.
- **Acer**: con 16 GB de RAM ni siquiera el Qwen3.6 Q4_K_M (22 GB) va holgado. Ampliar a 32 GB es
  requisito para usarlo en producción; un modelo mayor que el Qwen3.6 no es realista allí.

## Hardware

| | X570 (desarrollo) | Acer (producción) |
| --- | --- | --- |
| CPU | AMD Ryzen 5 3600X, 6 núcleos / 12 hilos, hasta 4,4 GHz, AVX2 (sin AVX-512) | sin comprobar |
| RAM | 64 GB DDR4-2666, doble canal (2 x 32 GB, 2 ranuras libres), ~42 GB/s teóricos | 16 GB (ampliable a 32 GB) |
| GPU | GTX 1070 8 GB, Pascal (CC 6.1), driver 580, ~1,2 GB ocupados por el escritorio | RTX 3060 12 GB, Ampere (CC 8.6) |
| Disco | 2 x Samsung 870 QVO 1 TB (SATA, QLC; ~550 GB libres) | sin comprobar |
| Software | Ubuntu 24.04, gcc 13.3, `libvulkan-dev`; sin `cmake`, sin `glslc`, sin toolkit CUDA | |

Con la parte del modelo que vive en RAM, la velocidad de generación la marca el ancho de banda de la
memoria: DDR4-2666 en doble canal es el cuello de botella de la X570, no la 1070. CUDA 13 ya no
compila para Pascal; CUDA 12.x sí (Ollama ya usa su backend `cuda_v12` con esta tarjeta).

## 1. Strata (github.com/Niko1221/Strata)

- **Qué es**: motor C++ para MoE grandes en hardware doméstico, MIT, API compatible con OpenAI
  (`/v1/chat/completions`, puerto 8080) y Anthropic. Reparte expertos entre VRAM, RAM y disco.
- **Requisitos**: tarjetas soportadas RTX 20/30/40/50. La serie GTX 10 funciona con el motor CUDA 12
  por "rutas experimentales, opt-in" escritas por la comunidad; los mantenedores solo tienen una P100.
  Recomiendan 12 GB de VRAM o más "para cualquier tarjeta"; la 1070 tiene 8.
- **Pascal en los issues**: una 1070 Ti con Gyro-S "funciona" (#4517, cerrado); regresión de
  rendimiento en una 1070 con 0.2.17 (#6377, abierto); regresiones en 1080 Ti y P40 (#6769, #5268).
- **Determinismo**: su propia documentación admite que el mismo prompt a temperatura 0 puede dar otra
  respuesta según la caché o el borrador especulativo, y hay issues abiertos (#4059 logprobs distintos
  a temperatura 0, #6736, #6977, #6776: 10 de 300 respuestas cambiadas, 7 de bien a mal). Para Txat
  importa: la batería deja de ser repetible.
- **Madurez**: proyecto muy activo y popular (~47 k estrellas), pero con 857 issues abiertos, 618 PR
  abiertas, una versión casi cada día (0.2.17 a 0.2.20 entre el 20 y el 22 de noviembre) y varios
  informes de cuelgues en tarjetas modernas. Joven y cambiante.
- **Qwen3.8-Flash-Next**: licencia **Qwen Community License 1.0** (no Apache 2.0). Permite uso
  comercial con condiciones (atribución por encima de 100 M usuarios o 20 M$/mes; licencia aparte para
  ofrecerlo como servicio). Uso personal e interno, sin problema. Leer el LICENSE oficial antes de
  cualquier otro uso.
- **Cifras del autor** (RTX 5070 12 GB, DDR5, 64 GB): Q2_0 ~87 tok/s; necesita ~34 GB de expertos +
  ~6 GB (descarga de 66 GB). Ni de lejos comparable con una 1070 y DDR4-2666.

**Veredicto**: no para la X570 (1070 por debajo del mínimo recomendado, ruta experimental, no
determinista). En el Acer con 32 GB sería probable, pero con los mismos riesgos de estabilidad.

## 2. llama.cpp con `--n-cpu-moe` / `--fit`

- **Opciones**: `--n-cpu-moe N` deja en la CPU los expertos de N capas; `--cpu-moe`, todos;
  `-ot "exps=CPU"` lo mismo por patrón; `--fit on` (por defecto) ajusta solo lo que no se fija a mano
  para caber en la VRAM, con `--fit-target` (margen, 1024 MiB por defecto). Hay además una caché de
  expertos en GPU (`--moe-cache-mib`). Para afinar a mano se recomienda `-fit off`, lotes grandes
  (`-b 4096 -ub 4096`) y `--no-mmap`.
- **Compilar para la 1070**:
  - **CUDA 12.x** (recomendado): `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61`. El toolkit 12.9 se
    puede instalar en el directorio de usuario con el instalador `.run` (`--toolkit --toolkitpath`),
    sin `sudo` y sin tocar el driver. Admite gcc 13. `cmake` se puede instalar con `uv tool`.
  - **Vulkan**: `-DGGML_VULKAN=ON`. Necesita `glslc` y `spirv-headers` del sistema (apt, con `sudo`:
    lo tendrías que instalar tú). En NVIDIA suele rendir menos que CUDA.
- **Ganancia frente a Ollama con el Qwen3.6**: poca. Ollama ya usa este mismo `llama-server` con
  `--fit`, y los logs muestran el reparto correcto (expertos en RAM, 28 tok/s). Lo que llama.cpp a
  mano añade: usar los ~2 GB de VRAM libres para algunos expertos más, lotes de prompt más grandes y
  flash attention. Ganancia esperable pequeña (estimación), a costa de un segundo motor.
- **Lo que sí aporta**: modelos que Ollama aún no carga (arquitecturas nuevas o ficheros extra, como
  la tabla de n-gramas de Qwen3.8-Flash-Next con `--ple`), y control fino de la colocación.

## 3. ik_llama.cpp y KTransformers

| | ik_llama.cpp | KTransformers |
| --- | --- | --- |
| Qué aporta | Fork de llama.cpp con cuantizaciones propias (IQ_K, `_R4`…), reempaquetado en CPU (`-rtr`) y mejoras para MoE híbrido | Expertos en CPU con kernels AVX-512/AMX y atención en GPU, servido con un fork de SGLang |
| CPU | AVX2 basta | AVX2 solo con el backend llamafile; lo rápido pide AVX-512 o AMX (Intel) |
| GPU | Solo CUDA. Pascal "funcional", con pasos de flash attention en la CPU; no aceptan issues de GPUs viejas ni Vulkan | Rueda de pip: CC 8.0+ (Ampere). GTX 10xx "no soportada" explícitamente |
| API | `llama-server` propio | SGLang (fork `sglang-kt`); API OpenAI no confirmada en la doc actual |
| Compatibilidad | Sus cuantizaciones propias no cargan en llama.cpp normal ni en Ollama | Conversión de pesos propia para AMX |
| X570 | Posible, poca ganancia: el cuello es la DDR4, no los kernels | No (Pascal) |
| Acer | Posible | En teoría sí (Ampere), pero sin AVX-512/AMX pierde su ventaja; complejo |

**Veredicto**: demasiado complejos para lo que ganan aquí. ik_llama.cpp brilla con CPUs de muchos
canales de memoria y cuantizaciones propias; KTransformers con Xeon con AMX y GPUs modernas.

## 4. Modelos "superiores" realistas en la X570 (64 GB)

Presupuesto: ~50 GB libres de RAM (el escritorio, Docker y el resto ocupan ~10 GB) + ~6,5 GB de VRAM.
Velocidades estimadas por ancho de banda (DDR4-2666, ~42 GB/s teóricos): sin medir en esta máquina.

| Modelo | Activos | Fichero | Cabe | Generación esperable | Comentario |
| --- | ---: | --- | :---: | --- | --- |
| `qwen3.6:35b-a3b` Q4_K_M (hoy) | 3B | 22 GB | sí | **28 tok/s (medido)** | 14/15 en la batería |
| Qwen3.8-Flash-Next Q2/IQ2 | 6B | ~40-45 GB + tabla n-gramas | justo | 8-15 tok/s | El candidato. SWE-bench Pro 62,5 según Qwen (no independiente) |
| Qwen3.8-Flash-Next IQ3_XXS | 6B | ~49 GB | muy justo | 6-12 tok/s | Sin margen para nada más en la máquina |
| gpt-oss-120b MXFP4 | 5,1B | ~63 GB | no | — | Pide 64 GB libres; con 96 GB sería otra cosa |
| GLM-4.5-Air Q3 | 12B | ~50 GB | justo | 3-5 tok/s | Demasiados activos para DDR4 |

**Cuantización agresiva**: en un MoE grande, Q2/IQ2 en los expertos pierde menos que en un modelo
denso del mismo tamaño, pero pierde: más errores de datos concretos (puertos, flags, versiones), que es
justo lo que mide la batería. Pasar de un 35B en Q4 a un 125B en Q2 puede compensar en razonamiento y
código; no hay comparación independiente con el Qwen3.6 para saberlo. Por eso hay que medirlo.

## 5. Encaje con Txat

Todos exponen una API compatible con OpenAI, así que entran como proveedor (ADR-019) sin tocar
código: `PROVIDERS=llamacpp`, `PROVIDER_LLAMACPP_BASE_URL=http://127.0.0.1:<puerto>/v1`,
`PROVIDER_LLAMACPP_LOCAL=true`. El choque es con ADR-020: dos motores no se ven en la GPU.

Propuesta (sin cambiar de motor):
- **Ollama sigue siendo el motor por defecto** para todo lo que carga.
- **Un motor experimental solo bajo demanda**, igual que LM Studio en ADR-020: antes de arrancarlo se
  descarga el modelo de Ollama (`ollama stop <modelo>`), y al terminar se para el servidor. Nunca los
  dos con un modelo cargado a la vez. Escuchando solo en `127.0.0.1`.
- **Si el experimento gana**, no migrar: esperar a que Ollama cargue ese modelo (usa el mismo
  `llama-server` por dentro y suele llegar semanas después) e importarlo con un `Modelfile`. Solo si
  Ollama no lo soporta en un plazo razonable, valorar llama.cpp como motor único (un ADR nuevo que
  sustituya a ADR-020).

## Riesgos

- **RAM**: un Q2 de 125B deja la X570 sin margen; con navegador y Docker puede acabar en swap.
- **Soporte del modelo**: Qwen3.8-Flash-Next trae arquitectura nueva (atención dispersa, tabla de
  n-gramas). Hay fuentes que piden la rama de Unsloth de llama.cpp y otras que dicen que la versión
  b12233+ ya carga la tabla con `--ple`. Hay que comprobarlo antes de descargar 50 GB.
- **Disco**: SATA QLC (~550 MB/s), no NVMe. Cargar 45 GB tarda ~1,5 min; el streaming de expertos
  desde disco (Strata) sería lento.
- **Comparabilidad**: la 1070 no es la máquina final. Los tiempos sirven para comparar entre sí, no
  para prever el Acer (ver la nota de tiempos de `docs/evals.md`).
- **Batería**: 15 preguntas, casi saturada. Un 15/15 frente a 14/15 no demuestra un modelo mejor;
  hay que leer las respuestas de revisión manual.
- **Licencia**: Qwen Community License, no Apache 2.0. Sin problema en uso personal.

## Plan B

Decisión del 2026-11-24: la fase A del plan siguiente no se ejecuta, porque una ganancia estimada del
10-20 % no compensa instalar CUDA 12 y compilar. Se queda Ollama como único motor (ADR-020).

Si Ollama añade a su biblioteca Qwen3.8-Flash-Next u otro MoE mayor que quepa en la X570, se prueba sin
cambiar de motor ni compilar nada (desde `backend/`, un paso cada vez):

1. Descargarlo con Ollama:
   ```bash
   ollama pull <modelo>
   ```
2. Medirlo con Pentester:
   ```bash
   uv run python -m app.cli eval --models <modelo> --think off --personality Pentester
   ```
3. Medirlo con Mentor CTF (la personalidad por defecto de la batería):
   ```bash
   uv run python -m app.cli eval --models <modelo> --think off
   ```
4. Medir la referencia con Pentester:
   ```bash
   uv run python -m app.cli eval --models qwen3.6:35b-a3b --think off --personality Pentester
   ```
5. Medir la referencia con Mentor CTF:
   ```bash
   uv run python -m app.cli eval --models qwen3.6:35b-a3b --think off
   ```
6. Añadir las filas a `docs/evals.md` y leer a mano las preguntas 11, 12, 14 y 15.

Mismo criterio de éxito que en el plan siguiente. Con un modelo así la X570 va justa de RAM: cerrar
lo que no haga falta antes de medir y comprobar con `ollama ps` cuánto queda en la GPU.

## Plan de prueba propuesto (no ejecutado; fase A descartada, ver Plan B)

Dos fases: la A sin descargar ningún modelo (Qwen3.6 en llama.cpp frente a Ollama); la B solo si la
comprobación del paso 7 sale bien. Un paso cada vez, desde la X570. Ningún paso usa `sudo`.

**Fase A: compilar llama.cpp y comparar con el Qwen3.6 que ya está en disco**

1. Instalar `cmake` en el usuario:
   ```bash
   uv tool install cmake
   ```
2. Descargar el instalador `.run` de CUDA 12.9 (~5 GB). El enlace exacto se toma de la página de
   archivo de NVIDIA (CUDA Toolkit 12.9, Linux x86_64, Ubuntu 24.04, "runfile (local)"):
   ```bash
   wget -P ~/Descargas "<enlace del runfile de CUDA 12.9>"
   ```
3. Instalar solo el toolkit en el directorio de usuario (no toca el driver):
   ```bash
   sh ~/Descargas/cuda_12.9.*_linux.run --silent --toolkit --toolkitpath=$HOME/opt/cuda-12.9 --no-man-page
   ```
4. Clonar llama.cpp:
   ```bash
   git clone https://github.com/ggml-org/llama.cpp ~/src/llama.cpp
   ```
5. Configurar para la 1070:
   ```bash
   cmake -S ~/src/llama.cpp -B ~/src/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -DCMAKE_CUDA_COMPILER=$HOME/opt/cuda-12.9/bin/nvcc
   ```
6. Compilar el servidor y el banco de pruebas:
   ```bash
   cmake --build ~/src/llama.cpp/build --config Release -j 12 --target llama-server llama-bench
   ```
7. Comprobar si esta versión soporta Qwen3.8-Flash-Next (decide si hay fase B):
   ```bash
   git -C ~/src/llama.cpp log --oneline -i -E --grep "qwen3\.8|flash.next|engram|ple" | head -20
   ```
8. Descargar de la GPU el modelo de Ollama:
   ```bash
   ollama stop qwen3.6:35b-a3b
   ```
9. Medir velocidad del Qwen3.6 en llama.cpp con el GGUF de LM Studio (sin descargar nada):
   ```bash
   ~/src/llama.cpp/build/bin/llama-bench -m ~/.lmstudio/models/lmstudio-community/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-Q4_K_M.gguf -ngl 99 -fa 1 -p 512 -n 128 -ub 512,2048
   ```
   Comparar con Ollama: ~28 tok/s generando, ~190 tok/s leyendo el prompt.

**Fase B: Qwen3.8-Flash-Next contra `qwen3.6:35b-a3b` de Ollama**

10. Elegir en https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF la cuantización más pequeña de
    calidad razonable (Q2/IQ2, ≤ 45 GB) y la tabla de n-gramas correspondiente, y descargarlas:
    ```bash
    uvx --from huggingface_hub hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "<patrón de la cuantización elegida>" --local-dir ~/models/qwen3.8-flash-next
    ```
11. Arrancar el servidor solo en local, con el razonamiento apagado como en el resto de la batería:
    ```bash
    ~/src/llama.cpp/build/bin/llama-server -m ~/models/qwen3.8-flash-next/<modelo>.gguf --ple ~/models/qwen3.8-flash-next/<tabla>.gguf -ngl 99 -fa on -c 8192 -b 2048 -ub 2048 --jinja --reasoning-budget 0 --host 127.0.0.1 --port 8081 --alias qwen3.8-flash-next
    ```
12. Medir con la batería (desde `backend/`, variables solo para este proceso, sin tocar `.env`):
    ```bash
    PROVIDERS=llamacpp PROVIDER_LLAMACPP_BASE_URL=http://127.0.0.1:8081/v1 PROVIDER_LLAMACPP_MODELS=qwen3.8-flash-next PROVIDER_LLAMACPP_LOCAL=true PROVIDER_LLAMACPP_CONTEXT_TOKENS=8192 uv run python -m app.cli eval --models llamacpp/qwen3.8-flash-next --personality Pentester
    ```
13. Parar `llama-server` (Ctrl+C en su terminal) y medir la referencia en Ollama, que aún no tiene
    medición en la batería (el 14/15 del Qwen3.6 fue en LM Studio):
    ```bash
    uv run python -m app.cli eval --models qwen3.6:35b-a3b --think off --personality Pentester
    ```
14. Repetir los pasos 11-13 con la personalidad por defecto de la batería (Mentor CTF), quitando
    `--personality Pentester`.
15. Añadir las filas a `docs/evals.md` y leer a mano las preguntas 11, 12, 14 y 15.

Criterio de éxito: Qwen3.8-Flash-Next acierta P9 o mejora claramente las respuestas de revisión
manual, a una velocidad usable (≥ 8 tok/s). Si no, se queda Qwen3.6 en Ollama y se borran los ~50 GB.

## Fuentes

- Strata: [repo](https://github.com/Niko1221/Strata), [DETAILS.md](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md), [releases](https://github.com/Niko1221/Strata/releases), [issues](https://github.com/Niko1221/Strata/issues) (OLDER_GPUS.md, INSTALL.md, #4059, #4517, #6377, #6776)
- Licencia Qwen3.8-Flash-Next: [ModelScope](https://www.modelscope.ai/models/Qwen/Qwen3.8-Flash-Next), [fichero de licencia en Ollama](https://ollama.com/library/qwen3.8-flash-next:125b-mlx/blobs/40ba997ad88d), [cellcog.ai](https://cellcog.ai/blog/qwen3-8-flash-next/)
- Qwen3.8-Flash-Next: [blog de Qwen](https://qwen.ai/blog?id=qwen3.8-flash-next), [GGUF de Unsloth](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF), [tabla engram](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/blob/main/engram/README.md), [computingforgeeks](https://computingforgeeks.com/run-qwen3-8-flash-next-locally/)
- llama.cpp: [build.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md), [README del servidor](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [guía de offload MoE (Hugging Face)](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- Ollama y MoE: [issue #14579](https://github.com/ollama/ollama/issues/14579), [PR #16688](https://github.com/ollama/ollama/pull/16688), [aliteq (secundaria)](https://aliteq.com/ollama-moe-offload-cpu), [v0.30.0](https://github.com/ollama/ollama/releases/tag/v0.30.0)
- gpt-oss-120b con offload: [hardware-corner](https://www.hardware-corner.net/guides/gpt-oss-offloading-moe-layers/)
- CUDA y Pascal: [CUDA Features Archive](https://docs.nvidia.com/cuda/cuda-features-archive/index.html), [Tom's Hardware](https://www.tomshardware.com/pc-components/gpus/nvidia-to-drop-cuda-support-for-maxwell-pascal-and-volta-gpus-with-the-next-major-toolkit-release)
- ik_llama.cpp: [repo](https://github.com/ikawrakow/ik_llama.cpp)
- KTransformers: [repo](https://github.com/kvcache-ai/ktransformers), [kt-kernel](https://github.com/kvcache-ai/ktransformers/blob/main/kt-kernel/README.md)
