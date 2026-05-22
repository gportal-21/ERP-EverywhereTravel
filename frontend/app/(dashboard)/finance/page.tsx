"use client";
import { useState } from "react";
import { DollarSign, CreditCard, CheckCircle, AlertTriangle, Search, Receipt } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

const fmt = (d: string) => d ? new Date(d).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" }) : "—";

const STATUS_CFG: Record<string, { label: string; cls: string }> = {
  PARTIAL:  { label: "Pago parcial", cls: "bg-yellow-100 text-yellow-700" },
  COMPLETE: { label: "Completada",   cls: "bg-green-100 text-green-700" },
  OVERDUE:  { label: "Vencida",      cls: "bg-red-100 text-red-700" },
};

export default function FinancePage() {
  const [code, setCode]           = useState("");
  const [liq, setLiq]             = useState<any>(null);
  const [loading, setLoading]     = useState(false);
  const [amount, setAmount]       = useState("");
  const [method, setMethod]       = useState("TRANSFER");
  const [paying, setPaying]       = useState(false);
  const [payError, setPayError]   = useState("");
  const [lastReceipt, setLastReceipt] = useState<string | null>(null);
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null);
  const [adjusting, setAdjusting] = useState(false);
  const [newTotal, setNewTotal]   = useState("");

  const notify = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3500); };

  const lookup = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setPayError("");
    const r = await fetch(`${API}/api/v1/liquidations/${code.trim()}`, { headers: authH() }).catch(() => null);
    if (r?.ok) { setLiq(await r.json()); setAmount(""); }
    else { notify("Reserva no encontrada", false); setLiq(null); }
    setLoading(false);
  };

  // Validación inline del monto
  const balance = liq ? parseFloat(liq.balance ?? 0) : 0;
  const amountNum = parseFloat(amount) || 0;
  const amountError = (() => {
    if (!amount || amountNum <= 0) return "";
    if (liq?.total_charged > 0 && balance <= 0) return "Esta reserva ya está completamente pagada.";
    if (liq?.total_charged > 0 && amountNum > balance) {
      return `El monto supera el saldo pendiente (S/. ${balance.toFixed(2)}). Puedes pagar hasta ese monto.`;
    }
    return "";
  })();

  const pay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!liq || !amount || amountError) return;
    setPaying(true);
    setPayError("");
    const r = await fetch(`${API}/api/v1/liquidations/${liq.reservation_code}/transactions`, {
      method: "POST", headers: authH(),
      body: JSON.stringify({ amount: amountNum, method, reference: `PAY-${Date.now()}` }),
    }).catch(() => null);
    if (r?.ok) {
      const data = await r.json();
      notify(`Pago de S/. ${amountNum.toFixed(2)} registrado correctamente`);
      setAmount("");
      if (data.receipt_url) setLastReceipt(data.receipt_url);
      // Refrescar datos completos para actualizar cronograma e historial
      const updated = await fetch(`${API}/api/v1/liquidations/${liq.reservation_code}`, { headers: authH() }).catch(() => null);
      if (updated?.ok) setLiq(await updated.json());
      else setLiq((prev: any) => ({ ...prev, total_paid: data.total_paid, balance: data.balance, status: data.status }));
    } else {
      const err = await r?.json().catch(() => null);
      setPayError(err?.detail || "Error al registrar el pago. Intenta nuevamente.");
    }
    setPaying(false);
  };

  const adjustTotal = async () => {
    if (!liq || !newTotal) return;
    const r = await fetch(`${API}/api/v1/liquidations/${liq.reservation_code}/adjust`, {
      method: "PATCH", headers: authH(), body: JSON.stringify({ total_charged: parseFloat(newTotal) }),
    }).catch(() => null);
    if (r?.ok) { notify("Monto actualizado"); setAdjusting(false); lookup(); }
    else notify("Error al ajustar", false);
  };

  const pct = liq && liq.total_charged > 0 ? Math.min(100, Math.round((liq.total_paid / liq.total_charged) * 100)) : 0;
  const cfg = liq ? (STATUS_CFG[liq.status] || { label: liq.status, cls: "bg-gray-100 text-gray-600" }) : null;

  return (
    <div className="p-6 space-y-6">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.ok ? <CheckCircle size={15}/> : <AlertTriangle size={15}/>} {toast.msg}
        </div>
      )}

      <h1 className="text-xl font-bold flex items-center gap-2"><DollarSign size={22}/> Finanzas</h1>

      {/* Búsqueda de reserva */}
      <div className="bg-white rounded-xl shadow p-5">
        <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2"><Search size={16}/> Consultar Reserva</h2>
        <form onSubmit={lookup} className="flex gap-3">
          <input type="text" placeholder="Código de reserva: ET-YYYYMMDD-XXXXX" value={code}
            onChange={e => setCode(e.target.value)}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"/>
          <button type="submit" disabled={loading}
            className="bg-blue-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {loading ? "Buscando…" : "Buscar"}
          </button>
        </form>
      </div>

      {liq && (
        <div className="space-y-4">
          {/* Resumen de liquidación */}
          <div className="bg-white rounded-xl shadow p-5">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="font-semibold text-gray-800">{liq.reservation_code}</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Viaje: {fmt(liq.travel_start)} → {fmt(liq.travel_end)} · {liq.traveler_count} viajeros
                </p>
              </div>
              {cfg && <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${cfg.cls}`}>{cfg.label}</span>}
            </div>

            {/* Progress bar */}
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                <span>Progreso de pago</span><span>{pct}%</span>
              </div>
              <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-500 ${pct >= 100 ? "bg-green-500" : pct > 50 ? "bg-blue-500" : "bg-yellow-400"}`}
                  style={{ width: `${pct}%` }}/>
              </div>
            </div>

            {/* Montos */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Total a pagar", val: liq.total_charged, bold: true, cls: "text-gray-800" },
                { label: "Total pagado",  val: liq.total_paid,    bold: true, cls: "text-green-700" },
                { label: "Saldo pendiente", val: liq.balance,     bold: true, cls: liq.balance > 0 ? "text-yellow-700" : "text-green-700" },
              ].map(({ label, val, cls }) => (
                <div key={label} className="bg-gray-50 rounded-xl p-3 text-center">
                  <p className="text-[10px] text-gray-400 mb-1">{label}</p>
                  <p className={`text-lg font-bold ${cls}`}>S/. {parseFloat(val || 0).toFixed(2)}</p>
                </div>
              ))}
            </div>

            {/* Ajustar monto total */}
            {liq.status !== "COMPLETE" && (
              <div className="border-t pt-3">
                {!adjusting ? (
                  <button onClick={() => { setAdjusting(true); setNewTotal(liq.total_charged); }}
                    className="text-xs text-gray-400 hover:text-blue-600 transition-colors">
                    Ajustar monto total →
                  </button>
                ) : (
                  <div className="flex gap-2 items-center">
                    <span className="text-xs text-gray-600">Nuevo total:</span>
                    <input type="number" step="0.01" value={newTotal} onChange={e => setNewTotal(e.target.value)}
                      className="border rounded-lg px-2 py-1.5 text-sm w-32 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    <button onClick={adjustTotal} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">Guardar</button>
                    <button onClick={() => setAdjusting(false)} className="px-3 py-1.5 bg-gray-100 rounded-lg text-xs hover:bg-gray-200">Cancelar</button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Cronograma */}
          {liq.payment_schedule?.length > 0 && (
            <div className="bg-white rounded-xl shadow p-5">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2 text-sm"><Receipt size={15}/> Cronograma de Pagos</h3>
              <div className="space-y-2">
                {liq.payment_schedule.map((s: any, i: number) => {
                  const isPast = new Date(s.due_date) < new Date();
                  return (
                    <div key={i} className={`flex justify-between items-center p-3 rounded-lg border text-sm ${isPast && liq.status !== "COMPLETE" ? "border-yellow-200 bg-yellow-50" : "border-gray-100 bg-gray-50"}`}>
                      <div>
                        <span className="font-medium text-gray-700">Cuota {i + 1}</span>
                        <span className="text-gray-400 ml-2 text-xs">vence {fmt(s.due_date)}</span>
                        {isPast && liq.status !== "COMPLETE" && <span className="ml-2 text-[10px] text-yellow-600 font-medium">Vencida</span>}
                      </div>
                      <span className="font-bold text-gray-800">S/. {parseFloat(s.amount).toFixed(2)} <span className="text-gray-400 font-normal text-xs">({s.pct}%)</span></span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Registrar pago */}
          {liq.status !== "COMPLETE" && liq.total_charged > 0 && (
            <div className="bg-white rounded-xl shadow p-5">
              <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm"><CreditCard size={15}/> Registrar Pago</h3>
              <form onSubmit={pay} className="space-y-3">

                {/* Atajos de cuotas */}
                {liq.payment_schedule?.length > 0 && balance > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-2">Pagar cuota rápida:</p>
                    <div className="flex flex-wrap gap-2">
                      {liq.payment_schedule.map((s: any, i: number) => {
                        const cuotaAmt = parseFloat(s.amount);
                        const factible = cuotaAmt <= balance;
                        return (
                          <button key={i} type="button"
                            disabled={!factible}
                            onClick={() => { setAmount(cuotaAmt.toFixed(2)); setPayError(""); }}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                              factible
                                ? "border-blue-200 text-blue-700 bg-blue-50 hover:bg-blue-100"
                                : "border-gray-100 text-gray-300 bg-gray-50 cursor-not-allowed"
                            }`}>
                            Cuota {i+1}: S/. {cuotaAmt.toFixed(2)}
                          </button>
                        );
                      })}
                      <button type="button"
                        onClick={() => { setAmount(balance.toFixed(2)); setPayError(""); }}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium border border-green-200 text-green-700 bg-green-50 hover:bg-green-100 transition-colors">
                        Pagar todo: S/. {balance.toFixed(2)}
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Monto (S/.) *
                      {balance > 0 && <span className="text-gray-400 ml-1">— máx S/. {balance.toFixed(2)}</span>}
                    </label>
                    <input
                      type="number" step="0.01" min="0.01" placeholder="0.00"
                      value={amount}
                      onChange={e => { setAmount(e.target.value); setPayError(""); }}
                      required
                      className={`w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 transition-colors ${
                        amountError
                          ? "border-red-300 focus:ring-red-400 bg-red-50"
                          : "border-gray-200 focus:ring-green-500"
                      }`}
                    />
                    {amountError && (
                      <p className="text-xs text-red-600 mt-1 flex items-start gap-1">
                        <AlertTriangle size={11} className="mt-0.5 flex-shrink-0"/>
                        {amountError}
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Método de Pago</label>
                    <select value={method} onChange={e => setMethod(e.target.value)}
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
                      <option value="TRANSFER">Transferencia Bancaria</option>
                      <option value="CARD">Tarjeta Crédito/Débito</option>
                      <option value="CASH">Efectivo</option>
                      <option value="YAPE">Yape / Plin</option>
                      <option value="DEPOSIT">Depósito Bancario</option>
                    </select>
                  </div>
                </div>

                {/* Error del backend */}
                {payError && (
                  <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                    <AlertTriangle size={13} className="mt-0.5 flex-shrink-0"/>
                    {payError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={paying || !amount || !!amountError || amountNum <= 0}
                  className="w-full bg-green-600 text-white py-2.5 rounded-lg font-medium flex items-center justify-center gap-2 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                  <CreditCard size={16}/>
                  {paying ? "Procesando…" : amountNum > 0 && !amountError ? `Registrar S/. ${amountNum.toFixed(2)}` : "Registrar Pago"}
                </button>

                {lastReceipt && (
                  <a href={lastReceipt} target="_blank" rel="noreferrer"
                    className="flex items-center justify-center gap-2 w-full border border-blue-300 text-blue-700 bg-blue-50 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-100 transition-colors">
                    <Receipt size={15}/> Descargar comprobante PDF
                  </a>
                )}
              </form>
            </div>
          )}

          {liq.status !== "COMPLETE" && liq.total_charged === 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-center gap-3">
              <AlertTriangle size={18} className="text-yellow-600 flex-shrink-0"/>
              <div>
                <p className="font-semibold text-yellow-800 text-sm">Monto total no definido</p>
                <p className="text-xs text-yellow-600 mt-0.5">Usa <strong>Ajustar monto total</strong> para establecer el costo de la reserva antes de registrar pagos.</p>
              </div>
            </div>
          )}

          {liq.status === "COMPLETE" && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3">
              <CheckCircle size={20} className="text-green-600 flex-shrink-0"/>
              <div>
                <p className="font-semibold text-green-800">Reserva completamente pagada</p>
                <p className="text-xs text-green-600 mt-0.5">Total: S/. {parseFloat(liq.total_charged).toFixed(2)} — Comisión: S/. {parseFloat(liq.commission_amount || 0).toFixed(2)}</p>
              </div>
            </div>
          )}

          {/* Historial de pagos */}
          {liq.transactions?.length > 0 && (
            <div className="bg-white rounded-xl shadow p-5">
              <h3 className="font-semibold text-gray-800 mb-3 text-sm">Historial de Pagos</h3>
              <div className="space-y-2">
                {liq.transactions.map((t: any, i: number) => (
                  <div key={i} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg text-sm">
                    <div>
                      <span className="font-medium text-gray-700">{t.method}</span>
                      {t.reference && <span className="text-gray-400 ml-2 text-xs">{t.reference}</span>}
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-green-700">+S/. {parseFloat(t.amount).toFixed(2)}</p>
                      <p className="text-gray-400 text-xs">{fmt(t.date)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
