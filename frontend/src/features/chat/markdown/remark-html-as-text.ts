interface MdastNode {
  type: string;
  value?: string;
  children?: MdastNode[];
}

/**
 * Turns raw HTML in the Markdown into plain text, so `<script>` or `<img onerror>` written by
 * the model is shown literally instead of being dropped or (with rehype-raw) executed.
 */
export function remarkHtmlAsText() {
  return (tree: MdastNode) => {
    const walk = (node: MdastNode) => {
      if (node.type === 'html') node.type = 'text';
      node.children?.forEach(walk);
    };
    walk(tree);
  };
}
