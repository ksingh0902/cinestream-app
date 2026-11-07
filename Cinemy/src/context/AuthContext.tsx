import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { AuthState, UserRole } from '../types/auth';
import { checkAuth, performLogout } from '../api/auth';
import { ApiError } from '../api/types';

interface AuthContextType extends AuthState {
  refreshAuth: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    authenticated: false,
    username: null,
    role: null,
    loading: true,
    error: null,
    isStorageOutage: false,
  });

  const isCheckingRef = useRef(false);
  const mountedRef = useRef(true);

  const verifySession = useCallback(async (isInitial = false) => {
    // Prevent overlapping concurrent polling requests
    if (isCheckingRef.current) return;
    isCheckingRef.current = true;

    if (isInitial) {
      setState((prev) => ({ ...prev, loading: true }));
    }

    try {
      const data = await checkAuth();
      if (!mountedRef.current) return;

      if (data.authenticated) {
        const userRole: UserRole = data.role === 'admin' ? 'admin' : 'viewer';
        setState({
          authenticated: true,
          username: data.username,
          role: userRole,
          loading: false,
          error: null,
          isStorageOutage: false,
        });
      } else {
        const isOutage = data.error === 'storage_unavailable';
        setState({
          authenticated: false,
          username: null,
          role: null,
          loading: false,
          error: isOutage ? 'Authentication storage is temporarily unavailable.' : null,
          isStorageOutage: isOutage,
        });
      }
    } catch (err) {
      if (!mountedRef.current) return;

      if (err instanceof ApiError) {
        const isOutage = err.status === 503 || err.detail === 'storage_unavailable';
        setState((prev) => ({
          ...prev,
          loading: false,
          error: isOutage ? 'Authentication storage is temporarily unavailable. Retrying...' : err.message,
          isStorageOutage: isOutage,
        }));
      } else {
        setState((prev) => ({
          ...prev,
          loading: false,
          error: 'Connection error during authentication verification.',
          isStorageOutage: false,
        }));
      }
    } finally {
      isCheckingRef.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    verifySession(true);

    // Poll session state every 60 seconds (matches existing Vanilla interval)
    const intervalId = setInterval(() => {
      verifySession(false);
    }, 60000);

    return () => {
      mountedRef.current = false;
      clearInterval(intervalId);
    };
  }, [verifySession]);

  const logout = useCallback(() => {
    performLogout();
  }, []);

  const value: AuthContextType = {
    ...state,
    refreshAuth: () => verifySession(false),
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
