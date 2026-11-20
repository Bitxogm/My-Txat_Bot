import type { ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import 'highlight.js/styles/github-dark.min.css';
import { CodeBlock } from './code-block';
import { rehypeHighlightCode } from './rehype-highlight-code';
import { remarkHtmlAsText } from './remark-html-as-text';
import { safeUrl } from './safe-url';

interface HastNode {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/** Concatenated text of a hast node: highlighting only wraps text in spans, never changes it. */
function textOf(node: HastNode | undefined): string {
  if (!node) return '';
  if (node.type === 'text') return node.value ?? '';
  return (node.children ?? []).map(textOf).join('');
}

function languageOf(node: HastNode | undefined): string | null {
  const className = node?.properties?.className;
  const classes = Array.isArray(className) ? className.map(String) : [];
  const language = classes.find((c) => c.startsWith('language-'));
  return language ? language.slice('language-'.length) : null;
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {children}
    </a>
  );
}

const components: Components = {
  a({ href, children }) {
    const url = safeUrl(href);
    // Unsafe or relative targets keep their text but are not clickable.
    return url ? <ExternalLink href={url}>{children}</ExternalLink> : <span>{children}</span>;
  },
  img({ src, alt }) {
    // Images are never loaded (no tracking pixels, no hotlinking): shown as a link instead.
    const url = safeUrl(typeof src === 'string' ? src : null);
    const label = `Imagen: ${alt || url || 'sin descripción'}`;
    return url ? <ExternalLink href={url}>{label}</ExternalLink> : <span>{label}</span>;
  },
  pre({ node, children }) {
    const code = (node?.children as HastNode[] | undefined)?.find(
      (child) => child.type === 'element' && child.tagName === 'code',
    );
    return (
      <CodeBlock code={textOf(code).replace(/\n$/, '')} language={languageOf(code)}>
        {children}
      </CodeBlock>
    );
  },
};

/**
 * Renders model output as Markdown (GFM). Raw HTML is never interpreted: remarkHtmlAsText turns
 * it into text and there is no rehype-raw. Partial Markdown while streaming is fine: an unclosed code
 * fence simply runs to the end of the text.
 */
export function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkHtmlAsText]}
        rehypePlugins={[rehypeHighlightCode]}
        urlTransform={(url) => safeUrl(url) ?? ''}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
