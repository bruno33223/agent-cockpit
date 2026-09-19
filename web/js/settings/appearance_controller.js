/**
 * Appearance Controller
 * Gerenciamento de temas visuais, tipografia reativa e tokens de interface.
 */

export function initThemeAndFontSettings() {
  const savedTheme = localStorage.getItem('ag_theme') || 'dark';
  const savedScale = localStorage.getItem('ag_font_scale') || '1';

  document.documentElement.setAttribute('data-theme', savedTheme);
  document.documentElement.style.setProperty('--app-font-scale', savedScale);

  const themeSelect = document.getElementById('ag-theme-select');
  if (themeSelect) {
    themeSelect.value = savedTheme;
    themeSelect.addEventListener('change', () => {
      const selected = themeSelect.value;
      setTheme(selected);
    });
  }

  const fontSelect = document.getElementById('ag-font-size-select');
  if (fontSelect) {
    fontSelect.value = savedScale;
    fontSelect.addEventListener('change', () => {
      const selected = fontSelect.value;
      setFontScale(selected);
    });
  }
}

export function setTheme(themeName) {
  if (!themeName) return;
  document.documentElement.setAttribute('data-theme', themeName);
  localStorage.setItem('ag_theme', themeName);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme: themeName } }));
  }
}

export function setFontScale(scaleValue) {
  if (!scaleValue) return;
  document.documentElement.style.setProperty('--app-font-scale', scaleValue);
  localStorage.setItem('ag_font_scale', scaleValue);
}

export function getCurrentTheme() {
  return localStorage.getItem('ag_theme') || document.documentElement.getAttribute('data-theme') || 'dark';
}

export function getCurrentFontScale() {
  return localStorage.getItem('ag_font_scale') || '1';
}
