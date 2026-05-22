"use client";
import { useEffect, useState } from "react";
import { BookOpen, Search, RefreshCw, Calendar, Users, CheckCircle, XCircle, ChevronDown, ChevronUp, DollarSign, Map, FileText } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

const STATUS: Record<string, { label: string; cls: string }> = {
  PENDING_PAYMENT: { label: "Pago pendiente", cls: "bg-yellow-100 text-yellow-700" },
  CONFIRMED:       { label: "Confirmada",      cls: "bg-green-100 text-green-700" },
  CANCELLED:       { label: "Cancelada",       cls: "bg-red-100 text-red-700" },
  REFUNDED:        { label: "Reembolsada",     cls: "bg-purple-100 text-purple-700" },
};

const fmt = (d: string) => d ? new Date(d).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export default function ReservationsPage() {
  const [reservations, setReservations] = useState<any[]>([]);
  const [loading, setLoading]    = useState(true);
  const [search, setSearch]      = useState("");
  const [filter, setFilter]      = useState("");
  const [expanded, setExpanded]  = useState<string | null>(null);
  const [liqData, setLiqData]    = useState<Record<string, any>>({});
  const [itinData, setItinData]  = useState<Record<string, string | null>>({});
  const [toast, setToast]        = useState<{ msg: string; ok: boolean } | null>(null);
  const [updating, setUpdating]  = useState<string | null>(null);

  const notify = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3000); };

  const load = async () => {
    setLoading(true);
    const q = filter ? `?status=${filter}` : "";
    const r = await fetch(`${API}/api/v1/reservations/${q}`, { headers: authH() }).catch(() => null);
    if (r?.ok) setReservations((await r.json()).reservations || []);
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]);

  const loadLiq = async (code: string, quoteId?: string) => {
    if (expanded === code) { setExpanded(null); return; }
    const [liqRes, itinRes] = await Promise.all([
      fetch(`${API}/api/v1/liquidations/${code}`, { headers: authH() }).catch(() => null),
      quoteId ? fetch(`${API}/api/v1/itinerary/${quoteId}`, { headers: authH() }).catch(() => null) : null,
    ]);
    if (liqRes?.ok) {
      const liq = await liqRes.json();
      setLiqData(d => ({ ...d, [code]: liq }));
    }
    if (itinRes?.ok) {
      const itin = await itinRes.json();
      setItinData(d => ({ ...d, [code]: itin.status === "ready" ? itin.url : null }));
    }
    setExpanded(code);
  };

  const updateStatus = async (code: string, status: string) => {
    setUpdating(code);
    const r = await fetch(`${API}/api/v1/reservations/${code}`, { method: "PATCH", headers: authH(), body: JSON.stringify({ status }) }).catch(() => null);
    if (r?.ok) { notify(`Estado → ${STATUS[status]?.label}`); load(); setLiqData({}); }
    else notify("Error al actualizar estado", false);
    setUpdating(null);
  };

  const filtered = reservations.filter(r =>
    !search || r.reservation_code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-5">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.ok ? <CheckCircle size={15}/> : <XCircle size={15}/>} {toast.msg}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2"><BookOpen size={22}/> Reservas</h1>
        <button onClick={load} className="p-2 hover:bg-white rounded-lg border transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
        </button>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input type="text" placeholder="Buscar por código…" value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
        </div>
        <select value={filter} onChange={e => setFilter(e.target.value)}
          className="w-48 px-3 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">Todos los estados</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-xl shadow overflow-hidden">
        <div className="px-5 py-3 border-b bg-gray-50">
          <span className="text-sm text-gray-500">{filtered.length} reservas</span>
        </div>

        {loading ? (
          <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"/></div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400"><BookOpen size={36} className="mx-auto mb-2 opacity-30"/><p className="text-sm">Sin reservas</p></div>
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(r => {
              const cfg = STATUS[r.status] || { label: r.status, cls: "bg-gray-100 text-gray-600" };
              const isExpanded = expanded === r.reservation_code;
              const liq = liqData[r.reservation_code];
              const itinUrl = itinData[r.reservation_code];
              const isBusy = updating === r.reservation_code;

              return (
                <div key={r.reservation_code}>
                  <div className="flex flex-col md:flex-row md:items-center gap-3 px-5 py-4 hover:bg-gray-50 transition-colors">
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                      <div>
                        <p className="font-mono font-bold text-gray-800 text-xs">{r.reservation_code}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium mt-1 inline-block ${cfg.cls}`}>{cfg.label}</span>
                      </div>
                      <div className="text-xs text-gray-500 flex items-start gap-1"><Calendar size={11} className="mt-0.5 flex-shrink-0"/><span>{fmt(r.travel_start)} → {fmt(r.travel_end)}</span></div>
                      <div className="text-xs text-gray-500 flex items-center gap-1"><Users size={11}/>{r.traveler_count} viajeros</div>
                      <div className="text-xs text-gray-400">{fmt(r.created_at)}</div>
                    </div>
                    <div className="flex gap-1.5 flex-shrink-0 flex-wrap">
                      {r.status === "PENDING_PAYMENT" && (
                        <button disabled={isBusy} onClick={() => updateStatus(r.reservation_code, "CONFIRMED")}
                          className="flex items-center gap-1 bg-green-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-green-600 disabled:opacity-50 transition-colors">
                          <CheckCircle size={11}/> Confirmar
                        </button>
                      )}
                      {(r.status === "PENDING_PAYMENT" || r.status === "CONFIRMED") && (
                        <button disabled={isBusy} onClick={() => { if (confirm("¿Cancelar esta reserva?")) updateStatus(r.reservation_code, "CANCELLED"); }}
                          className="flex items-center gap-1 border border-red-200 text-red-600 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-red-50 disabled:opacity-50 transition-colors">
                          <XCircle size={11}/> Cancelar
                        </button>
                      )}
                      <button onClick={() => loadLiq(r.reservation_code, r.quote_id)}
                        className="flex items-center gap-1 border border-gray-200 text-gray-600 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-gray-50 transition-colors">
                        <DollarSign size={11}/> Detalle {isExpanded ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="bg-indigo-50/60 border-t border-indigo-100 px-5 py-4 space-y-3">
                      {!liq ? (
                        <div className="flex justify-center py-4"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-400"/></div>
                      ) : (
                        <>
                          <div className="grid grid-cols-3 gap-3">
                            {[
                              { label: "Total a pagar", val: `S/. ${liq.total_charged?.toFixed(2)}`, cls: "text-gray-800" },
                              { label: "Total pagado",  val: `S/. ${liq.total_paid?.toFixed(2)}`,    cls: "text-green-700" },
                              { label: "Saldo pendiente", val: `S/. ${liq.balance?.toFixed(2)}`,    cls: liq.balance > 0 ? "text-yellow-700" : "text-green-700" },
                            ].map(({ label, val, cls }) => (
                              <div key={label} className="bg-white rounded-xl p-3 text-center shadow-sm">
                                <p className="text-[10px] text-gray-400 mb-1">{label}</p>
                                <p className={`text-base font-bold ${cls}`}>{val}</p>
                              </div>
                            ))}
                          </div>

                          {liq.payment_schedule?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-gray-600 mb-2">Cronograma</p>
                              <div className="space-y-1.5">
                                {liq.payment_schedule.map((s: any, i: number) => (
                                  <div key={i} className="flex justify-between items-center bg-white rounded-lg px-3 py-2 text-xs shadow-sm">
                                    <span className="text-gray-500">Cuota {i+1} — vence {fmt(s.due_date)}</span>
                                    <span className="font-semibold">S/. {parseFloat(s.amount).toFixed(2)} <span className="text-gray-400">({s.pct}%)</span></span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {liq.transactions?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-gray-600 mb-2">Pagos registrados</p>
                              <div className="space-y-1">
                                {liq.transactions.map((t: any) => (
                                  <div key={t.id} className="flex justify-between items-center bg-white rounded-lg px-3 py-2 text-xs shadow-sm">
                                    <span className="text-gray-600 font-medium">{t.method} {t.reference && <span className="text-gray-400">— {t.reference}</span>}</span>
                                    <div className="text-right">
                                      <p className="font-bold text-green-600">+S/. {parseFloat(t.amount).toFixed(2)}</p>
                                      <p className="text-gray-400">{fmt(t.date)}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Itinerario */}
                          <div className="pt-1 border-t border-indigo-100">
                            {itinUrl ? (
                              <a href={itinUrl} target="_blank" rel="noreferrer"
                                className="flex items-center gap-2 w-full bg-indigo-600 text-white py-2 px-3 rounded-lg text-xs font-medium hover:bg-indigo-700 transition-colors">
                                <Map size={13}/> Ver itinerario PDF
                              </a>
                            ) : (
                              <p className="flex items-center gap-1.5 text-xs text-gray-400 py-1">
                                <FileText size={12}/> Itinerario no generado — genéralo desde Cotizaciones
                              </p>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
