export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function authHeaders(): Record<string, string> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export function fmt(d?: string | null) {
  return d
    ? new Date(d).toLocaleDateString("es-PE", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";
}

export async function fetchJson<T>(
  url: string,
  init?: RequestInit,
): Promise<{ data: T | null; error: string | null; status?: number }> {
  try {
    const res = await fetch(url, init);
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = body?.detail || body?.message || `HTTP ${res.status}`;
      return { data: null, error: detail, status: res.status };
    }
    return { data: body as T, error: null, status: res.status };
  } catch {
    return { data: null, error: "No se pudo conectar con el backend" };
  }
}

export function money(value: unknown) {
  const n = Number(value ?? 0);
  return `S/. ${n.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
