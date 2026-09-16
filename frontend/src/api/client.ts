import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE || "/api";

export const api = axios.create({
  baseURL,
  timeout: 1_800_000, // LLM calls can be slow (20b council on CPU)
  headers: { "Content-Type": "application/json" },
});

export const API_BASE = baseURL;
