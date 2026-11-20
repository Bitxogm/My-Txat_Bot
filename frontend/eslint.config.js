// Las dependencias (eslint, typescript-eslint, plugins) se instalan en Fase 1 con el scaffold de Vite.
// Al instalarlas, ajustar la config de react-hooks a la versión fijada (v6+ usa configs.flat.recommended).
import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'src/components/ui'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Usa el cliente API único (src/lib/api) en lugar de fetch directo.' },
      ],
    },
  },
  {
    files: ['src/lib/api/**'],
    rules: { 'no-restricted-globals': 'off' },
  },
  prettier,
);
