# Spec: barra lateral colapsable y contrastes WCAG AA

Estado: implementada (barra lateral #54; contrastes en fix/wcag-aa-contrast)

## Objetivo

Más espacio para leer en escritorio, plegando la barra lateral cuando estorba, y una interfaz legible
para cualquiera en los dos temas: todo el texto y los controles cumplen WCAG AA. Son los pendientes
de UX de la Fase 3 (`docs/roadmap.md`).

## Fuera de alcance

- Redimensionar la barra lateral arrastrando, cambiar su contenido u orden, o dejar una franja de
  iconos al plegarla: plegada se oculta del todo.
- Un sistema de atajos de teclado general: solo Ctrl+B.
- WCAG AAA y una auditoría de accesibilidad completa (lectores de pantalla, orden de foco): solo
  contraste AA.
- Colores de marca nuevos o rediseño del tema: solo se ajustan las variables existentes.
- Los componentes generados de `components/ui/`, salvo que el fallo de contraste esté en una clase
  que no se pueda corregir desde las variables del tema.

## Criterios de aceptación

1. **Dado** el escritorio (≥ 768 px), **cuando** pulso el botón de plegar la barra lateral o Ctrl+B
   (también con el foco en el cuadro de mensaje), **entonces** se pliega o se despliega, el chat
   ocupa el espacio libre, el botón dice su estado (`aria-expanded`, etiqueta "Ocultar/Mostrar
   conversaciones") y, al recargar la página, la barra sigue como la dejé. Sin `localStorage`
   disponible (modo privado, bloqueado) funciona igual, solo que no se recuerda.
2. **Dado** el móvil (< 768 px), **cuando** abro la app, **entonces** la barra lateral está cerrada,
   se abre como panel superpuesto con el botón de menú y se cierra sola al elegir una conversación,
   empezar una nueva o abrir una página de configuración. La preferencia de escritorio no la afecta.
3. **Dado** el tema claro y el oscuro, **cuando** mido los contrastes, **entonces** el texto normal
   llega a 4,5:1 y el texto grande, los iconos y los bordes de los controles a 3:1. Incluye: texto
   normal y secundario (`muted-foreground`), enlaces, placeholders, bloques de código (fondo, texto y
   resaltado), el desplegable de personalidad bloqueado y deshabilitado, los botones 👍/👎 (sin
   valorar, 👍 y 👎 activos), los avisos de error y los bordes de los campos.
4. **Dado** un contraste que no llega, **cuando** se corrige, **entonces** se hace cambiando las
   variables del tema (`index.css`, `:root` y `.dark`) y no con colores sueltos en los componentes, y
   la tabla de abajo queda con los valores medidos antes y después. Un test calcula los ratios desde
   esas variables y falla si alguno baja del mínimo.

## Decisiones

- **Tonos mates**: el fondo claro deja de ser blanco puro y el oscuro de ser casi negro (escala de
  grises algo más apagada en los dos temas), sin bajar de AA.
- **Barra plegada**: se oculta del todo; el botón para mostrarla queda en la cabecera.
- **Bloques de código**: sus colores fijos (`#0d1117`, `white/60`, ámbar y el CSS de `github-dark`)
  pasan a variables `--code-bg`, `--code-fg` y `--code-muted` en `index.css`, con el mismo valor en
  los dos temas (el bloque sigue siendo oscuro). El token de resaltado que no llega se sobrescribe
  con una variable.
- **Desplegable de personalidad deshabilitado**: el `opacity-50` viene de `components/ui/select.tsx`
  y ninguna variable lo arregla; se sobrescribe solo en `personality-select.tsx` (`className`), sin
  editar `components/ui/`.

## ADRs relacionados

- ADR-017 (PWA): no afecta; el service worker no cambia.
- ADR-024 (valoraciones): los botones 👍/👎 entran en la auditoría.
- No hace falta ADR nuevo. Sí hay que actualizar `.claude/rules/frontend.md` y `docs/security.md`,
  que dicen que el tema es lo único que se guarda en `localStorage`: se añade la preferencia de la
  barra lateral (dato de interfaz, no sensible).

## Contrastes medidos

Ratio WCAG 2.x (luminancia relativa), calculado desde las variables de `index.css` por
`frontend/src/test/theme-contrast.test.ts`, que falla en CI si alguna fila baja de su mínimo
(`CONTRAST_TABLE=1 npx vitest run src/test/theme-contrast.test.ts` imprime la tabla). "AA" = 4,5:1
texto normal, 3:1 texto grande, iconos y bordes de controles. Los colores con transparencia se miden
mezclados con su fondo real, no con el selector de color del navegador.

| Elemento | Primer plano / fondo | Claro antes | Claro después | Oscuro antes | Oscuro después | Mínimo |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Texto normal | `foreground` / `background` | 19,79 | 18,15 | 18,96 | 17,34 | 4,5 |
| Texto secundario | `muted-foreground` / `background` | 4,73 | 5,50 | 7,63 | 6,98 | 4,5 |
| Texto secundario en barra lateral | `muted-foreground` / `sidebar` | 4,53 | 5,19 | 6,91 | 6,43 | 4,5 |
| Texto secundario sobre `muted` (respuesta del asistente, fila activa) | `muted-foreground` / `muted` | **4,34** | 4,88 | 5,83 | 5,63 | 4,5 |
| Placeholder | `muted-foreground` / campo (`input`/30 en oscuro) | 4,73 | 5,50 | 7,04 | 5,21 | 4,5 |
| Enlace en una respuesta | `primary` / `muted` | 16,42 | 14,58 | 12,00 | 11,59 | 4,5 |
| Bloque de código (texto) | `code-fg` / `code-bg` | 16,02 | 16,02 | 16,02 | 16,02 | 4,5 |
| Bloque de código (etiqueta y botón copiar) | `code-muted` / `code-bg` | 7,21 | 7,78 | 7,21 | 7,78 | 4,5 |
| Bloque de código (resaltado, peor token) | token / `code-bg` | **4,08** | 6,15 | **4,08** | 6,15 | 4,5 |
| Aviso de caracteres ocultos en código | `code-warning` / `code-warning-bg` | — | 11,94 | — | 11,94 | 4,5 |
| Personalidad bloqueada | `muted-foreground` / `background` | 4,73 | 5,50 | 7,63 | 6,98 | 4,5 |
| Personalidad deshabilitada | `foreground` al 50 % → 80 % / `background` (+ `input`/30 en oscuro) | **3,71** | 10,58 | 4,97 | 9,03 | 4,5 |
| Personalidad cargando ("Personalidad", deshabilitado) | `muted-foreground` → `foreground`, al 80 % | **3,39** | 10,58 | **4,34** | 9,03 | 4,5 |
| 👍/👎 sin valorar (icono) | `foreground` / `background` | 19,79 | 18,15 | 18,96 | 17,34 | 3 |
| 👍 activo (icono) | `primary` / `background` | 17,91 | 16,42 | 15,72 | 14,38 | 3 |
| 👎 activo (icono) | `destructive` / `background` | 4,76 | 4,98 | 6,84 | 6,26 | 3 |
| Texto de error | `destructive` / `background` | 4,76 | 4,98 | 6,84 | 6,26 | 4,5 |
| Borde de campo | `input` / `background` | **1,26** | 3,21 | **1,47** | 3,23 | 3 |

En negrita, los que no llegaban. Cambios:

- Tonos mates, a petición de Void (el blanco puro y el casi negro brillaban demasiado):
  - claro: `--background` 1 → 0,97; `--card`/`--popover` 0,985; `--muted`, `--secondary`, `--accent` y
    `--sidebar-accent` 0,97 → 0,93; `--sidebar` 0,985 → 0,95; `--border` 0,922 → 0,88;
  - oscuro: `--background` 0,145 → 0,2; `--card`/`--popover` 0,205 → 0,24; `--muted`, `--secondary`,
    `--accent` y `--sidebar-accent` 0,269 → 0,28; `--sidebar` 0,205 → 0,235.
- `--muted-foreground` (claro): `oklch(0.556 0 0)` → `oklch(0.5 0 0)`.
- `--destructive` (claro): `oklch(0.577 0.245 27.325)` → `oklch(0.55 0.22 27.325)` (sobre el fondo mate
  se quedaba en 4,37).
- `--input` (claro): `oklch(0.922 0 0)` → `oklch(0.63 0 0)`; (oscuro): blanco al 15 % → 35 %. `--border` no
  cambia: los separadores son decorativos y WCAG solo pide 3:1 en los límites de los controles.
- Bloques de código: `--code-bg`, `--code-fg`, `--code-muted`, `--code-border`, `--code-warning`,
  `--code-warning-bg` (iguales en los dos temas). El encabezado de highlight.js (`.hljs-section`,
  `#1f6feb`, 4,08) pasa a `--code-heading` (`#58a6ff`, 7,49); el peor token que queda es el
  comentario (`#8b949e`, 6,15). Un test comprueba todos los colores del tema `github-dark`.
- Desplegable de personalidad deshabilitado: `disabled:opacity-80` en `personality-select.tsx`, y el
  texto "Personalidad" que muestra mientras cargan las personalidades pasa de `muted-foreground` a
  `foreground` (es la etiqueta del control, no una pista).
- Revisado y fuera de la tabla: el borde de un campo en oscuro contra su propio relleno da 2,47 (WCAG
  1.4.11 se cumple con el fondo de la página, 3,23); el borde de la personalidad bloqueada usa
  `--border` (decorativo: la información está en el texto); el placeholder del cuadro de mensaje
  deshabilitado ("Elige un modelo…") queda exento como control deshabilitado.
- Los elementos deshabilitados no tienen mínimo obligatorio en WCAG, pero se piden aquí porque el
  desplegable bloqueado o deshabilitado muestra información (la personalidad).

## Cómo probarlo a mano

1. Escritorio, tema claro: plegar y desplegar con el botón y con Ctrl+B (también escribiendo en el
   cuadro de mensaje); recargar y comprobar que se recuerda. Repetir en tema oscuro.
2. Ventana privada o almacenamiento bloqueado: la barra se pliega y despliega sin errores en consola.
3. Vista móvil (375 px): la barra empieza cerrada; abrirla con el menú; elegir una conversación,
   "Nueva conversación" y "Correcciones": se cierra sola cada vez.
4. Contrastes, en los dos temas: medir con las herramientas del navegador (selector de color o
   panel de accesibilidad) los elementos de la tabla, incluido un bloque de código con resaltado, una
   respuesta con 👍 y otra con 👎, y el desplegable de personalidad bloqueado.
5. Navegar con el teclado (Tab) por la barra lateral, la cabecera y los botones 👍/👎: el foco se ve
   en los dos temas.
