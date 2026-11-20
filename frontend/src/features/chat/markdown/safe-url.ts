const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);

/**
 * Returns the URL only if it is absolute and uses http, https or mailto. Everything else
 * (javascript:, data:, vbscript:, file:, relative paths...) returns null. The WHATWG parser
 * strips tabs/newlines and lowercases the scheme, so "Java\tScript:" is caught too.
 */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return SAFE_PROTOCOLS.has(new URL(url).protocol) ? url : null;
  } catch {
    return null;
  }
}
