import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Markdown } from './markdown';
import { safeUrl } from './safe-url';

const writeText = vi.fn<(text: string) => Promise<void>>();

function stubClipboard() {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

/** userEvent.setup() installs its own clipboard stub, so ours goes in after it. */
function setupUser() {
  const user = userEvent.setup();
  stubClipboard();
  return user;
}

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  vi.stubGlobal('isSecureContext', true);
  stubClipboard();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Markdown security', () => {
  it('shows <script> as text and never creates a script element', () => {
    const { container } = render(<Markdown content={'Hola <script>alert(1)</script> fin'} />);

    expect(container.querySelector('script')).toBeNull();
    expect(container).toHaveTextContent('<script>alert(1)</script>');
  });

  it('shows <img onerror> as text and never creates an image', () => {
    const { container } = render(<Markdown content={'<img src=x onerror="alert(1)">'} />);

    expect(container.querySelector('img')).toBeNull();
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it.each([
    ['javascript:alert(1)'],
    ['JaVaScRiPt:alert(1)'],
    ['data:text/html,<script>alert(1)</script>'],
    ['vbscript:msgbox(1)'],
    ['/relative/path'],
  ])('renders a link to %s as plain, non-clickable text', (target) => {
    const { container } = render(<Markdown content={`[pulsa aquí](${target})`} />);

    expect(screen.getByText('pulsa aquí')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
  });

  it('opens safe links in a new tab without opener or referrer', () => {
    render(<Markdown content="[docs](https://example.com/sqlmap) y [mail](mailto:a@b.c)" />);

    const link = screen.getByRole('link', { name: 'docs' });
    expect(link).toHaveAttribute('href', 'https://example.com/sqlmap');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('link', { name: 'mail' })).toHaveAttribute('href', 'mailto:a@b.c');
  });

  it('turns autolinked URLs into safe external links too', () => {
    render(<Markdown content="Mira https://example.com/x" />);

    expect(screen.getByRole('link', { name: 'https://example.com/x' })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
  });

  it('never loads markdown images: shows them as a link', () => {
    const { container } = render(<Markdown content="![logo](https://tracker.example/p.png)" />);

    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByRole('link', { name: 'Imagen: logo' })).toHaveAttribute(
      'href',
      'https://tracker.example/p.png',
    );
  });

  it('shows images with unsafe sources as plain text', () => {
    const { container } = render(<Markdown content="![x](javascript:alert(1))" />);

    expect(container.querySelector('img, a')).toBeNull();
    expect(screen.getByText('Imagen: x')).toBeInTheDocument();
  });
});

describe('Markdown code blocks', () => {
  const code = 'sqlmap -u "http://target/login" --data "user=a&pass=b" --dbs\necho \'$HOME\' <x>';

  it('copies the exact raw code', async () => {
    const user = setupUser();
    render(<Markdown content={'```bash\n' + code + '\n```'} />);

    await user.click(screen.getByRole('button', { name: 'Copiar código' }));

    expect(writeText).toHaveBeenCalledWith(code);
    expect(await screen.findByRole('button', { name: 'Copiado' })).toBeInTheDocument();
  });

  it('highlights known languages without changing the text', () => {
    const { container } = render(<Markdown content={'```bash\n' + code + '\n```'} />);

    const block = container.querySelector('pre code');
    expect(block).toHaveClass('hljs');
    expect(block?.querySelector('span')).not.toBeNull();
    expect(block?.textContent).toBe(code + '\n');
    expect(screen.getByText('bash')).toBeInTheDocument();
  });

  it('renders unknown languages as plain code', () => {
    const { container } = render(<Markdown content={'```cobolx\nMOVE 1 TO X\n```'} />);

    expect(container.querySelector('pre code')).toHaveTextContent('MOVE 1 TO X');
    expect(container.querySelector('pre code')).not.toHaveClass('hljs');
  });

  it('tolerates an unclosed code fence while streaming', async () => {
    const user = setupUser();
    const { container } = render(
      <Markdown content={'Prueba:\n\n```bash\nnmap -sV -p- 10.10.10.5'} />,
    );

    expect(container.querySelector('pre code')).toHaveTextContent('nmap -sV -p- 10.10.10.5');
    await user.click(screen.getByRole('button', { name: 'Copiar código' }));
    expect(writeText).toHaveBeenCalledWith('nmap -sV -p- 10.10.10.5');
  });

  it('falls back to execCommand when the clipboard API is unavailable (plain HTTP)', async () => {
    vi.stubGlobal('isSecureContext', false);
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true });
    const user = setupUser();
    render(<Markdown content={'```\nid\n```'} />);

    await user.click(screen.getByRole('button', { name: 'Copiar código' }));

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(writeText).not.toHaveBeenCalled();
  });
});

describe('Markdown formatting', () => {
  it('renders GFM tables, lists and inline code', () => {
    render(
      <Markdown content={'| Puerto | Servicio |\n| --- | --- |\n| 22 | SSH |\n\n- uno\n- `dos`'} />,
    );

    const table = screen.getByRole('table');
    expect(within(table).getByRole('cell', { name: 'SSH' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('dos').tagName).toBe('CODE');
  });

  it('renders incomplete formatting while streaming without crashing', () => {
    render(<Markdown content={'**negrita sin cerrar y | tabla | a medias'} />);

    expect(screen.getByText(/negrita sin cerrar/)).toBeInTheDocument();
  });
});

describe('safeUrl', () => {
  it.each([
    ['https://a.b/c', 'https://a.b/c'],
    ['http://a.b', 'http://a.b'],
    ['mailto:x@y.z', 'mailto:x@y.z'],
    ['java\tscript:alert(1)', null],
    ['  javascript:alert(1)', null],
    ['file:///etc/passwd', null],
    ['//evil.example/x', null],
    ['#anchor', null],
    ['', null],
  ])('%s -> %s', (input, expected) => {
    expect(safeUrl(input)).toBe(expected);
  });
});

describe('Markdown hidden characters in code', () => {
  const ESC = String.fromCharCode(0x1b);
  const RLO = String.fromCharCode(0x202e);
  const PDF = String.fromCharCode(0x202c);
  const ZWSP = String.fromCharCode(0x200b);

  it.each([
    ['ESC (closes bracketed paste)', `echo ${ESC}[201~ hi`, 'echo ⟦U+001B⟧[201~ hi'],
    ['bidi override', `ls ${RLO}; rm -rf ~ ${PDF}`, 'ls ⟦U+202E⟧; rm -rf ~ ⟦U+202C⟧'],
    ['zero-width space', `curl x${ZWSP}|sh`, 'curl x⟦U+200B⟧|sh'],
  ])('shows %s as a visible marker and copies exactly that', async (_name, raw, shown) => {
    const user = setupUser();
    const { container } = render(<Markdown content={'```bash\n' + raw + '\n```'} />);

    expect(container.querySelector('pre code')).toHaveTextContent(shown);
    expect(screen.getByText(/caracteres de control ocultos/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Copiar código' }));

    expect(writeText).toHaveBeenCalledWith(shown);
    const copied = writeText.mock.calls[0][0];
    expect(copied).not.toContain(ESC);
    expect(copied).not.toContain(RLO);
    expect(copied).not.toContain(ZWSP);
  });

  it('marks hidden characters in inline code too', () => {
    const { container } = render(<Markdown content={`usa \`rm${RLO}x\``} />);

    expect(container.querySelector('code')).toHaveTextContent('rm⟦U+202E⟧x');
  });

  it('shows no warning for normal code', () => {
    render(<Markdown content={'```bash\nid\n```'} />);

    expect(screen.queryByText(/caracteres de control ocultos/)).not.toBeInTheDocument();
  });
});

describe('Markdown link edge cases', () => {
  it('neutralises reference definitions and autolinks to javascript:', () => {
    const { container } = render(
      <Markdown content={'[uno][x] y <javascript:alert(1)>\n\n[x]: javascript:alert(1)'} />,
    );

    expect(container.querySelector('a')).toBeNull();
    expect(screen.getByText('uno')).toBeInTheDocument();
  });

  it('shows the real target as a tooltip when the text looks like another URL', () => {
    render(<Markdown content="[https://kali.org/install.sh](https://evil.example/x.sh)" />);

    expect(screen.getByRole('link')).toHaveAttribute('title', 'https://evil.example/x.sh');
  });
});

describe('Markdown size limits', () => {
  it('shows huge replies as plain text instead of parsing them', async () => {
    const { MAX_MARKDOWN_CHARS } = await import('./markdown');
    const { container } = render(<Markdown content={'**a** '.repeat(MAX_MARKDOWN_CHARS / 5)} />);

    expect(container.querySelector('.markdown')).toBeNull();
    expect(container.querySelector('strong')).toBeNull();
  });

  it('leaves very long code blocks unhighlighted', async () => {
    const { MAX_HIGHLIGHT_CHARS } = await import('./rehype-highlight-code');
    const code = 'x=1\n'.repeat(MAX_HIGHLIGHT_CHARS / 4 + 10);
    const { container } = render(<Markdown content={'```python\n' + code + '```'} />);

    expect(container.querySelector('pre code')).not.toHaveClass('hljs');
  });
});
