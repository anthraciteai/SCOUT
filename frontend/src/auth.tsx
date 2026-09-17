import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { AuthApi } from "./api";
import type { AuthStatus, ScoutUser } from "./types";

interface AuthCtx {
  status: AuthStatus | null;
  user: ScoutUser | null;
  ready: boolean;
  login: (username: string, password?: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [user, setUser] = useState<ScoutUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const s = await AuthApi.status();
        setStatus(s);
        const token = localStorage.getItem("scout_token");
        if (token) {
          try {
            setUser(await AuthApi.me());
            setReady(true);
            return;
          } catch {
            localStorage.removeItem("scout_token");
          }
        }
        if (s.auth_disabled) {
          const auto = await AuthApi.login("dev");
          localStorage.setItem("scout_token", auto.token);
          setUser(auto.user);
        }
      } catch {
        /* backend not up yet */
      } finally {
        setReady(true);
      }
    })();
  }, []);

  async function login(username: string, password = "") {
    const res = await AuthApi.login(username, password);
    localStorage.setItem("scout_token", res.token);
    setUser(res.user);
  }

  function logout() {
    localStorage.removeItem("scout_token");
    setUser(null);
  }

  return (
    <Ctx.Provider value={{ status, user, ready, login, logout }}>{children}</Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within AuthProvider");
  return c;
}
