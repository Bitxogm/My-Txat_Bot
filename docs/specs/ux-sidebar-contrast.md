# Spec: barra lateral colapsable y contrastes WCAG AA

Estado: borrador

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

Se rellena en la PR de contrastes. Ratio WCAG 2.x (relación de luminancia relativa); "AA" = 4,5:1
texto normal, 3:1 texto grande, iconos y bordes de controles.

| Elemento | Primer plano / fondo | Claro antes | Claro después | Oscuro antes | Oscuro después | Mínimo |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Texto normal | `foreground` / `background` | | | | | 4,5 |
| Texto secundario | `muted-foreground` / `background` | | | | | 4,5 |
| Texto secundario en barra lateral | `muted-foreground` / `sidebar` | | | | | 4,5 |
| Texto secundario en fila activa o al pasar el ratón | `muted-foreground` / `muted` | | | | | 4,5 |
| Placeholder | `muted-foreground` / `input` | | | | | 4,5 |
| Enlace | | | | | | 4,5 |
| Bloque de código (texto) | `code-fg` / `code-bg` | | | | | 4,5 |
| Bloque de código (etiqueta y comentarios) | `code-muted` / `code-bg` | | | | | 4,5 |
| Bloque de código (resaltado, peor token) | token / `code-bg` | | | | | 4,5 |
| Personalidad bloqueada | `muted-foreground` / `background` | | | | | 4,5 |
| Personalidad deshabilitada | | | | | | 4,5 |
| 👍/👎 sin valorar (icono) | | | | | | 3 |
| 👍 activo (icono) | `primary` / `background` | | | | | 3 |
| 👎 activo (icono) | `destructive` / `background` | | | | | 3 |
| Texto de error | `destructive` / `background` | | | | | 4,5 |
| Borde de campo | `input`/`border` / `background` | | | | | 3 |

Los colores con transparencia se miden mezclados con su fondo real, no con el selector de color del
navegador. Los elementos deshabilitados no tienen mínimo obligatorio en WCAG, pero se piden aquí porque el
desplegable bloqueado muestra información (la personalidad fijada).

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
