import { useLayoutEffect, useState } from 'react';

type Theme = 'system' | 'light' | 'dark';
const THEME_KEY = 'margono-theme';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      // Storage can be disabled by the browser.
    }
    return 'system';
  });

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // The current tab still applies the theme.
    }
  }, [theme]);

  return { theme, setTheme };
}

const timestampFormat = new Intl.DateTimeFormat('id-ID', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
});

export function formatTimestamp(value: string) {
  return `${timestampFormat.format(new Date(value))} UTC`;
}

export function selectionUrl(parameter: 'case' | 'saved', id?: string): URL {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(parameter, id);
  else url.searchParams.delete(parameter);
  return url;
}

export function rememberSelection(parameter: 'case' | 'saved', id?: string) {
  const url = selectionUrl(parameter, id);
  if (url.href !== window.location.href) window.history.pushState(null, '', url);
}
