---
paths:
  - "frontend/**"
---

# Reglas frontend

- Vite + React SPA. No hay Next.js, ni SSR, ni server components.
- Toda llamada HTTP pasa por `src/lib/api`. `fetch` directo fuera de ahí está bloqueado por ESLint.
- Errores: el cliente API devuelve errores tipados; la UI los muestra con Sonner (`toast.error`) incluyendo el `request_id` en los 5xx.
- Componentes base con shadcn/ui (`npx shadcn add ...`). No editar `src/components/ui/` salvo necesidad clara.
- Sin `any`. Nada de tokens ni datos sensibles en `localStorage`/`sessionStorage`; la sesión va en cookie httpOnly.
- Antes de dar algo por terminado: `npm run lint && npm run format:check && npx tsc -b && npm run test -- --run`.
- TypeScript fijado en `~6.0`: typescript-eslint aún no soporta TS 7 (peer `<6.1`). No subirlo hasta que lo soporte.
- Type-check con `npx tsc -b` (el `tsconfig.json` raíz solo tiene referencias; `tsc --noEmit` sobre él no comprueba nada).
- Si se añade vite-plugin-pwa: excluir `/api/*` de cualquier caché de Workbox (`navigateFallbackDenylist: [/^\/api\//]`, nada de `runtimeCaching` sobre `/api`), o `/auth/me` y el chat podrían servirse desde caché tras el logout.
