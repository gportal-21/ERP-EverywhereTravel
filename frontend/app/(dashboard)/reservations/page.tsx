"use client";
import { useEffect, useState } from "react";
import { BookOpen, Search, RefreshCw, Calendar, Users, CheckCircle, XCircle, ChevronDown, ChevronUp, DollarSign, Map, FileText } from "lucide-react";
import { API, authHeaders, fetchJson, fmt, money } from "@/lib/fetch-api";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { DataState } from "@/components/ui/data-state";

const STATUS: Record<string, { label: string; variant: "warning" | "success" | "error" | "purple" }> = {
  PENDING_PAYMENT: { label: "Pago pendiente", variant: "warning" },
  CONFIRMED:       { label: "Confirmada",     variant: "success" },
  CANCELLED:       { label: "Cancelada",      variant: "error" },
  REFUNDED:        { label: "Reembolsada",    variant: "purple" },
};

export default function ReservationsPage() {
  const [reservations, setReservations] = useState<any[]>([]);
  const [loading, setLoading]    = useState(true);
  const [search, setSearch]      = useState("");
  const [filter, setFilter]      = useState("");
  const [expanded, setExpanded]  = useState<string | null>(null);
  const [liqData, setLiqData]    = useState<Record<string, any>>({});
  const [itinData, setItinData]  = useState<Record<string, string | null>>({});
  const [updating, setUpdating]  = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");
  const { toast, notify } = useToast();

  const load = async () => {
    setLoading(true);
    setLoadError("");
    const q = filter ? `?status=${filter}` : "";
    const { data, error } = await fetchJson<{ reservations: any[] }>(`${API}/api/v1/reservations/${q}`, { headers: authHeaders() });
    if (data) setReservations(Array.isArray(data.reservations) ? data.reservations : []);
    if (error) setLoadError(error);
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]);

  const loadLiq = async (code: string, quoteId?: string) => {
    if (expanded === code) { setExpanded(null); return; }
    const [liqRes, itinRes] = await Promise.all([
      fetchJson<any>(`${API}/api/v1/liquidations/${code}`, { headers: authHeaders() }),
      quoteId ? fetchJson<any>(`${API}/api/v1/itinerary/${quoteId}`, { headers: authHeaders() }) : Promise.resolve(null),
    ]);
    setLiqData(d => ({ ...d, [code]: liqRes?.data || { error: liqRes?.error || "Liquidacion no disponible" } }));
    if (itinRes?.data) setItinData(d => ({ ...d, [code]: itinRes.data.status === "ready" ? itinRes.data.url : null }));
    setExpanded(code);
  };

  const updateStatus = async (code: string, status: string) => {
    setUpdating(code);
    const { error } = await fetchJson(`${API}/api/v1/reservations/${code}`, { method: "PATCH", headers: authHeaders(), body: JSON.stringify({ status }) });
    if (!error) { notify(`Estado actualizado: ${STATUS[status]?.label}`); load(); setLiqData({}); }
    else notify(error, false);
    setUpdating(null);
  };

  const filtered = reservations.filter(r =>
    !search || r.reservation_code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <Toast toast={toast} />

      <PageHeader
        icon={<BookOpen size={20} />}
        title="Reservas"
        actions={
          <button onClick={load} className="p-2.5 hover:bg-white rounded-xl border border-gray-200 transition-colors" aria-label="Refrescar">
            <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
          </button>
        }
      />

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input type="text" placeholder="Buscar por codigo..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:border-blue-500 transition-colors"/>
        </div>
        <select value={filter} onChange={e => setFilter(e.target.value)}
          className="w-full sm:w-48 px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:border-blue-500 transition-colors">
          <option value="">Todos los estados</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 bg-gray-50/50">
          <span className="text-sm text-gray-500">{filtered.length} reservas</span>
        </div>

        {loading ? (
          <TableSkeleton rows={4} />
        ) : loadError ? (
          <div className="p-5">
            <DataState kind="error" title="No se pudieron cargar las reservas" description={loadError} actionLabel="Reintentar" onAction={load} />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<BookOpen size={32} />}
            title="Sin reservas"
            description="Las reservas se crean desde cotizaciones validadas."
          />
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(r => {
              const cfg = STATUS[r.status] || { label: r.status, variant: "neutral" as const };
              const isExpanded = expanded === r.reservation_code;
              const liq = liqData[r.reservation_code];
              const itinUrl = itinData[r.reservation_code];
              const isBusy = updating === r.reservation_code;

              return (
                <div key={r.reservation_code}>
                  <div className="flex flex-col md:flex-row md:items-center gap-3 px-5 py-4 hover:bg-gray-50/50 transition-colors">
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                      <div>
                        <p className="font-mono font-bold text-gray-800 text-xs">{r.reservation_code}</p>
                        <div className="mt-1">
                          <StatusBadge variant={cfg.variant}>{cfg.label}</StatusBadge>
                        </div>
                      </div>
                      <div className="text-xs text-gray-500 flex items-start gap-1">
                        <Calendar size={12} className="mt-0.5 flex-shrink-0"/>
                        <span>{fmt(r.travel_start)} - {fmt(r.travel_end)}</span>
                      </div>
                      <div className="text-xs text-gray-500 flex items-center gap-1">
                        <Users size={12}/>{r.traveler_count} viajeros
                      </div>
                      <div className="text-xs text-gray-500">{fmt(r.created_at)}</div>
                    </div>
                    <div className="flex gap-1.5 flex-shrink-0 flex-wrap">
                      {r.status === "PENDING_PAYMENT" && (
                        <button disabled={isBusy} onClick={() => updateStatus(r.reservation_code, "CONFIRMED")}
                          className="flex items-center gap-1 bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-emerald-600 disabled:opacity-50 transition-colors">
                          <CheckCircle size={11}/> Confirmar
                        </button>
                      )}
                      {(r.status === "PENDING_PAYMENT" || r.status === "CONFIRMED") && (
                        <button disabled={isBusy} onClick={() => { if (confirm("Cancelar esta reserva?")) updateStatus(r.reservation_code, "CANCELLED"); }}
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
                    <div className="bg-indigo-50/40 border-t border-indigo-100 px-5 py-4 space-y-3 animate-fade-in">
                      {!liq ? (
                        <div className="flex justify-center py-4"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-400"/></div>
                      ) : liq.error ? (
                        <DataState kind="placeholder" title="Liquidacion no disponible" description={liq.error} />
                      ) : (
                        <>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            {[
                              { label: "Total a pagar", val: money(liq.total_charged), cls: "text-gray-800" },
                              { label: "Total pagado",  val: money(liq.total_paid),    cls: "text-emerald-700" },
                              { label: "Saldo pendiente", val: money(liq.balance),    cls: liq.balance > 0 ? "text-amber-700" : "text-emerald-700" },
                            ].map(({ label, val, cls }) => (
                              <div key={label} className="bg-white rounded-xl p-3 text-center shadow-sm ring-1 ring-gray-100">
                                <p className="text-xs text-gray-500 mb-1">{label}</p>
                                <p className={`text-base font-bold ${cls}`}>{val}</p>
                              </div>
                            ))}
                          </div>

                          {liq.payment_schedule?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-gray-600 mb-2">Cronograma</p>
                              <div className="space-y-1.5">
                                {liq.payment_schedule.map((s: any, i: number) => (
                                  <div key={i} className="flex justify-between items-center bg-white rounded-lg px-3 py-2 text-xs shadow-sm ring-1 ring-gray-100">
                                    <span className="text-gray-500">Cuota {i+1} -- vence {fmt(s.due_date)}</span>
                                    <span className="font-semibold">{money(s.amount)} <span className="text-gray-400">({s.pct}%)</span></span>
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
                                  <div key={t.id} className="flex justify-between items-center bg-white rounded-lg px-3 py-2 text-xs shadow-sm ring-1 ring-gray-100">
                                    <span className="text-gray-600 font-medium">{t.method} {t.reference && <span className="text-gray-400">-- {t.reference}</span>}</span>
                                    <div className="text-right">
                                      <p className="font-bold text-emerald-600">+{money(t.amount)}</p>
                                      <p className="text-gray-400">{fmt(t.date)}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="pt-1 border-t border-indigo-100">
                            {itinUrl ? (
                              <a href={itinUrl} target="_blank" rel="noreferrer"
                                className="flex items-center gap-2 w-full bg-indigo-600 text-white py-2 px-3 rounded-xl text-xs font-medium hover:bg-indigo-700 transition-colors">
                                <Map size={13}/> Ver itinerario PDF
                              </a>
                            ) : (
                              <p className="flex items-center gap-1.5 text-xs text-gray-400 py-1">
                                <FileText size={12}/> Itinerario no generado -- generalo desde Cotizaciones
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
