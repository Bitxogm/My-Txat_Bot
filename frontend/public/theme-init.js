// Applies the saved light/dark theme before React renders, so the page never flashes the wrong
// colors. An external file because the CSP (script-src 'self') blocks inline scripts.
// Keep the storage key and logic in sync with src/lib/theme.ts.
(function () {
  var saved = null;
  try {
    saved = window.localStorage.getItem('txat-theme');
  } catch (e) {
    saved = null;
  }
  var dark =
    saved === 'dark' ||
    (saved !== 'light' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
})();
