import React from 'react';

export type V2Theme = 'dark' | 'light';

const STORAGE_KEY = 'aiops-v2-theme';

export const useV2Theme = (): { theme: V2Theme; toggle: () => void } => {
  const [theme, setTheme] = React.useState<V2Theme>(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  });

  const toggle = React.useCallback(() => {
    setTheme((current) => {
      const next: V2Theme = current === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // localStorage를 못 쓰는 환경에서는 세션 내 상태만 유지
      }
      return next;
    });
  }, []);

  return { theme, toggle };
};
