import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { AuthApi, type AuthTokenResponse } from "./api";
import type { AuthStatus, ScoutUser } from "./types";

function storeTokens(res: AuthTokenResponse) {
  localStorage.setItem("scout_token", res.token);
  if (res.refresh_token) localStorage.setItem("scout_refresh", res.refresh_token);
  else localStorage.removeItem("scout_refresh");
  if (res.id_token) localStorage.setItem("scout_id_token", res.id_token);
  else localStorage.removeItem("scout_id_token");
}

function clearTokens() {
  localStorage.removeItem("scout_token");
  localStorage.removeItem("scout_refresh");
  localStorage.removeItem("scout_id_token");
}

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
            // Access token may just be stale — try a refresh (Keycloak mode).
            const refresh = localStorage.getItem("scout_refresh");
            if (refresh) {
              try {
                const r = await AuthApi.refresh(refresh);
                storeTokens(r);
                setUser(r.user);
                setReady(true);
                return;
              } catch {
                clearTokens();
              }
            } else {
              clearTokens();
            }
          }
        }
        if (s.auth_disabled) {
          const auto = await AuthApi.login("dev");
          storeTokens(auto);
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
    storeTokens(res);
    setUser(res.user);
  }

  function logout() {
    const idToken = localStorage.getItem("scout_id_token");
    clearTokens();
    setUser(null);
    // In Keycloak mode, end the SSO session too (RP-initiated logout) so the
    // browser lands back on Keycloak, not a half-logged-in app.
    if (status && !status.auth_disabled && status.keycloak_url && status.keycloak_realm) {
      const base = status.keycloak_url.replace(/\/+$/, "");
      const url = new URL(`${base}/realms/${status.keycloak_realm}/protocol/openid-connect/logout`);
      if (idToken) url.searchParams.set("id_token_hint", idToken);
      if (status.keycloak_client_id) url.searchParams.set("client_id", status.keycloak_client_id);
      url.searchParams.set("post_logout_redirect_uri", window.location.origin + "/");
      window.location.href = url.toString();
    }
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
