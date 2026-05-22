"use client";
import { useEffect, useState } from "react";
import {
  FileText, Plus, RefreshCw, Clock, CheckCircle, XCircle,
  AlertCircle, BookOpen, ChevronDown, ChevronUp, Calculator, Sparkles, Send, Map,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

const STATUS: Record<string, { label: string; cls: string; icon: any }> = {
  DRAFT:     { label: "Borrador",   cls: "bg-gray-100 text-gray-600",    icon: Clock },
  VALIDATED: { label: "Validada",   cls: "bg-green-100 text-green-700",  icon: CheckCircle },
  REJECTED:  { label: "Rechazada",  cls: "bg-red-100 text-red-700",      icon: XCircle },
  EXPIRED:   { label: "Expirada",   cls: "bg-yellow-100 text-yellow-700",icon: AlertCircle },
};

const fmt = (d: string) => d
  ? new Date(d).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" })
  : "—";

type MainTab = "list" | "new";
type NewTab  = "direct" | "agent";

export default function QuotationsPage() {
  const [mainTab, setMainTab]     = useState<MainTab>("list");
  const [newTab, setNewTab]       = useState<NewTab>("direct");
  const [quotations, setQuotations] = useState<any[]>([]);
  const [clients, setClients]     = useState<any[]>([]);
  const [packages, setPackages]   = useState<any[]>([]);
  const [loading, setLoading]     = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [reserving, setReserving]           = useState<string | null>(null);
  const [generatingItin, setGeneratingItin] = useState<string | null>(null);
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null);
  const [preview, setPreview]     = useState<any>(null);

  // Formulario cotización directa
  const [direct, setDirect] = useState({
    client_id: "", package_id: "", traveler_count: 2,
    start_date: "", end_date: "",
  });

  // Formulario consulta multiagente
  const [agent, setAgent] = useState({
    client_id: "", destination: "", start_date: "", end_date: "",
    budget_min: 1000, budget_max: 5000, traveler_count: 2, preferences: "",
  });
  const [agentResult, setAgentResult] = useState<any>(null);

  const notify = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  };

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/v1/quotations/`, { headers: authH() });
      if (r.ok) setQuotations((await r.json()).quotations || []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    load();
    Promise.all([
      fetch(`${API}/api/v1/clients/`, { headers: authH() }).then(r => r.json()),
      fetch(`${API}/api/v1/packages/`, { headers: authH() }).then(r => r.json()),
    ]).then(([c, p]) => {
      setClients(c.clients || []);
      setPackages(p.packages?.filter((pkg: any) => pkg.is_active && parseFloat(pkg.base_price) > 0) || []);
    }).catch(() => {});
  }, []);

  // Preview en tiempo real
  useEffect(() => {
    if (!direct.package_id || !direct.traveler_count) { setPreview(null); return; }
    const pkg = packages.find(p => p.id === direct.package_id);
    if (!pkg) { setPreview(null); return; }
    const base   = parseFloat(pkg.base_price) * direct.traveler_count;
    const margin = base * 0.20;
    const igv    = base * 0.18;
    setPreview({ pkg_name: pkg.name, destination: pkg.destination, duration: pkg.duration_days, base, margin, igv, total: base + margin + igv });
  }, [direct.package_id, direct.traveler_count, packages]);

  // ── Cotización directa ──────────────────────────────────────────────────
  const submitDirect = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await fetch(`${API}/api/v1/quotations/direct`, {
        method: "POST", headers: authH(), body: JSON.stringify(direct),
      });
      if (r.ok) {
        notify("Cotización creada y validada. Ya puedes reservar.");
        setMainTab("list");
        setDirect({ client_id: "", package_id: "", traveler_count: 2, start_date: "", end_date: "" });
        setPreview(null);
        load();
      } else {
        const err = await r.json();
        notify(err.detail || "Error al crear cotización", false);
      }
    } catch { notify("Error de conexión", false); }
    setSubmitting(false);
  };

  // ── Consulta multiagente ────────────────────────────────────────────────
  const submitAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setAgentResult(null);
    try {
      const payload = {
        ...agent,
        budget_min: Number(agent.budget_min),
        budget_max: Number(agent.budget_max),
        traveler_count: Number(agent.traveler_count),
        preferences: agent.preferences
          ? agent.preferences.split(",").map((s: string) => s.trim()).filter(Boolean)
          : [],
      };
      const r = await fetch(`${API}/api/v1/inquiries`, {
        method: "POST", headers: authH(), body: JSON.stringify(payload),
      });
      if (r.ok) {
        const data = await r.json();
        setAgentResult(data);
        notify("Consulta enviada al sistema multiagente. La cotización aparecerá en la lista en segundos.");
        // Auto-refrescar la lista cada 5s por 30s
        let tries = 0;
        const interval = setInterval(async () => {
          await load();
          tries++;
          if (tries >= 6) clearInterval(interval);
        }, 5000);
      } else {
        const err = await r.json();
        notify(err.detail || "Error al enviar consulta", false);
      }
    } catch { notify("Error de conexión", false); }
    setSubmitting(false);
  };

  // ── Generar itinerario PDF ─────────────────────────────────────────────
  const generateItinerary = async (quoteId: string) => {
    setGeneratingItin(quoteId);
    try {
      const r = await fetch(`${API}/api/v1/itinerary/${quoteId}`, {
        method: "POST", headers: authH(),
      });
      if (r.ok) {
        notify("Itinerario en generación. Estará listo en unos segundos.");
      } else {
        const err = await r.json();
        notify(err.detail || "Error al generar itinerario", false);
      }
    } catch { notify("Error de conexión", false); }
    setGeneratingItin(null);
  };

  // ── Reservar desde cotización ───────────────────────────────────────────
  const reserveFromQuote = async (quoteId: string, q: any) => {
    setReserving(quoteId);
    try {
      const r = await fetch(`${API}/api/v1/reservations/from-quotation`, {
        method: "POST", headers: authH(),
        body: JSON.stringify({
          quote_id: quoteId,
          start_date: q.customizations?.start_date,
          end_date: q.customizations?.end_date,
          traveler_count: q.customizations?.traveler_count,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        notify(`Reserva ${data.reservation_code} creada. Ve a Reservas para gestionar el pago.`);
      } else {
        const err = await r.json();
        notify(err.detail || "Error al crear reserva", false);
      }
    } catch { notify("Error de conexión", false); }
    setReserving(null);
  };

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="p-6 space-y-5">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 max-w-sm ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.ok ? <CheckCircle size={15}/> : <XCircle size={15}/>}
          <span>{toast.msg}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2"><FileText size={22}/> Cotizaciones</h1>
        <div className="flex gap-2">
          <button onClick={() => { setMainTab("list"); load(); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${mainTab === "list" ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"}`}>
            Lista ({quotations.length})
          </button>
          <button onClick={() => setMainTab("new")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${mainTab === "new" ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"}`}>
            <Plus size={14}/> Nueva Cotización
          </button>
        </div>
      </div>

      {/* ════════════ LISTA ════════════ */}
      {mainTab === "list" && (
        <div className="bg-white rounded-xl shadow overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b bg-gray-50">
            <span className="text-sm text-gray-500">{quotations.length} cotizaciones</span>
            <button onClick={load} className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors">
              <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"/>
            </div>
          ) : quotations.length === 0 ? (
            <div className="text-center py-16 space-y-3">
              <FileText size={40} className="mx-auto text-gray-200"/>
              <p className="text-gray-500 font-medium">Sin cotizaciones aún</p>
              <p className="text-sm text-gray-400">Crea una cotización directa o envía una consulta al sistema multiagente.</p>
              <button onClick={() => setMainTab("new")}
                className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
                <Plus size={14}/> Nueva Cotización
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {quotations.map(q => {
                const cfg  = STATUS[q.status] || STATUS.DRAFT;
                const Icon = cfg.icon;
                const isOpen = expanded === q.quote_id;
                return (
                  <div key={q.id}>
                    <div className="flex items-center gap-4 px-5 py-4 hover:bg-gray-50 transition-colors">
                      <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm min-w-0">
                        <div>
                          <p className="font-mono text-xs text-gray-400">#{q.quote_id?.slice(0, 8)}…</p>
                          <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold mt-1 ${cfg.cls}`}>
                            <Icon size={10}/>{cfg.label}
                          </span>
                        </div>
                        <div>
                          <p className="font-bold text-gray-900">S/. {parseFloat(q.total_cost).toFixed(2)}</p>
                          <p className="text-xs text-gray-400">Margen: {q.margin_pct}%</p>
                        </div>
                        <div className="text-xs text-gray-500">
                          <p>Vence: {fmt(q.valid_until)}</p>
                          <p className="text-gray-400">Creada: {fmt(q.created_at)}</p>
                        </div>
                        <div className="text-xs text-gray-400">
                          {q.customizations?.start_date
                            ? `${fmt(q.customizations.start_date)} → ${fmt(q.customizations.end_date)}`
                            : "Fechas no especificadas"}
                        </div>
                      </div>

                      <div className="flex gap-1.5 flex-shrink-0">
                        <button onClick={() => setExpanded(isOpen ? null : q.quote_id)}
                          className="flex items-center gap-1 border border-gray-200 text-gray-600 px-2.5 py-1.5 rounded-lg text-xs hover:bg-gray-50 transition-colors">
                          Desglose {isOpen ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
                        </button>
                        {q.status === "VALIDATED" && (
                          <>
                            <button
                              onClick={() => reserveFromQuote(q.quote_id, q)}
                              disabled={reserving === q.quote_id}
                              className="flex items-center gap-1 bg-green-600 text-white px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50 transition-colors">
                              <BookOpen size={11}/>
                              {reserving === q.quote_id ? "Reservando…" : "Reservar"}
                            </button>
                            <button
                              onClick={() => generateItinerary(q.quote_id)}
                              disabled={generatingItin === q.quote_id}
                              className="flex items-center gap-1 bg-indigo-600 text-white px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                              <Map size={11}/>
                              {generatingItin === q.quote_id ? "Generando…" : "Itinerario"}
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {isOpen && (
                      <div className="bg-indigo-50/50 border-t border-indigo-100 px-5 py-3">
                        {q.line_items?.length > 0 ? (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-gray-500 border-b border-indigo-100">
                                <th className="text-left pb-1.5 font-medium">Concepto</th>
                                <th className="text-right pb-1.5 font-medium">Precio unit.</th>
                                <th className="text-right pb-1.5 font-medium">Cant.</th>
                                <th className="text-right pb-1.5 font-medium">Subtotal</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-indigo-100/50">
                              {q.line_items.map((item: any, i: number) => (
                                <tr key={i} className="text-gray-600">
                                  <td className="py-1.5">{item.concept}</td>
                                  <td className="py-1.5 text-right">S/. {parseFloat(item.unit_price).toFixed(2)}</td>
                                  <td className="py-1.5 text-right">{item.quantity}</td>
                                  <td className="py-1.5 text-right font-medium">S/. {parseFloat(item.subtotal).toFixed(2)}</td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr className="font-bold text-gray-800 border-t border-indigo-200">
                                <td colSpan={3} className="pt-2">Total</td>
                                <td className="pt-2 text-right">S/. {parseFloat(q.total_cost).toFixed(2)}</td>
                              </tr>
                            </tfoot>
                          </table>
                        ) : (
                          <p className="text-xs text-gray-400 text-center py-2">Sin desglose disponible</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ════════════ NUEVA COTIZACIÓN ════════════ */}
      {mainTab === "new" && (
        <div className="space-y-5">
          {/* Selector de modo */}
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => setNewTab("direct")}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                newTab === "direct"
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Calculator size={18} className={newTab === "direct" ? "text-blue-600" : "text-gray-400"}/>
                <span className={`font-semibold text-sm ${newTab === "direct" ? "text-blue-700" : "text-gray-700"}`}>
                  Cotización Directa
                </span>
                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                  Inmediato
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Calcula el precio automáticamente usando la fórmula base + margen + IGV.
                No requiere API de IA. Estado final: <strong>VALIDATED</strong>.
              </p>
            </button>

            <button
              onClick={() => setNewTab("agent")}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                newTab === "agent"
                  ? "border-purple-500 bg-purple-50"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Sparkles size={18} className={newTab === "agent" ? "text-purple-600" : "text-gray-400"}/>
                <span className={`font-semibold text-sm ${newTab === "agent" ? "text-purple-700" : "text-gray-700"}`}>
                  Consulta Inteligente
                </span>
                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">
                  Requiere créditos
                </span>
              </div>
              <p className="text-xs text-gray-500">
                El sistema multiagente analiza la solicitud con IA y genera una cotización
                personalizada. Permite destinos y paquetes personalizados.
              </p>
            </button>
          </div>

          {/* ── MODO DIRECTO ── */}
          {newTab === "direct" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-xl shadow p-6">
                <div className="flex items-center gap-2 mb-5">
                  <Calculator size={18} className="text-blue-600"/>
                  <h2 className="font-semibold text-gray-800">Cotización Directa</h2>
                </div>

                <form onSubmit={submitDirect} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Cliente *</label>
                    <select value={direct.client_id} onChange={e => setDirect({...direct, client_id: e.target.value})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="">Selecciona un cliente…</option>
                      {clients.map(c => (
                        <option key={c.id} value={c.id}>{c.full_name} — {c.email}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Paquete *</label>
                    <select value={direct.package_id} onChange={e => setDirect({...direct, package_id: e.target.value})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="">Selecciona un paquete…</option>
                      {packages.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name} — {p.destination} — S/. {parseFloat(p.base_price).toLocaleString("es-PE")}/persona
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">N° de viajeros *</label>
                    <input type="number" min="1" max="50" value={direct.traveler_count}
                      onChange={e => setDirect({...direct, traveler_count: parseInt(e.target.value) || 1})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Fecha inicio *</label>
                      <input type="date" value={direct.start_date}
                        onChange={e => setDirect({...direct, start_date: e.target.value})} required
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Fecha fin *</label>
                      <input type="date" value={direct.end_date}
                        onChange={e => setDirect({...direct, end_date: e.target.value})} required
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    </div>
                  </div>

                  <div className="flex gap-3 pt-2">
                    <button type="button" onClick={() => setMainTab("list")}
                      className="px-4 py-2.5 border rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">
                      Cancelar
                    </button>
                    <button type="submit" disabled={submitting || !direct.client_id || !direct.package_id}
                      className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                      {submitting
                        ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/> Calculando…</>
                        : <><Calculator size={15}/> Generar Cotización</>}
                    </button>
                  </div>
                </form>
              </div>

              {/* Preview */}
              {preview ? (
                <div className="bg-white rounded-xl shadow p-6 space-y-4">
                  <div>
                    <h3 className="font-semibold text-gray-800">{preview.pkg_name}</h3>
                    <p className="text-sm text-gray-500">{preview.destination} · {preview.duration} días · {direct.traveler_count} viajero{direct.traveler_count > 1 ? "s" : ""}</p>
                  </div>
                  <div className="space-y-2 text-sm">
                    {[
                      { label: `${preview.pkg_name} × ${direct.traveler_count}`, val: preview.base,   cls: "text-gray-700" },
                      { label: "Margen de servicio (20%)",                       val: preview.margin, cls: "text-gray-500" },
                      { label: "IGV (18%)",                                       val: preview.igv,    cls: "text-gray-500" },
                    ].map(({ label, val, cls }) => (
                      <div key={label} className="flex justify-between py-1.5 border-b border-gray-50">
                        <span className={cls}>{label}</span>
                        <span className={`font-medium ${cls}`}>S/. {val.toFixed(2)}</span>
                      </div>
                    ))}
                    <div className="flex justify-between pt-2">
                      <span className="font-bold text-gray-900">Total</span>
                      <span className="font-bold text-blue-700 text-xl">S/. {preview.total.toFixed(2)}</span>
                    </div>
                  </div>
                  <div className="bg-green-50 border border-green-100 rounded-lg p-3 text-xs text-green-700 flex items-center gap-2">
                    <CheckCircle size={13}/>
                    Quedará como <strong>VALIDATED</strong> — podrás reservar inmediatamente.
                  </div>
                </div>
              ) : (
                <div className="bg-white rounded-xl shadow p-6 flex flex-col items-center justify-center text-center h-full min-h-52 text-gray-400">
                  <Calculator size={36} className="mb-3 opacity-30"/>
                  <p className="text-sm font-medium">Vista previa del precio</p>
                  <p className="text-xs mt-1">Selecciona un paquete y el N° de viajeros.</p>
                </div>
              )}
            </div>
          )}

          {/* ── MODO MULTIAGENTE ── */}
          {newTab === "agent" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-xl shadow p-6">
                <div className="flex items-center gap-2 mb-1">
                  <Sparkles size={18} className="text-purple-600"/>
                  <h2 className="font-semibold text-gray-800">Consulta Inteligente</h2>
                </div>
                <p className="text-xs text-gray-400 mb-5">
                  El sistema multiagente analiza la solicitud y genera una cotización personalizada usando IA.
                  Requiere API key de Anthropic con créditos disponibles.
                </p>

                <form onSubmit={submitAgent} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Cliente *</label>
                    <select value={agent.client_id} onChange={e => setAgent({...agent, client_id: e.target.value})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500">
                      <option value="">Selecciona un cliente…</option>
                      {clients.map(c => (
                        <option key={c.id} value={c.id}>{c.full_name} — {c.email}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Destino *</label>
                    <input type="text" placeholder="ej: Machu Picchu, Cusco" value={agent.destination}
                      onChange={e => setAgent({...agent, destination: e.target.value})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    <p className="text-xs text-gray-400 mt-1">Puede ser cualquier destino, incluso fuera del catálogo.</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Fecha inicio *</label>
                      <input type="date" value={agent.start_date}
                        onChange={e => setAgent({...agent, start_date: e.target.value})} required
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Fecha fin *</label>
                      <input type="date" value={agent.end_date}
                        onChange={e => setAgent({...agent, end_date: e.target.value})} required
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Presupuesto mín. (S/.)</label>
                      <input type="number" min="0" value={agent.budget_min}
                        onChange={e => setAgent({...agent, budget_min: Number(e.target.value)})}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Presupuesto máx. (S/.)</label>
                      <input type="number" min="1" value={agent.budget_max}
                        onChange={e => setAgent({...agent, budget_max: Number(e.target.value)})}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">N° de viajeros *</label>
                    <input type="number" min="1" max="50" value={agent.traveler_count}
                      onChange={e => setAgent({...agent, traveler_count: Number(e.target.value)})} required
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Preferencias</label>
                    <input type="text" placeholder="hotel 4*, vuelo incluido, traslados…" value={agent.preferences}
                      onChange={e => setAgent({...agent, preferences: e.target.value})}
                      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"/>
                    <p className="text-xs text-gray-400 mt-1">Separadas por comas. La IA las considerará al armar el paquete.</p>
                  </div>

                  <div className="flex gap-3 pt-2">
                    <button type="button" onClick={() => setMainTab("list")}
                      className="px-4 py-2.5 border rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">
                      Cancelar
                    </button>
                    <button type="submit" disabled={submitting || !agent.client_id || !agent.destination}
                      className="flex-1 flex items-center justify-center gap-2 bg-purple-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
                      {submitting
                        ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/> Enviando…</>
                        : <><Send size={15}/> Enviar al Sistema Multiagente</>}
                    </button>
                  </div>
                </form>
              </div>

              {/* Panel informativo / resultado */}
              <div className="space-y-4">
                {agentResult ? (
                  <div className="bg-purple-50 border border-purple-200 rounded-xl p-5 space-y-3">
                    <div className="flex items-center gap-2 text-purple-800">
                      <Sparkles size={16}/>
                      <span className="font-semibold text-sm">Consulta enviada correctamente</span>
                    </div>
                    <div className="text-xs space-y-1 text-purple-700">
                      <p><strong>Saga ID:</strong> <span className="font-mono">{agentResult.saga_id?.slice(0,16)}…</span></p>
                      <p><strong>Estado:</strong> {agentResult.status}</p>
                    </div>
                    <p className="text-xs text-purple-600">
                      La lista de cotizaciones se actualiza automáticamente cada 5 segundos.
                      El proceso multiagente puede tomar entre 5 y 30 segundos dependiendo de la complejidad.
                    </p>
                    <button onClick={() => { setMainTab("list"); setAgentResult(null); }}
                      className="text-xs text-purple-700 underline hover:no-underline">
                      Ver lista de cotizaciones →
                    </button>
                  </div>
                ) : (
                  <div className="bg-white rounded-xl shadow p-6 space-y-4">
                    <div className="flex items-center gap-2">
                      <Sparkles size={18} className="text-purple-500"/>
                      <h3 className="font-semibold text-gray-800 text-sm">¿Cómo funciona?</h3>
                    </div>
                    <ol className="space-y-3 text-xs text-gray-600">
                      {[
                        { n: 1, title: "Orchestrator Agent", desc: "Recibe la solicitud y la enruta al Sales Agent." },
                        { n: 2, title: "Sales Agent (IA)", desc: "Busca paquetes en el catálogo y construye un PackageRequest óptimo usando Claude." },
                        { n: 3, title: "Quotation Agent (IA)", desc: "Calcula el precio con desglose completo. Si el paquete es personalizado, estima componentes con IA." },
                        { n: 4, title: "Validation Agent", desc: "Verifica márgenes, fechas y compliance (R001-R012). Aprueba o rechaza la cotización." },
                        { n: 5, title: "Resultado", desc: "La cotización aparece en la lista con estado VALIDATED o REJECTED." },
                      ].map(({ n, title, desc }) => (
                        <li key={n} className="flex gap-3">
                          <span className="w-5 h-5 rounded-full bg-purple-100 text-purple-700 text-[10px] font-bold flex items-center justify-center flex-shrink-0">{n}</span>
                          <div><strong className="text-gray-700">{title}</strong> — {desc}</div>
                        </li>
                      ))}
                    </ol>
                    <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs text-amber-700 flex items-start gap-2">
                      <AlertCircle size={13} className="mt-0.5 flex-shrink-0"/>
                      Requiere API key de Anthropic con créditos. Sin créditos, los agentes usarán lógica de fallback determinístico.
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
