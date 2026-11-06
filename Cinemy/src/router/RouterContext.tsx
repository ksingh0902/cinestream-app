import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

export interface RouteMatch {
  matches: boolean;
  params: Record<string, string>;
}

export interface RouterContextType {
  path: string;
  search: string;
  navigate: (to: string, options?: { replace?: boolean; scroll?: boolean }) => void;
  back: () => void;
  matchRoute: (pattern: string) => RouteMatch;
}

const RouterContext = createContext<RouterContextType | null>(null);

/**
 * Matches a URL pathname against a parameterized pattern (e.g., '/movie/:movieId').
 */
export function matchRoutePattern(pattern: string, currentPath: string): RouteMatch {
  const patternParts = pattern.split('/').filter(Boolean);
  const pathParts = currentPath.split('/').filter(Boolean);

  if (patternParts.length !== pathParts.length) {
    return { matches: false, params: {} };
  }

  const params: Record<string, string> = {};
  for (let i = 0; i < patternParts.length; i++) {
    const p = patternParts[i];
    const actual = pathParts[i];
    if (p.startsWith(':')) {
      const paramName = p.slice(1);
      params[paramName] = decodeURIComponent(actual);
    } else if (p.toLowerCase() !== actual.toLowerCase()) {
      return { matches: false, params: {} };
    }
  }

  return { matches: true, params };
}

export const RouterProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [path, setPath] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return window.location.pathname || '/';
    }
    return '/';
  });

  const [search, setSearch] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return window.location.search || '';
    }
    return '';
  });

  // Listen to browser Back/Forward (popstate)
  useEffect(() => {
    const handlePopState = () => {
      setPath(window.location.pathname || '/');
      setSearch(window.location.search || '');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback(
    (to: string, options: { replace?: boolean; scroll?: boolean } = {}) => {
      if (typeof window === 'undefined') return;

      const [targetPath, targetSearch = ''] = to.split('?');
      const normalizedPath = targetPath.startsWith('/') ? targetPath : `/${targetPath}`;
      const fullUrl = targetSearch ? `${normalizedPath}?${targetSearch}` : normalizedPath;

      if (options.replace) {
        window.history.replaceState({}, '', fullUrl);
      } else {
        window.history.pushState({}, '', fullUrl);
      }

      setPath(normalizedPath);
      setSearch(targetSearch ? `?${targetSearch}` : '');

      if (options.scroll !== false) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },
    []
  );

  const back = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.history.back();
    }
  }, []);

  const matchRoute = useCallback(
    (pattern: string) => matchRoutePattern(pattern, path),
    [path]
  );

  return (
    <RouterContext.Provider value={{ path, search, navigate, back, matchRoute }}>
      {children}
    </RouterContext.Provider>
  );
};

export function useRouter(): RouterContextType {
  const ctx = useContext(RouterContext);
  if (!ctx) {
    throw new Error('useRouter must be used within a RouterProvider');
  }
  return ctx;
}

