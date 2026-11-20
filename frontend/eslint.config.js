import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'coverage', 'src/components/ui'] },
  {
    extends: [
      js.configs.recommended,
      ...tseslint.configs.strict,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'Usa el cliente API único (src/lib/api) en lugar de fetch directo.',
        },
      ],
    },
  },
  {
    files: ['src/lib/api/**'],
    rules: { 'no-restricted-globals': 'off' },
  },
  prettier,
);
