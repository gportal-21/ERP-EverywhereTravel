"use client";
import { DollarSign, CreditCard } from "lucide-react";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function FinancePage() {
  const [code, setCode] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("TRANSFER");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const registerPayment = async () => {
    if (!code.trim() || !amount) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/v1/liquidations/${code.trim()}/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ amount: parseFloat(amount), method, reference: `PAY-${Date.now()}` }),
      });
      setResult(await r.json());
    } catch (e) { setResult({ error: String(e) }); }
    setLoading(false);
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <DollarSign size={22} /> Finanzas — Registro de Pagos
      </h1>
      <div className="bg-white rounded-xl shadow p-6 max-w-lg space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Código de Reserva</label>
          <input
            type="text" placeholder="ET-YYYYMMDD-XXXXX" value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Monto (PEN)</label>
          <input
            type="number" placeholder="0.00" value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Método de Pago</label>
          <select
            value={method} onChange={(e) => setMethod(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="TRANSFER">Transferencia Bancaria</option>
            <option value="CARD">Tarjeta</option>
            <option value="CASH">Efectivo</option>
            <option value="YAPE">Yape/Plin</option>
          </select>
        </div>
        <button
          onClick={registerPayment} disabled={loading}
          className="w-full bg-green-600 text-white py-2.5 rounded-lg font-medium flex items-center justify-center gap-2 hover:bg-green-700 transition-colors disabled:opacity-50"
        >
          <CreditCard size={16} />
          {loading ? "Registrando..." : "Registrar Pago"}
        </button>
        {result && (
          <div className={`p-4 rounded-lg text-sm ${result.error ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
            {result.error ? result.error : (
              <div>
                <p className="font-medium">Pago registrado correctamente</p>
                <p>Total pagado: S/. {result.total_paid}</p>
                <p>Estado: {result.status}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
