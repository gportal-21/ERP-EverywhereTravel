"use client";
import { FileText, Send } from "lucide-react";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function QuotationsPage() {
  const [form, setForm] = useState({
    client_id: "", destination: "Cusco", start_date: "2026-09-01",
    end_date: "2026-09-06", budget_min: 1000, budget_max: 4000, traveler_count: 2,
  });
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/v1/inquiries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, budget_min: Number(form.budget_min), budget_max: Number(form.budget_max), traveler_count: Number(form.traveler_count) }),
      });
      setResult(await r.json());
    } catch (e) { setResult({ error: String(e) }); }
    setLoading(false);
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <FileText size={22} /> Nueva Cotización
      </h1>
      <div className="bg-white rounded-xl shadow p-6 max-w-lg space-y-4">
        {[
          { label: "ID Cliente", key: "client_id", type: "text" },
          { label: "Destino", key: "destination", type: "text" },
          { label: "Fecha inicio", key: "start_date", type: "date" },
          { label: "Fecha fin", key: "end_date", type: "date" },
          { label: "Presupuesto mín (PEN)", key: "budget_min", type: "number" },
          { label: "Presupuesto máx (PEN)", key: "budget_max", type: "number" },
          { label: "Viajeros", key: "traveler_count", type: "number" },
        ].map(({ label, key, type }) => (
          <div key={key}>
            <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
            <input
              type={type}
              value={(form as any)[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        ))}
        <button
          onClick={submit}
          disabled={loading}
          className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium flex items-center justify-center gap-2 hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          <Send size={16} />
          {loading ? "Enviando al sistema multiagente..." : "Solicitar Cotización"}
        </button>
        {result && (
          <div className={`p-4 rounded-lg text-sm ${result.error ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
            {result.error ? result.error : (
              <div>
                <p className="font-medium">Cotización iniciada</p>
                <p className="font-mono text-xs mt-1">Saga: {result.saga_id}</p>
                <p>Estado: {result.status}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
