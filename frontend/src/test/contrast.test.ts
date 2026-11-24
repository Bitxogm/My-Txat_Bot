import { describe, expect, it } from 'vitest';
import {
  over,
  parseColor,
  parseHex,
  parseOklch,
  ratio,
  themeVariables,
  withAlpha,
} from './contrast';

describe('contrast helper', () => {
  it('matches the WCAG reference values', () => {
    expect(ratio(parseHex('#000'), parseHex('#fff'))).toBeCloseTo(21, 5);
    expect(ratio(parseHex('#767676'), parseHex('#fff'))).toBeCloseTo(4.54, 2);
    expect(ratio(parseHex('#777'), parseHex('#fff'))).toBeLessThan(4.5);
  });

  it('converts oklch to the same sRGB as the browser', () => {
    const white = parseOklch('oklch(1 0 0)');
    const black = parseOklch('oklch(0 0 0)');
    for (const channel of ['r', 'g', 'b'] as const) {
      expect(white[channel]).toBeCloseTo(1, 6);
      expect(black[channel]).toBeCloseTo(0, 6);
    }
    // oklch(0.628 0.2577 29.23) is #ff0000.
    const red = parseOklch('oklch(0.628 0.2577 29.23)');
    expect(red.r).toBeCloseTo(1, 2);
    expect(red.g).toBeCloseTo(0, 2);
    expect(red.b).toBeCloseTo(0, 2);
    expect(parseOklch('oklch(1 0 0 / 15%)').a).toBeCloseTo(0.15);
  });

  it('blends a translucent color over its background', () => {
    const half = over(withAlpha(parseColor('#ffffff'), 0.5), parseColor('#000000'));
    expect(half.r).toBeCloseTo(0.5);
  });

  it('reads the variables of a theme block', () => {
    const css = ':root {\n  --a: oklch(1 0 0);\n}\n\n.dark {\n  --a: oklch(0 0 0 / 10%);\n}';
    expect(themeVariables(css, ':root')).toEqual({ a: 'oklch(1 0 0)' });
    expect(themeVariables(css, '.dark')).toEqual({ a: 'oklch(0 0 0 / 10%)' });
  });
});
