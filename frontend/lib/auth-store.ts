/**
 * Auth Store — Zustand store para gestión de autenticación.
 *
 * Maneja:
 * - Estado de sesión (user, token, role)
 * - Login contra /api/v1/auth/token
 * - Logout y limpieza de localStorage
 * - Hidratación desde localStorage al iniciar
 */

import { create } from "zustand";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AuthUser {
  username: string;
  role: string;
  token: string;
}

interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    try {
      const resp = await fetch(`${API}/api/v1/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username, password }),
      });

      if (!resp.ok) {
        const detail =
          resp.status === 401
            ? "Credenciales incorrectas. Intenta nuevamente."
            : `Error del servidor (${resp.status})`;
        set({ isLoading: false, error: detail });
        return false;
      }

      const data = await resp.json();
      const user: AuthUser = {
        username: data.username,
        role: data.role,
        token: data.access_token,
      };

      localStorage.setItem("et_token", data.access_token);
      localStorage.setItem("et_user", data.username);
      localStorage.setItem("et_role", data.role);

      set({ user, isAuthenticated: true, isLoading: false, error: null });
      return true;
    } catch {
      set({
        isLoading: false,
        error: "No se puede conectar con el servidor. Verifica que el sistema esté activo.",
      });
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem("et_token");
    localStorage.removeItem("et_user");
    localStorage.removeItem("et_role");
    set({ user: null, isAuthenticated: false, error: null });
  },

  hydrate: () => {
    if (typeof window === "undefined") return;

    const token = localStorage.getItem("et_token");
    const username = localStorage.getItem("et_user");
    const role = localStorage.getItem("et_role");

    if (token && username && role) {
      set({
        user: { username, role, token },
        isAuthenticated: true,
      });
    }
  },
}));
