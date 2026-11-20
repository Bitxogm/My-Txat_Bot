/**
 * Invisible or terminal-relevant characters: C0 controls except tab/newline (ESC can close
 * bracketed paste and run what follows), DEL and C1 controls, zero-width characters and bidi
 * controls (they make a command look different from what is copied).
 */
// Code point ranges, built at runtime so the source has no invisible characters in it.
const HIDDEN_RANGES: [number, number][] = [
  [0x00, 0x08],
  [0x0b, 0x1f],
  [0x7f, 0x9f],
  [0x200b, 0x200f],
  [0x202a, 0x202e],
  [0x2060, 0x2064],
  [0x2066, 0x2069],
  [0xfeff, 0xfeff],
];
const hex = (n: number) => `\\u${n.toString(16).padStart(4, '0')}`;
const HIDDEN = new RegExp(
  `[${HIDDEN_RANGES.map(([from, to]) => (from === to ? hex(from) : `${hex(from)}-${hex(to)}`)).join('')}]`,
  'g',
);

export const HIDDEN_MARKER = '⟦U+';

function marker(char: string): string {
  const code = char.codePointAt(0) ?? 0;
  return `${HIDDEN_MARKER}${code.toString(16).toUpperCase().padStart(4, '0')}⟧`;
}

/** Replaces each hidden character with a visible marker such as ⟦U+202E⟧. */
export function revealHidden(text: string): string {
  return text.replace(HIDDEN, marker);
}

/** Removes hidden characters (last line of defence before writing to the clipboard). */
export function stripHidden(text: string): string {
  return text.replace(HIDDEN, '');
}

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  children?: HastNode[];
}

/**
 * Makes hidden characters visible inside code (inline and blocks), so what you see is exactly
 * what the copy button copies. Runs before highlighting.
 */
export function rehypeRevealHiddenChars() {
  return (tree: HastNode) => {
    const walk = (node: HastNode, inCode: boolean) => {
      if (node.type === 'text' && inCode && node.value) {
        node.value = revealHidden(node.value);
        return;
      }
      const code = inCode || (node.type === 'element' && node.tagName === 'code');
      node.children?.forEach((child) => walk(child, code));
    };
    walk(tree, false);
  };
}
