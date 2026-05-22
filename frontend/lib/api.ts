/**
 * API Client — Axios instance preconfigurada con interceptor de auth.
 *
 * - Inyecta automáticamente el Bearer token desde localStorage
 * - En respuestas 401, limpia sesión y redirige a /login
 */

import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor: adjuntar token
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("et_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor: manejar 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.includes("/login")
    ) {
      localStorage.removeItem("et_token");
      localStorage.removeItem("et_user");
      localStorage.removeItem("et_role");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
