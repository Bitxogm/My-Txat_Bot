/**
 * WCAG 2.x contrast ratios computed from the theme variables in index.css (oklch), so a theme
 * change that breaks AA fails in CI (spec ux-sidebar-contrast, criteria 3 and 4).
 */

export type Rgba = { r: number; g: number; b: number; a: number }; // sRGB 0..1, alpha 0..1

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x));
}

function linearToSrgb(x: number): number {
  return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;
}

function srgbToLinear(x: number): number {
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
}

/** oklch(L C H [/ A]) with L as 0..1 or %, A as 0..1 or %. Gamut-clipped to sRGB. */
export function parseOklch(value: string): Rgba {
  const m = /^oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+)(%?))?\s*\)$/.exec(
    value.trim(),
  );
  if (!m) throw new Error(`Not an oklch() color: ${value}`);
  const l = Number(m[1]) / (m[2] ? 100 : 1);
  const c = Number(m[3]);
  const h = (Number(m[4]) * Math.PI) / 180;
  const a = m[5] === undefined ? 1 : Number(m[5]) / (m[6] ? 100 : 1);
  const labA = c * Math.cos(h);
  const labB = c * Math.sin(h);
  // OKLab -> LMS' -> LMS -> linear sRGB (Björn Ottosson's reference matrices).
  const l_ = l + 0.3963377774 * labA + 0.2158037573 * labB;
  const m_ = l - 0.1055613458 * labA - 0.0638541728 * labB;
  const s_ = l - 0.0894841775 * labA - 1.291485548 * labB;
  const L = l_ ** 3;
  const M = m_ ** 3;
  const S = s_ ** 3;
  const r = 4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S;
  const g = -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S;
  const b = -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S;
  return {
    r: clamp01(linearToSrgb(r)),
    g: clamp01(linearToSrgb(g)),
    b: clamp01(linearToSrgb(b)),
    a,
  };
}

export function parseHex(value: string): Rgba {
  const hex = value.trim().replace(/^#/, '');
  const full = hex.length === 3 ? [...hex].map((c) => c + c).join('') : hex;
  if (!/^[0-9a-f]{6}$/i.test(full)) throw new Error(`Not a hex color: ${value}`);
  const n = Number.parseInt(full, 16);
  return { r: ((n >> 16) & 255) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255, a: 1 };
}

export function parseColor(value: string): Rgba {
  return value.trim().startsWith('#') ? parseHex(value) : parseOklch(value);
}

/** `top` painted over an opaque `bottom` (alpha compositing in sRGB, as browsers do). */
export function over(top: Rgba, bottom: Rgba): Rgba {
  const a = top.a;
  return {
    r: top.r * a + bottom.r * (1 - a),
    g: top.g * a + bottom.g * (1 - a),
    b: top.b * a + bottom.b * (1 - a),
    a: 1,
  };
}

export function withAlpha(color: Rgba, alpha: number): Rgba {
  return { ...color, a: color.a * alpha };
}

function luminance({ r, g, b }: Rgba): number {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

/** Contrast ratio of an opaque foreground on an opaque background (1..21). */
export function ratio(fg: Rgba, bg: Rgba): number {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Custom properties declared in a CSS block such as `:root { ... }` or `.dark { ... }`. */
export function themeVariables(css: string, selector: ':root' | '.dark'): Record<string, string> {
  const escaped = selector.replace('.', '\\.');
  const block = new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (!block) throw new Error(`No ${selector} block`);
  const vars: Record<string, string> = {};
  for (const match of block[1].matchAll(/--([\w-]+)\s*:\s*([^;]+);/g))
    vars[match[1]] = match[2].trim();
  return vars;
}
