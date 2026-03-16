"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
} from "react";
import { useRouter } from "next/navigation";
import { api, loginRequest } from "@/lib/api";
import { clearToken, getToken, setToken } from "@/lib/auth";
import type { User } from "@/lib/types";

// ── State ──────────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  isLoading: boolean;
}

type AuthAction =
  | { type: "SET_USER"; user: User }
  | { type: "CLEAR_USER" }
  | { type: "SET_LOADING"; loading: boolean };

function reducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "SET_USER":
      return { user: action.user, isLoading: false };
    case "CLEAR_USER":
      return { user: null, isLoading: false };
    case "SET_LOADING":
      return { ...state, isLoading: action.loading };
  }
}

// ── Context ────────────────────────────────────────────────────────────────

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, dispatch] = useReducer(reducer, {
    user: null,
    isLoading: true,
  });

  // On mount: hydrate user from token if present
  useEffect(() => {
    const token = getToken();
    if (!token) {
      dispatch({ type: "CLEAR_USER" });
      return;
    }
    api
      .get<User>("/api/auth/me")
      .then((user) => dispatch({ type: "SET_USER", user }))
      .catch(() => {
        clearToken();
        dispatch({ type: "CLEAR_USER" });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await loginRequest(email, password);
    setToken(access_token);
    const user = await api.get<User>("/api/auth/me");
    dispatch({ type: "SET_USER", user });
    router.push("/dashboard");
  }, [router]);

  const logout = useCallback(() => {
    clearToken();
    dispatch({ type: "CLEAR_USER" });
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider
      value={{ user: state.user, isLoading: state.isLoading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
