/**
 * Every pairing of the spec's contrast table (docs/specs/ux-sidebar-contrast.md) meets WCAG AA in
 * both themes. Colors come from the theme variables in index.css, blended with their real
 * background when they are translucent.
 */
/// <reference types="node" />
// CSS is read from disk (paths relative to frontend/, where Vitest runs): with `css: false`
// Vitest hands even `?raw` CSS imports over empty.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';
import { over, parseColor, ratio, themeVariables, withAlpha, type Rgba } from './contrast';

const css = readFileSync('src/index.css', 'utf8');
const highlightCss = readFileSync(
  createRequire(`${process.cwd()}/`).resolve('highlight.js/styles/github-dark.min.css'),
  'utf8',
);

type Theme = 'claro' | 'oscuro';

// Every token color of highlight.js's theme; the ones index.css overrides take a variable instead.
const OVERRIDDEN_TOKENS = new Set(['#1f6feb']);
const TOKEN_COLORS = [...highlightCss.matchAll(/(?<![-\w])color:\s*(#[0-9a-f]{3,6})/gi)].map((m) =>
  m[1].toLowerCase(),
);

interface Row {
  name: string;
  /** Foreground and background, already composited. */
  colors: (v: (name: string) => Rgba, theme: Theme) => [Rgba, Rgba];
  min: number;
}

// Opacity of the personality select when disabled (personality-select.tsx overrides the 50% of
// components/ui/select.tsx).
const DISABLED_SELECT_OPACITY = 0.8;

const ROWS: Row[] = [
  { name: 'Texto normal', colors: (v) => [v('foreground'), v('background')], min: 4.5 },
  { name: 'Texto secundario', colors: (v) => [v('muted-foreground'), v('background')], min: 4.5 },
  {
    name: 'Texto secundario en barra lateral',
    colors: (v) => [v('muted-foreground'), v('sidebar')],
    min: 4.5,
  },
  {
    name: 'Texto secundario sobre muted (respuesta, fila activa)',
    colors: (v) => [v('muted-foreground'), v('muted')],
    min: 4.5,
  },
  {
    // Fields are transparent on light and input/30 on dark (components/ui/textarea, input).
    name: 'Placeholder',
    colors: (v, theme) => [
      v('muted-foreground'),
      theme === 'oscuro' ? over(withAlpha(v('input'), 0.3), v('background')) : v('background'),
    ],
    min: 4.5,
  },
  {
    name: 'Enlace en una respuesta',
    colors: (v) => [v('primary'), v('muted')],
    min: 4.5,
  },
  { name: 'Bloque de código (texto)', colors: (v) => [v('code-fg'), v('code-bg')], min: 4.5 },
  {
    name: 'Bloque de código (etiqueta y botón)',
    colors: (v) => [v('code-muted'), v('code-bg')],
    min: 4.5,
  },
  {
    name: 'Bloque de código (resaltado, peor token)',
    colors: (v) => {
      const bg = v('code-bg');
      const tokens = [
        ...TOKEN_COLORS.filter((hex) => !OVERRIDDEN_TOKENS.has(hex)).map(parseColor),
        v('code-heading'),
      ];
      const worst = tokens.reduce((a, b) => (ratio(a, bg) <= ratio(b, bg) ? a : b));
      return [worst, bg];
    },
    min: 4.5,
  },
  {
    name: 'Aviso de caracteres ocultos en código',
    colors: (v) => [v('code-warning'), over(v('code-warning-bg'), v('code-bg'))],
    min: 4.5,
  },
  {
    name: 'Personalidad bloqueada',
    colors: (v) => [v('muted-foreground'), v('background')],
    min: 4.5,
  },
  {
    // The whole trigger fades, its own background (input/30 on dark) included.
    name: 'Personalidad deshabilitada',
    colors: (v, theme) => [
      over(withAlpha(v('foreground'), DISABLED_SELECT_OPACITY), v('background')),
      theme === 'oscuro'
        ? over(withAlpha(v('input'), 0.3 * DISABLED_SELECT_OPACITY), v('background'))
        : v('background'),
    ],
    min: 4.5,
  },
  { name: '👍/👎 sin valorar (icono)', colors: (v) => [v('foreground'), v('background')], min: 3 },
  { name: '👍 activo (icono)', colors: (v) => [v('primary'), v('background')], min: 3 },
  { name: '👎 activo (icono)', colors: (v) => [v('destructive'), v('background')], min: 3 },
  { name: 'Texto de error', colors: (v) => [v('destructive'), v('background')], min: 4.5 },
  {
    name: 'Borde de campo',
    colors: (v) => [over(v('input'), v('background')), v('background')],
    min: 3,
  },
];

const THEMES: [Theme, ':root' | '.dark'][] = [
  ['claro', ':root'],
  ['oscuro', '.dark'],
];

function lookup(theme: ':root' | '.dark') {
  const light = themeVariables(css, ':root');
  const vars = theme === ':root' ? light : { ...light, ...themeVariables(css, '.dark') };
  return (name: string): Rgba => {
    const value = vars[name];
    if (!value) throw new Error(`Missing --${name} in ${theme}`);
    return parseColor(value);
  };
}

describe('theme contrast (WCAG AA)', () => {
  // CONTRAST_TABLE=1 npx vitest run src/test/theme-contrast.test.ts prints the table of the spec.
  if (process.env.CONTRAST_TABLE) {
    it('prints the measured table', () => {
      const [light, dark] = THEMES.map(([theme, selector]) => {
        const v = lookup(selector);
        return ROWS.map((row) =>
          ratio(...row.colors(v, theme))
            .toFixed(2)
            .replace('.', ','),
        );
      });
      const lines = ROWS.map((row, i) => `| ${row.name} | ${light[i]} | ${dark[i]} | ${row.min} |`);
      console.log(['| Elemento | Claro | Oscuro | Mínimo |', ...lines].join('\n'));
    });
  }

  for (const [theme, selector] of THEMES) {
    const v = lookup(selector);
    it.each(ROWS.map((row) => [row.name, row] as const))(`${theme}: %s`, (_name, row) => {
      const [fg, bg] = row.colors(v, theme);
      expect(ratio(fg, bg)).toBeGreaterThanOrEqual(row.min);
    });
  }

  it('reads the token colors of the highlight.js theme', () => {
    expect(TOKEN_COLORS.length).toBeGreaterThan(5);
    expect(TOKEN_COLORS).toContain('#1f6feb');
  });
});
