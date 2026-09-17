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

export const API_BASE = baseURL;
