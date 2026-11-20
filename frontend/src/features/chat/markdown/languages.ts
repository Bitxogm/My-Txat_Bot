import bash from 'highlight.js/lib/languages/bash';
import c from 'highlight.js/lib/languages/c';
import diff from 'highlight.js/lib/languages/diff';
import dockerfile from 'highlight.js/lib/languages/dockerfile';
import go from 'highlight.js/lib/languages/go';
import http from 'highlight.js/lib/languages/http';
import ini from 'highlight.js/lib/languages/ini';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import nginx from 'highlight.js/lib/languages/nginx';
import php from 'highlight.js/lib/languages/php';
import plaintext from 'highlight.js/lib/languages/plaintext';
import powershell from 'highlight.js/lib/languages/powershell';
import python from 'highlight.js/lib/languages/python';
import ruby from 'highlight.js/lib/languages/ruby';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';

/**
 * Languages highlighted in code blocks: the usual ones in labs/CTF and in this stack. Keeping the
 * list short keeps the bundle small (all of highlight.js "common" roughly doubled it). Unknown
 * languages render as plain code.
 */
export const HIGHLIGHT_LANGUAGES = {
  bash,
  c,
  diff,
  dockerfile,
  go,
  http,
  ini,
  javascript,
  json,
  nginx,
  php,
  plaintext,
  powershell,
  python,
  ruby,
  sql,
  typescript,
  xml,
  yaml,
};

/** Common names models use for the same languages. */
export const HIGHLIGHT_ALIASES = {
  bash: ['sh', 'shell', 'zsh', 'console'],
  powershell: ['ps1', 'pwsh'],
  python: ['py'],
  javascript: ['js'],
  typescript: ['ts'],
  xml: ['html'],
  yaml: ['yml'],
  plaintext: ['text', 'txt'],
};
