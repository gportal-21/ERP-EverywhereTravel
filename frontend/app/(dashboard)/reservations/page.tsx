"use client";
import { BookOpen, Search } from "lucide-react";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function ReservationsPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/v1/reservations/${code.trim()}`, { headers: authHeaders() });
      setResult(await r.json());
    } catch (e) { setResult({ detail: "Error de conexión" }); }
    setLoading(false);
  };

  const STATUS_COLORS: Record<string, string> = {
    PENDING_PAYMENT: "bg-yellow-100 text-yellow-700",
    CONFIRMED: "bg-green-100 text-green-700",
    CANCELLED: "bg-red-100 text-red-700",
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <BookOpen size={22} /> Reservas
      </h1>
      <div className="bg-white rounded-xl shadow p-6 max-w-lg">
        <p className="text-sm text-gray-600 mb-4">Busca una reserva por su código (ej: ET-20260801-AB123)</p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="ET-YYYYMMDD-XXXXX"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
          />
          <button
            onClick={search}
            disabled={loading}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg flex items-center gap-1.5 text-sm hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            <Search size={15} /> Buscar
          </button>
        </div>
        {result && !result.detail && (
          <div className="mt-4 space-y-2 border-t pt-4">
            <div className="flex items-center justify-between">
              <span className="font-mono font-semibold">{result.reservation_code}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[result.status] || "bg-gray-100 text-gray-600"}`}>
                {result.status}
              </span>
            </div>
            <p className="text-sm text-gray-600">Viaje: {result.travel_start?.slice(0,10)} → {result.travel_end?.slice(0,10)}</p>
            <p className="text-sm text-gray-600">Viajeros: {result.traveler_count}</p>
          </div>
        )}
        {result?.detail && (
          <p className="mt-4 text-sm text-red-600">{result.detail}</p>
        )}
      </div>
    </div>
  );
}
