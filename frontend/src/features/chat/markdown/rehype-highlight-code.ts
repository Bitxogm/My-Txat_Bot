import { createLowlight } from 'lowlight';
import { HIGHLIGHT_ALIASES, HIGHLIGHT_LANGUAGES } from './languages';

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/** Longer blocks stay as plain code: highlighting cost grows with size. */
export const MAX_HIGHLIGHT_CHARS = 20_000;

const lowlight = createLowlight(HIGHLIGHT_LANGUAGES);
lowlight.registerAlias(HIGHLIGHT_ALIASES);

function textOf(node: HastNode): string {
  if (node.type === 'text') return node.value ?? '';
  return (node.children ?? []).map(textOf).join('');
}

function languageOf(node: HastNode): string | null {
  const className = node.properties?.className;
  const classes = Array.isArray(className) ? className.map(String) : [];
  const language = classes.find((c) => c.startsWith('language-'));
  return language ? language.slice('language-'.length).toLowerCase() : null;
}

/**
 * Highlights fenced code blocks whose language is in HIGHLIGHT_LANGUAGES (no auto-detection).
 * Used instead of rehype-highlight, which always bundles highlight.js "common" (~37 languages).
 * Highlighting only wraps the text in spans, so the code text is unchanged.
 */
export function rehypeHighlightCode() {
  return (tree: HastNode) => {
    const walk = (node: HastNode, parent: HastNode | null) => {
      if (node.type === 'element' && node.tagName === 'code' && parent?.tagName === 'pre') {
        const language = languageOf(node);
        const text = textOf(node);
        if (language && lowlight.registered(language) && text.length <= MAX_HIGHLIGHT_CHARS) {
          const result = lowlight.highlight(language, text);
          node.children = result.children as HastNode[];
          const className = node.properties?.className;
          node.properties = {
            ...node.properties,
            className: [...(Array.isArray(className) ? className : []), 'hljs'],
          };
        }
        return;
      }
      node.children?.forEach((child) => walk(child, node));
    };
    walk(tree, null);
  };
}
