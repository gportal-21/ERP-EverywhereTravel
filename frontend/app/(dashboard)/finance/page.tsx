"use client";
import { useState } from "react";
import { DollarSign, CreditCard, CheckCircle, AlertTriangle, Search, Receipt } from "lucide-react";
import { API, authHeaders, fetchJson, fmt, money } from "@/lib/fetch-api";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { DataState } from "@/components/ui/data-state";

const STATUS_CFG: Record<string, { label: string; variant: "warning" | "success" | "error" }> = {
  PARTIAL:  { label: "Pago parcial", variant: "warning" },
  COMPLETE: { label: "Completada",   variant: "success" },
  OVERDUE:  { label: "Vencida",      variant: "error" },
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
  const [adjusting, setAdjusting] = useState(false);
  const [newTotal, setNewTotal]   = useState("");
  const [lookupError, setLookupError] = useState("");
  const { toast, notify } = useToast();

  const lookup = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setPayError("");
    setLookupError("");
    const { data, error } = await fetchJson<any>(`${API}/api/v1/liquidations/${code.trim()}`, { headers: authHeaders() });
    if (data) { setLiq(data); setAmount(""); }
    else {
      const msg = error || "Reserva no encontrada";
      notify(msg, false);
      setLookupError(msg);
      setLiq(null);
    }
    setLoading(false);
  };

  const balance = liq ? parseFloat(liq.balance ?? 0) : 0;
  const amountNum = parseFloat(amount) || 0;
  const amountError = (() => {
    if (!amount || amountNum <= 0) return "";
    if (liq?.total_charged > 0 && balance <= 0) return "Esta reserva ya esta completamente pagada.";
    if (liq?.total_charged > 0 && amountNum > balance) {
      return `El monto supera el saldo pendiente (${money(balance)}).`;
    }
    return "";
  })();

  const pay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!liq || !amount || amountError) return;
    setPaying(true);
    setPayError("");
    const { data, error } = await fetchJson<any>(`${API}/api/v1/liquidations/${liq.reservation_code}/transactions`, {
      method: "POST", headers: authHeaders(),
      body: JSON.stringify({ amount: amountNum, method, reference: `PAY-${Date.now()}` }),
    });
    if (data) {
      notify(`Pago de S/. ${amountNum.toFixed(2)} registrado correctamente`);
      setAmount("");
      if (data.receipt_url) setLastReceipt(data.receipt_url);
      const updated = await fetchJson<any>(`${API}/api/v1/liquidations/${liq.reservation_code}`, { headers: authHeaders() });
      if (updated.data) setLiq(updated.data);
      else setLiq((prev: any) => ({ ...prev, total_paid: data.total_paid, balance: data.balance, status: data.status }));
    } else {
      setPayError(error || "Error al registrar el pago.");
    }
    setPaying(false);
  };

  const adjustTotal = async () => {
    if (!liq || !newTotal) return;
    const { error } = await fetchJson(`${API}/api/v1/liquidations/${liq.reservation_code}/adjust`, {
      method: "PATCH", headers: authHeaders(), body: JSON.stringify({ total_charged: parseFloat(newTotal) }),
    });
    if (!error) { notify("Monto actualizado"); setAdjusting(false); lookup(); }
    else notify(error, false);
  };

  const pct = liq && liq.total_charged > 0 ? Math.min(100, Math.round((liq.total_paid / liq.total_charged) * 100)) : 0;
  const cfg = liq ? (STATUS_CFG[liq.status] || null) : null;

  const inputCls = "w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors";

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <Toast toast={toast} />

      <PageHeader icon={<DollarSign size={20} />} title="Finanzas" />

      {/* Reservation lookup */}
      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
        <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm">
          <Search size={15} className="text-blue-500"/> Consultar Reserva
        </h2>
        <form onSubmit={lookup} className="flex flex-col sm:flex-row gap-3">
          <input type="text" placeholder="Codigo de reserva: ET-YYYYMMDD-XXXXX" value={code}
            onChange={e => setCode(e.target.value)}
            className="flex-1 border border-gray-200 rounded-xl px-3 py-2.5 text-sm font-mono focus:border-blue-500 bg-white transition-colors"/>
          <button type="submit" disabled={loading}
            className="bg-blue-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm">
            {loading ? "Buscando..." : "Buscar"}
          </button>
        </form>
      </div>

      {!liq && lookupError && (
        <DataState
          kind="error"
          title="No se encontro liquidacion para esa reserva"
          description={lookupError}
          actionLabel="Buscar de nuevo"
          onAction={() => lookup()}
        />
      )}

      {liq && (
        <div className="space-y-4 animate-fade-in">
          {/* Liquidation summary */}
          <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
              <div>
                <h2 className="font-semibold text-gray-800">{liq.reservation_code}</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Viaje: {fmt(liq.travel_start)} - {fmt(liq.travel_end)} -- {liq.traveler_count} viajeros
                </p>
              </div>
              {cfg && <StatusBadge variant={cfg.variant}>{cfg.label}</StatusBadge>}
            </div>

            {/* Progress bar */}
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                <span>Progreso de pago</span><span className="font-medium">{pct}%</span>
              </div>
              <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${pct >= 100 ? "bg-emerald-500" : pct > 50 ? "bg-blue-500" : "bg-amber-400"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>

            {/* Amounts */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              {[
                { label: "Total a pagar", val: liq.total_charged, cls: "text-gray-800" },
                { label: "Total pagado",  val: liq.total_paid,    cls: "text-emerald-700" },
                { label: "Saldo pendiente", val: liq.balance,     cls: liq.balance > 0 ? "text-amber-700" : "text-emerald-700" },
              ].map(({ label, val, cls }) => (
                <div key={label} className="bg-gray-50 rounded-xl p-3 text-center ring-1 ring-gray-100">
                  <p className="text-xs text-gray-500 mb-1">{label}</p>
                  <p className={`text-lg font-bold ${cls}`}>{money(val)}</p>
                </div>
              ))}
            </div>

            {/* Adjust total */}
            {liq.status !== "COMPLETE" && (
              <div className="border-t border-gray-100 pt-3">
                {!adjusting ? (
                  <button onClick={() => { setAdjusting(true); setNewTotal(liq.total_charged); }}
                    className="text-xs text-gray-500 hover:text-blue-600 transition-colors font-medium">
                    Ajustar monto total
                  </button>
                ) : (
                  <div className="flex flex-wrap gap-2 items-center">
                    <span className="text-xs text-gray-600">Nuevo total:</span>
                    <input type="number" step="0.01" value={newTotal} onChange={e => setNewTotal(e.target.value)}
                      className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm w-32 focus:border-blue-500"/>
                    <button onClick={adjustTotal} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors">Guardar</button>
                    <button onClick={() => setAdjusting(false)} className="px-3 py-1.5 bg-gray-100 rounded-lg text-xs hover:bg-gray-200 transition-colors">Cancelar</button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Payment schedule */}
          {liq.payment_schedule?.length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2 text-sm">
                <Receipt size={15} className="text-blue-500"/> Cronograma de Pagos
              </h3>
              <div className="space-y-2">
                {liq.payment_schedule.map((s: any, i: number) => {
                  const isPast = new Date(s.due_date) < new Date();
                  return (
                    <div key={i} className={`flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 rounded-xl border text-sm ${isPast && liq.status !== "COMPLETE" ? "border-amber-200 bg-amber-50/50" : "border-gray-100 bg-gray-50"}`}>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-700">Cuota {i + 1}</span>
                        <span className="text-gray-400 text-xs">vence {fmt(s.due_date)}</span>
                        {isPast && liq.status !== "COMPLETE" && (
                          <StatusBadge variant="warning">Vencida</StatusBadge>
                        )}
                      </div>
                      <span className="font-bold text-gray-800">
                        {money(s.amount)} <span className="text-gray-400 font-normal text-xs">({s.pct}%)</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Register payment */}
          {liq.status !== "COMPLETE" && liq.total_charged > 0 && (
            <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm">
                <CreditCard size={15} className="text-emerald-500"/> Registrar Pago
              </h3>
              <form onSubmit={pay} className="space-y-3">
                {/* Quick payment buttons */}
                {liq.payment_schedule?.length > 0 && balance > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-2">Pagar cuota rapida:</p>
                    <div className="flex flex-wrap gap-2">
                      {liq.payment_schedule.map((s: any, i: number) => {
                        const cuotaAmt = parseFloat(s.amount);
                        const factible = cuotaAmt <= balance;
                        return (
                          <button key={i} type="button" disabled={!factible}
                            onClick={() => { setAmount(cuotaAmt.toFixed(2)); setPayError(""); }}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                              factible
                                ? "border-blue-200 text-blue-700 bg-blue-50 hover:bg-blue-100"
                                : "border-gray-100 text-gray-300 bg-gray-50 cursor-not-allowed"
                            }`}>
                            Cuota {i+1}: {money(cuotaAmt)}
                          </button>
                        );
                      })}
                      <button type="button"
                        onClick={() => { setAmount(balance.toFixed(2)); setPayError(""); }}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors">
                        Pagar todo: {money(balance)}
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">
                      Monto (S/.) *
                      {balance > 0 && <span className="text-gray-400 ml-1">-- max {money(balance)}</span>}
                    </label>
                    <input
                      type="number" step="0.01" min="0.01" placeholder="0.00"
                      value={amount}
                      onChange={e => { setAmount(e.target.value); setPayError(""); }}
                      required
                      className={`${inputCls} ${amountError ? "border-red-300 bg-red-50" : ""}`}
                    />
                    {amountError && (
                      <p className="text-xs text-red-600 mt-1 flex items-start gap-1">
                        <AlertTriangle size={11} className="mt-0.5 flex-shrink-0"/>
                        {amountError}
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">Metodo de Pago</label>
                    <select value={method} onChange={e => setMethod(e.target.value)} className={inputCls}>
                      <option value="TRANSFER">Transferencia Bancaria</option>
                      <option value="CARD">Tarjeta Credito/Debito</option>
                      <option value="CASH">Efectivo</option>
                      <option value="YAPE">Yape / Plin</option>
                      <option value="DEPOSIT">Deposito Bancario</option>
                    </select>
                  </div>
                </div>

                {payError && (
                  <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
                    <AlertTriangle size={13} className="mt-0.5 flex-shrink-0"/>
                    {payError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={paying || !amount || !!amountError || amountNum <= 0}
                  className="w-full bg-emerald-600 text-white py-2.5 rounded-xl font-medium flex items-center justify-center gap-2 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm">
                  <CreditCard size={16}/>
                  {paying ? "Procesando..." : amountNum > 0 && !amountError ? `Registrar S/. ${amountNum.toFixed(2)}` : "Registrar Pago"}
                </button>

                {lastReceipt && (
                  <a href={lastReceipt} target="_blank" rel="noreferrer"
                    className="flex items-center justify-center gap-2 w-full border border-blue-200 text-blue-700 bg-blue-50 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-100 transition-colors">
                    <Receipt size={15}/> Descargar comprobante PDF
                  </a>
                )}
              </form>
            </div>
          )}

          {liq.status !== "COMPLETE" && liq.total_charged === 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-center gap-3">
              <AlertTriangle size={18} className="text-amber-600 flex-shrink-0"/>
              <div>
                <p className="font-semibold text-amber-800 text-sm">Monto total no definido</p>
                <p className="text-xs text-amber-600 mt-0.5">Usa <strong>Ajustar monto total</strong> para establecer el costo antes de registrar pagos.</p>
              </div>
            </div>
          )}

          {liq.status === "COMPLETE" && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 flex items-center gap-3">
              <CheckCircle size={20} className="text-emerald-600 flex-shrink-0"/>
              <div>
                <p className="font-semibold text-emerald-800">Reserva completamente pagada</p>
                <p className="text-xs text-emerald-600 mt-0.5">Total: {money(liq.total_charged)} -- Comision: {money(liq.commission_amount)}</p>
              </div>
            </div>
          )}

          {/* Payment history */}
          {liq.transactions?.length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-3 text-sm">Historial de Pagos</h3>
              <div className="space-y-2">
                {liq.transactions.map((t: any, i: number) => (
                  <div key={i} className="flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 bg-gray-50 rounded-xl text-sm ring-1 ring-gray-100">
                    <div>
                      <span className="font-medium text-gray-700">{t.method}</span>
                      {t.reference && <span className="text-gray-400 ml-2 text-xs">{t.reference}</span>}
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-emerald-700">+{money(t.amount)}</p>
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
