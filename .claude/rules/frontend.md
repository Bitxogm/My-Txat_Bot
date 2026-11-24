---
paths:
  - "frontend/**"
---

# Reglas frontend

- Vite + React SPA. No hay Next.js, ni SSR, ni server components.
- Toda llamada HTTP pasa por `src/lib/api`. `fetch` directo fuera de ahí está bloqueado por ESLint.
- Errores: el cliente API devuelve errores tipados; la UI los muestra con Sonner (`toast.error`) incluyendo el `request_id` en los 5xx.
- Componentes base con shadcn/ui (`npx shadcn add ...`). No editar `src/components/ui/` salvo necesidad clara.
- Colores solo con variables del tema (`src/index.css`, `:root` y `.dark`, también `--code-*` para los bloques de código), nunca colores sueltos en componentes. `src/test/theme-contrast.test.ts` comprueba WCAG AA en los dos temas: un elemento nuevo con una combinación de colores nueva lleva su fila ahí y en la spec `ux-sidebar-contrast`.
- Sin `any`. Nada de tokens ni datos sensibles en `localStorage`/`sessionStorage`; la sesión va en cookie httpOnly.
- Antes de dar algo por terminado: `npm run lint && npm run format:check && npx tsc -b && npm run test -- --run`.
- TypeScript fijado en `~6.0`: typescript-eslint aún no soporta TS 7 (peer `<6.1`). No subirlo hasta que lo soporte.
- Type-check con `npx tsc -b` (el `tsconfig.json` raíz solo tiene referencias; `tsc --noEmit` sobre él no comprueba nada).
- PWA (`src/pwa/options.ts`, ADR-017): nunca añadir `runtimeCaching` ni nada que haga pasar `/api` por el service worker, y mantener `navigateFallbackDenylist: [/^\/api\//]`; si no, `/auth/me`, el chat o los adjuntos podrían servirse desde caché tras el logout. Lo comprueba `src/pwa/options.test.ts`. El panel del navegador integrado no admite service workers: probar con un Chromium real.
- `localStorage` solo guarda preferencias visuales: `txat-theme` (tema) y `txat-sidebar` (barra lateral plegada, `src/lib/sidebar.ts`), siempre con `try/catch` y funcionando sin almacenamiento.
- Tema día/noche: la clave `txat-theme` es solo una preferencia visual. La lógica está duplicada en `public/theme-init.js` (se ejecuta antes de React para evitar el parpadeo; la CSP no permite scripts inline) y `src/lib/theme.ts`: cambiar las dos a la vez.
