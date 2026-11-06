import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE || "/api";

export const api = axios.create({
  baseURL,
  timeout: 1_800_000, // LLM calls can be slow (20b council on CPU)
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("scout_token");
  if (t) {
    cfg.headers = cfg.headers || {};
    cfg.headers.Authorization = `Bearer ${t}`;
  }
  return cfg;
});

// Keycloak access tokens are short-lived. On a 401, try one silent refresh with
// the stored refresh token, then replay the original request. In dev (stub
// tokens, no refresh token) this is a no-op.
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const cfg = error.config || {};
    const status = error.response?.status;
    const refresh = localStorage.getItem("scout_refresh");
    const isRefreshCall = (cfg.url || "").includes("/auth/refresh");
    if (status === 401 && refresh && !cfg._retry && !isRefreshCall) {
      cfg._retry = true;
      try {
        const r = await api.post("/auth/refresh", { refresh_token: refresh });
        const next = r.data as { token: string; refresh_token?: string };
        localStorage.setItem("scout_token", next.token);
        if (next.refresh_token) localStorage.setItem("scout_refresh", next.refresh_token);
        cfg.headers = cfg.headers || {};
        cfg.headers.Authorization = `Bearer ${next.token}`;
        return api(cfg);
      } catch {
        localStorage.removeItem("scout_token");
        localStorage.removeItem("scout_refresh");
      }
    }
    return Promise.reject(error);
  }
);

export const API_BASE = baseURL;
