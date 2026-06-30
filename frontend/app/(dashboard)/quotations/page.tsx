"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import {
  FileText, Plus, RefreshCw, Clock, CheckCircle, XCircle,
  AlertCircle, BookOpen, ChevronDown, ChevronUp, Calculator,
  Sparkles, Send, Map, Cpu, ArrowRight, Zap, Shield, BarChart3,
  Server, Loader2,
} from "lucide-react";
import { API, authHeaders, fetchJson, fmt, money } from "@/lib/fetch-api";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { DataState } from "@/components/ui/data-state";

const STATUS: Record<string, { label: string; variant: "neutral" | "success" | "error" | "warning"; icon: any }> = {
  DRAFT:     { label: "Borrador",   variant: "neutral", icon: Clock },
  VALIDATED: { label: "Validada",   variant: "success", icon: CheckCircle },
  REJECTED:  { label: "Rechazada",  variant: "error",   icon: XCircle },
  EXPIRED:   { label: "Expirada",   variant: "warning", icon: AlertCircle },
};

const AGENT_META: Record<string, { label: string; icon: any; color: string }> = {
  "orchestrator-agent": { label: "Orchestrator", icon: Cpu,       color: "text-blue-600" },
  "sales-agent":        { label: "Sales Agent",  icon: Sparkles,  color: "text-purple-600" },
  "quotation-agent":    { label: "Quotation Agent", icon: Calculator, color: "text-emerald-600" },
  "validation-agent":   { label: "Validation Agent", icon: Shield,    color: "text-amber-600" },
  "itinerary-agent":    { label: "Itinerary Agent",  icon: Map,       color: "text-indigo-600" },
  "document-agent":     { label: "Document Agent",   icon: FileText,  color: "text-rose-600" },
  "finance-agent":      { label: "Finance Agent",    icon: BarChart3, color: "text-teal-600" },
};

const STEP_LABELS: Record<string, string> = {
  route_to_sales_rabbitmq: "Enrutando al agente de ventas",
  sales_package_request: "Paquete seleccionado por IA",
  quotation_calculated: "Precio calculado con desglose",
  validation_complete: "Reglas de negocio verificadas",
  pipeline_quotation_complete: "Pipeline de cotizacion completado",
  route_to_quotation_agent: "Enrutando al agente de cotizacion",
  route_to_validation_agent: "Enrutando al agente de validacion",
};

type MainTab = "list" | "new";
type NewTab  = "direct" | "agent";

interface SagaStep {
  step: string;
  agent: string;
  status: string;
  timestamp: string;
  output_ref?: string;
  error?: string;
}

interface SagaState {
  saga_id: string;
  saga_type: string;
  status: string;
  steps: SagaStep[];
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

interface AgentHistory {
  quote_id: string;
  saga?: {
    saga_id: string;
    saga_type: string;
    status: string;
    initiated_by?: string;
    created_at?: string;
    completed_at?: string;
  } | null;
  timeline: Array<{
    step: string;
    agent: string;
    status: string;
    timestamp?: string;
    output_ref?: string;
    error?: string;
    title: string;
    summary: string;
  }>;
  validation_logs: Array<{
    id: string;
    overall_status: string;
    rules_checked: Array<{ rule_id: string; passed: boolean; severity: string; message: string }>;
    compliance_flags: string[];
    audited_by_agent: string;
    audited_at?: string;
  }>;
}

export default function QuotationsPage() {
  const [mainTab, setMainTab]     = useState<MainTab>("list");
  const [newTab, setNewTab]       = useState<NewTab>("direct");
  const [quotations, setQuotations] = useState<any[]>([]);
  const [clients, setClients]     = useState<any[]>([]);
  const [packages, setPackages]   = useState<any[]>([]);
  const [loading, setLoading]     = useState(true);
  const [loadError, setLoadError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [agentHistories, setAgentHistories] = useState<Record<string, AgentHistory>>({});
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [reserving, setReserving]           = useState<string | null>(null);
  const [generatingItin, setGeneratingItin] = useState<string | null>(null);
  const [preview, setPreview]     = useState<any>(null);
  const { toast, notify } = useToast();

  // Agent pipeline state
  const [sagaId, setSagaId]       = useState<string | null>(null);
  const [saga, setSaga]           = useState<SagaState | null>(null);
  const [polling, setPolling]     = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const [direct, setDirect] = useState({
    client_id: "", package_id: "", traveler_count: 2,
    start_date: "", end_date: "",
  });

  const [agent, setAgent] = useState({
    client_id: "", destination: "", start_date: "", end_date: "",
    budget_min: 1000, budget_max: 5000, traveler_count: 2, preferences: "",
  });

  const load = async () => {
    setLoading(true);
    setLoadError("");
    const { data, error } = await fetchJson<{ quotations: any[] }>(`${API}/api/v1/quotations/`, { headers: authHeaders() });
    if (data) setQuotations(Array.isArray(data.quotations) ? data.quotations : []);
    if (error) setLoadError(error);
    setLoading(false);
  };

  useEffect(() => {
    load();
    Promise.all([
      fetchJson<{ clients: any[] }>(`${API}/api/v1/clients/`, { headers: authHeaders() }),
      fetchJson<{ packages: any[] }>(`${API}/api/v1/packages/`, { headers: authHeaders() }),
    ]).then(([c, p]) => {
      if (c.data) setClients(Array.isArray(c.data.clients) ? c.data.clients : []);
      if (p.data) setPackages((p.data.packages || []).filter((pkg: any) => pkg.is_active && parseFloat(pkg.base_price) > 0));
      if (c.error || p.error) setCatalogError(c.error || p.error || "No se pudo cargar clientes o paquetes");
    }).catch(() => setCatalogError("No se pudo cargar clientes o paquetes"));
  }, []);

  useEffect(() => {
    if (!direct.package_id || !direct.traveler_count) { setPreview(null); return; }
    const pkg = packages.find(p => p.id === direct.package_id);
    if (!pkg) { setPreview(null); return; }
    const base   = parseFloat(pkg.base_price) * direct.traveler_count;
    const margin = base * 0.20;
    const igv    = base * 0.18;
    setPreview({ pkg_name: pkg.name, destination: pkg.destination, duration: pkg.duration_days, base, margin, igv, total: base + margin + igv });
  }, [direct.package_id, direct.traveler_count, packages]);

  // Saga polling
  const pollSaga = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/api/v1/sagas/${id}`, { headers: authHeaders() });
      if (r.ok) {
        const data = await r.json();
        setSaga(data);
        if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "REQUIRES_MANUAL") {
          setPolling(false);
          if (pollRef.current) clearInterval(pollRef.current);
          load();
        }
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (polling && sagaId) {
      pollSaga(sagaId);
      pollRef.current = setInterval(() => pollSaga(sagaId), 2000);
      return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }
  }, [polling, sagaId, pollSaga]);

  const submitDirect = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await fetch(`${API}/api/v1/quotations/direct`, {
        method: "POST", headers: authHeaders(), body: JSON.stringify(direct),
      });
      if (r.ok) {
        notify("Cotizacion creada y validada. Ya puedes reservar.");
        setMainTab("list");
        setDirect({ client_id: "", package_id: "", traveler_count: 2, start_date: "", end_date: "" });
        setPreview(null);
        load();
      } else {
        const err = await r.json();
        notify(err.detail || "Error al crear cotizacion", false);
      }
    } catch { notify("Error de conexion", false); }
    setSubmitting(false);
  };

  const submitAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSaga(null);
    setSagaId(null);
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
        method: "POST", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (r.ok) {
        const data = await r.json();
        setSagaId(data.saga_id);
        setPolling(true);
        notify("Consulta enviada -- observa el progreso de los agentes.");
      } else {
        const err = await r.json();
        notify(err.detail || "Error al enviar consulta", false);
      }
    } catch { notify("Error de conexion", false); }
    setSubmitting(false);
  };

  const generateItinerary = async (quoteId: string) => {
    setGeneratingItin(quoteId);
    try {
      const r = await fetch(`${API}/api/v1/itinerary/${quoteId}`, {
        method: "POST", headers: authHeaders(),
      });
      if (r.ok) {
        notify("Itinerario en generacion. Te avisare cuando este listo.");
        for (let attempt = 0; attempt < 30; attempt++) {
          await new Promise(resolve => setTimeout(resolve, 2000));
          const status = await fetch(`${API}/api/v1/itinerary/${quoteId}`, { headers: authHeaders() });
          if (status.ok) {
            const data = await status.json();
            if (data.status === "ready") {
              notify("Itinerario listo para descargar.");
              break;
            }
          }
        }
      }
      else {
        const err = await r.json();
        notify(err.detail || "Error al generar itinerario", false);
      }
    } catch { notify("Error de conexion", false); }
    setGeneratingItin(null);
  };

  const loadAgentHistory = async (quoteId: string) => {
    if (agentHistories[quoteId]) return;
    setHistoryLoading(quoteId);
    try {
      const r = await fetch(`${API}/api/v1/quotations/${quoteId}/agent-history`, { headers: authHeaders() });
      if (r.ok) {
        const data = await r.json();
        setAgentHistories(prev => ({ ...prev, [quoteId]: data }));
      }
    } catch {}
    setHistoryLoading(null);
  };

  const toggleExpanded = (quoteId: string) => {
    const next = expanded === quoteId ? null : quoteId;
    setExpanded(next);
    if (next) loadAgentHistory(next);
  };

  const reserveFromQuote = async (quoteId: string, q: any) => {
    setReserving(quoteId);
    try {
      const r = await fetch(`${API}/api/v1/reservations/from-quotation`, {
        method: "POST", headers: authHeaders(),
        body: JSON.stringify({
          quote_id: quoteId,
          start_date: q.customizations?.start_date,
          end_date: q.customizations?.end_date,
          traveler_count: q.customizations?.traveler_count,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        notify(`Reserva ${data.reservation_code} creada.`);
      } else {
        const err = await r.json();
        notify(err.detail || "Error al crear reserva", false);
      }
    } catch { notify("Error de conexion", false); }
    setReserving(null);
  };

  const resetAgent = () => {
    setSaga(null);
    setSagaId(null);
    setPolling(false);
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const inputCls = "w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors";
  const inputClsPurple = "w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-purple-500 bg-white transition-colors";

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <Toast toast={toast} />

      <PageHeader
        icon={<FileText size={20} />}
        title="Cotizaciones"
        actions={
          <div className="flex gap-2">
            <button onClick={() => { setMainTab("list"); load(); }}
              className={`px-4 py-2.5 rounded-xl text-sm font-medium transition-colors ${mainTab === "list" ? "bg-blue-600 text-white shadow-sm" : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
              Lista ({quotations.length})
            </button>
            <button onClick={() => { setMainTab("new"); resetAgent(); }}
              className={`flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors ${mainTab === "new" ? "bg-blue-600 text-white shadow-sm" : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
              <Plus size={14}/> Nueva
            </button>
          </div>
        }
      />

      {/* ═══ LIST VIEW ═══ */}
      {mainTab === "list" && (
        <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50/50">
            <span className="text-sm text-gray-500">{quotations.length} cotizaciones</span>
            <button onClick={load} className="p-2 hover:bg-gray-200 rounded-lg transition-colors" aria-label="Refrescar">
              <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
            </button>
          </div>

          {loading ? (
            <TableSkeleton rows={4} />
          ) : loadError ? (
            <div className="p-5">
              <DataState kind="error" title="No se pudieron cargar las cotizaciones" description={loadError} actionLabel="Reintentar" onAction={load} />
            </div>
          ) : quotations.length === 0 ? (
            <EmptyState
              icon={<FileText size={32} />}
              title="Sin cotizaciones aun"
              description="Crea una cotizacion directa o envia una consulta al sistema multiagente."
              action={
                <button onClick={() => setMainTab("new")}
                  className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 shadow-sm">
                  <Plus size={14}/> Nueva Cotizacion
                </button>
              }
            />
          ) : (
            <div className="divide-y divide-gray-50">
              {quotations.map(q => {
                const cfg  = STATUS[q.status] || STATUS.DRAFT;
                const Icon = cfg.icon;
                const isOpen = expanded === q.quote_id;
                return (
                  <div key={q.id || q.quote_id}>
                    <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-5 py-4 hover:bg-gray-50/50 transition-colors">
                      <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm min-w-0">
                        <div>
                          <p className="font-mono text-xs text-gray-500">#{q.quote_id?.slice(0, 8)}</p>
                          <div className="mt-1">
                            <StatusBadge variant={cfg.variant} icon={<Icon size={10}/>}>{cfg.label}</StatusBadge>
                          </div>
                        </div>
                        <div>
                          <p className="font-bold text-gray-900">{money(q.total_cost)}</p>
                          <p className="text-xs text-gray-500">Margen: {q.margin_pct}%</p>
                        </div>
                        <div className="text-xs text-gray-500">
                          <p>Vence: {fmt(q.valid_until)}</p>
                          <p className="text-gray-400">Creada: {fmt(q.created_at)}</p>
                        </div>
                        <div className="text-xs text-gray-500">
                          {q.customizations?.start_date
                            ? `${fmt(q.customizations.start_date)} - ${fmt(q.customizations.end_date)}`
                            : "Fechas no especificadas"}
                        </div>
                      </div>
                      <div className="flex gap-1.5 flex-shrink-0 flex-wrap">
                        <button onClick={() => toggleExpanded(q.quote_id)}
                          className="flex items-center gap-1 border border-gray-200 text-gray-600 px-3 py-1.5 rounded-lg text-xs hover:bg-gray-50 transition-colors">
                          Detalle {isOpen ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
                        </button>
                        {q.status === "VALIDATED" && (
                          <>
                            <button onClick={() => reserveFromQuote(q.quote_id, q)} disabled={reserving === q.quote_id}
                              className="flex items-center gap-1 bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors">
                              <BookOpen size={11}/>{reserving === q.quote_id ? "Reservando..." : "Reservar"}
                            </button>
                            <button onClick={() => generateItinerary(q.quote_id)} disabled={generatingItin === q.quote_id}
                              className="flex items-center gap-1 bg-indigo-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                              <Map size={11}/>{generatingItin === q.quote_id ? "Generando..." : "Itinerario"}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {isOpen && (
                      <div className="bg-indigo-50/40 border-t border-indigo-100 px-5 py-4 animate-fade-in space-y-5">
                        {q.line_items?.length > 0 ? (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-gray-500 border-b border-indigo-100">
                                <th className="text-left pb-2 font-medium">Concepto</th>
                                <th className="text-right pb-2 font-medium">Precio unit.</th>
                                <th className="text-right pb-2 font-medium">Cant.</th>
                                <th className="text-right pb-2 font-medium">Subtotal</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-indigo-100/50">
                              {q.line_items.map((item: any, i: number) => (
                                <tr key={i} className="text-gray-600">
                                  <td className="py-2">{item.concept}</td>
                                  <td className="py-2 text-right">S/. {parseFloat(item.unit_price).toFixed(2)}</td>
                                  <td className="py-2 text-right">{item.quantity}</td>
                                  <td className="py-2 text-right font-medium">S/. {parseFloat(item.subtotal).toFixed(2)}</td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr className="font-bold text-gray-800 border-t border-indigo-200">
                                <td colSpan={3} className="pt-2">Total</td>
                                <td className="pt-2 text-right">{money(q.total_cost)}</td>
                              </tr>
                            </tfoot>
                          </table>
                        ) : (
                          <p className="text-xs text-gray-400 text-center py-2">Sin desglose disponible</p>
                        )}
                        <AgentHistoryPanel
                          history={agentHistories[q.quote_id]}
                          loading={historyLoading === q.quote_id}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ═══ NEW QUOTATION VIEW ═══ */}
      {mainTab === "new" && (
        <div className="space-y-5">
          {/* Mode selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button onClick={() => { setNewTab("direct"); resetAgent(); }}
              className={`p-4 rounded-2xl border-2 text-left transition-all ${
                newTab === "direct" ? "border-blue-500 bg-blue-50/50 shadow-sm" : "border-gray-200 bg-white hover:border-gray-300"
              }`}>
              <div className="flex items-center gap-2 mb-1">
                <Calculator size={18} className={newTab === "direct" ? "text-blue-600" : "text-gray-400"}/>
                <span className={`font-semibold text-sm ${newTab === "direct" ? "text-blue-700" : "text-gray-700"}`}>Cotizacion Directa</span>
                <StatusBadge variant="success">Inmediato</StatusBadge>
              </div>
              <p className="text-xs text-gray-500 mt-1">Calcula automaticamente: base + margen + IGV. Estado final: VALIDATED.</p>
            </button>

            <button onClick={() => setNewTab("agent")}
              className={`p-4 rounded-2xl border-2 text-left transition-all ${
                newTab === "agent" ? "border-purple-500 bg-purple-50/50 shadow-sm" : "border-gray-200 bg-white hover:border-gray-300"
              }`}>
              <div className="flex items-center gap-2 mb-1">
                <Sparkles size={18} className={newTab === "agent" ? "text-purple-600" : "text-gray-400"}/>
                <span className={`font-semibold text-sm ${newTab === "agent" ? "text-purple-700" : "text-gray-700"}`}>Consulta Inteligente</span>
                <StatusBadge variant="purple">IA + Qwen3</StatusBadge>
              </div>
              <p className="text-xs text-gray-500 mt-1">5 agentes de IA procesan tu solicitud en tiempo real con modelo local gratuito.</p>
            </button>
          </div>

          {catalogError && (
            <DataState
              kind="error"
              title="No se pudo cargar todo el catalogo"
              description={`${catalogError}. Puedes refrescar la lista o revisar el backend.`}
              actionLabel="Reintentar"
              onAction={() => window.location.reload()}
            />
          )}

          {/* ── DIRECT MODE ── */}
          {newTab === "direct" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5 sm:p-6">
                <div className="flex items-center gap-2 mb-5">
                  <Calculator size={18} className="text-blue-600"/>
                  <h2 className="font-semibold text-gray-800 text-sm">Cotizacion Directa</h2>
                </div>
                <form onSubmit={submitDirect} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Cliente *</label>
                    <select value={direct.client_id} onChange={e => setDirect({...direct, client_id: e.target.value})} required className={inputCls}>
                      <option value="">Selecciona un cliente...</option>
                      {clients.length === 0 && <option value="" disabled>No hay clientes disponibles</option>}
                      {clients.map(c => <option key={c.id} value={c.id}>{c.full_name} -- {c.email}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Paquete *</label>
                    <select value={direct.package_id} onChange={e => setDirect({...direct, package_id: e.target.value})} required className={inputCls}>
                      <option value="">Selecciona un paquete...</option>
                      {packages.length === 0 && <option value="" disabled>No hay paquetes con precio base</option>}
                      {packages.map(p => <option key={p.id} value={p.id}>{p.name} -- {p.destination} -- {money(p.base_price)}/persona</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">N. de viajeros *</label>
                    <input type="number" min="1" max="50" value={direct.traveler_count}
                      onChange={e => setDirect({...direct, traveler_count: parseInt(e.target.value) || 1})} required className={inputCls}/>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">Fecha inicio *</label>
                      <input type="date" value={direct.start_date} onChange={e => setDirect({...direct, start_date: e.target.value})} required className={inputCls}/>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">Fecha fin *</label>
                      <input type="date" value={direct.end_date} onChange={e => setDirect({...direct, end_date: e.target.value})} required className={inputCls}/>
                    </div>
                  </div>
                  <div className="flex gap-3 pt-2">
                    <button type="button" onClick={() => setMainTab("list")}
                      className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">Cancelar</button>
                    <button type="submit" disabled={submitting || !direct.client_id || !direct.package_id}
                      className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm">
                      {submitting
                        ? <><Loader2 size={15} className="animate-spin"/> Calculando...</>
                        : <><Calculator size={15}/> Generar Cotizacion</>}
                    </button>
                  </div>
                </form>
              </div>
              {preview ? (
                <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5 sm:p-6 space-y-4">
                  <div>
                    <h3 className="font-semibold text-gray-800">{preview.pkg_name}</h3>
                    <p className="text-sm text-gray-500">{preview.destination} -- {preview.duration} dias -- {direct.traveler_count} viajero{direct.traveler_count > 1 ? "s" : ""}</p>
                  </div>
                  <div className="space-y-2 text-sm">
                    {[
                      { label: `${preview.pkg_name} x ${direct.traveler_count}`, val: preview.base, cls: "text-gray-700" },
                      { label: "Margen de servicio (20%)", val: preview.margin, cls: "text-gray-500" },
                      { label: "IGV (18%)", val: preview.igv, cls: "text-gray-500" },
                    ].map(({ label, val, cls }) => (
                      <div key={label} className="flex justify-between py-2 border-b border-gray-100">
                        <span className={cls}>{label}</span>
                        <span className={`font-medium ${cls}`}>{money(val)}</span>
                      </div>
                    ))}
                    <div className="flex justify-between pt-2">
                      <span className="font-bold text-gray-900">Total</span>
                      <span className="font-bold text-blue-700 text-xl">{money(preview.total)}</span>
                    </div>
                  </div>
                  <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-3 text-xs text-emerald-700 flex items-center gap-2">
                    <CheckCircle size={13}/> Quedara como <strong>VALIDATED</strong> -- podras reservar inmediatamente.
                  </div>
                </div>
              ) : (
                <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-6 flex flex-col items-center justify-center text-center h-full min-h-52 text-gray-400">
                  <Calculator size={36} className="mb-3 opacity-30"/>
                  <p className="text-sm font-medium text-gray-500">Vista previa del precio</p>
                  <p className="text-xs mt-1 text-gray-400">Selecciona un paquete y el N. de viajeros.</p>
                </div>
              )}
            </div>
          )}

          {/* ── AGENT MODE ── */}
          {newTab === "agent" && (
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              {/* Form - 2 cols */}
              <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5 sm:p-6">
                <div className="flex items-center gap-2 mb-1">
                  <Sparkles size={18} className="text-purple-600"/>
                  <h2 className="font-semibold text-gray-800 text-sm">Consulta Inteligente</h2>
                </div>
                <div className="flex items-center gap-2 mb-5">
                  <Server size={12} className="text-gray-400"/>
                  <p className="text-xs text-gray-400">Qwen3 8B via OpenRouter (gratuito)</p>
                </div>

                <form onSubmit={submitAgent} className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Cliente *</label>
                    <select value={agent.client_id} onChange={e => setAgent({...agent, client_id: e.target.value})} required className={inputClsPurple}>
                      <option value="">Selecciona...</option>
                      {clients.length === 0 && <option value="" disabled>No hay clientes disponibles</option>}
                      {clients.map(c => <option key={c.id} value={c.id}>{c.full_name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Destino *</label>
                    <input type="text" placeholder="ej: Machu Picchu, Cusco" value={agent.destination}
                      onChange={e => setAgent({...agent, destination: e.target.value})} required className={inputClsPurple}/>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Inicio *</label>
                      <input type="date" value={agent.start_date} onChange={e => setAgent({...agent, start_date: e.target.value})} required className={inputClsPurple}/>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Fin *</label>
                      <input type="date" value={agent.end_date} onChange={e => setAgent({...agent, end_date: e.target.value})} required className={inputClsPurple}/>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Presup. min (S/.)</label>
                      <input type="number" min="0" value={agent.budget_min} onChange={e => setAgent({...agent, budget_min: Number(e.target.value)})} className={inputClsPurple}/>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Presup. max (S/.)</label>
                      <input type="number" min="1" value={agent.budget_max} onChange={e => setAgent({...agent, budget_max: Number(e.target.value)})} className={inputClsPurple}/>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Viajeros *</label>
                    <input type="number" min="1" max="50" value={agent.traveler_count}
                      onChange={e => setAgent({...agent, traveler_count: Number(e.target.value)})} required className={inputClsPurple}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Preferencias</label>
                    <input type="text" placeholder="hotel 4*, vuelo incluido..." value={agent.preferences}
                      onChange={e => setAgent({...agent, preferences: e.target.value})} className={inputClsPurple}/>
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button type="button" onClick={() => setMainTab("list")}
                      className="px-3 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors">Cancelar</button>
                    <button type="submit" disabled={submitting || polling || !agent.client_id || !agent.destination}
                      className="flex-1 flex items-center justify-center gap-2 bg-purple-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors shadow-sm">
                      {submitting
                        ? <><Loader2 size={15} className="animate-spin"/> Enviando...</>
                        : <><Send size={15}/> Enviar</>}
                    </button>
                  </div>
                </form>
              </div>

              {/* Agent Timeline - 3 cols */}
              <div className="lg:col-span-3 space-y-4">
                {sagaId && saga ? (
                  <AgentTimeline saga={saga} onViewList={() => { setMainTab("list"); resetAgent(); load(); }} />
                ) : sagaId && !saga ? (
                  <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-8 flex flex-col items-center justify-center">
                    <Loader2 size={28} className="animate-spin text-purple-500 mb-3" />
                    <p className="text-sm text-gray-600 font-medium">Conectando con los agentes...</p>
                    <p className="text-xs text-gray-400 mt-1">Saga: {sagaId.slice(0, 16)}</p>
                  </div>
                ) : (
                  <AgentInfoPanel />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══ AGENT TIMELINE COMPONENT ═══ */

function AgentHistoryPanel({ history, loading }: { history?: AgentHistory; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-indigo-100 p-4 flex items-center gap-2 text-sm text-gray-500">
        <Loader2 size={15} className="animate-spin text-indigo-500" />
        Cargando historial de agentes...
      </div>
    );
  }

  if (!history) {
    return (
      <div className="bg-white rounded-xl border border-indigo-100 p-4 text-sm text-gray-400">
        Historial de agentes no disponible para esta cotizacion.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-indigo-100 p-4 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
            <Cpu size={14} className="text-indigo-600" />
            Historial de trabajo de agentes
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Auditoria operativa: entradas, decisiones y salidas registradas por el flujo.
          </p>
        </div>
        {history.saga && (
          <StatusBadge variant={history.saga.status === "COMPLETED" ? "success" : "warning"}>
            {history.saga.status}
          </StatusBadge>
        )}
      </div>

      {history.saga && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-2">
            <span className="text-gray-400 block">Saga</span>
            <span className="font-mono text-gray-700">{history.saga.saga_id.slice(0, 18)}</span>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-2">
            <span className="text-gray-400 block">Tipo</span>
            <span className="text-gray-700">{history.saga.saga_type}</span>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-2">
            <span className="text-gray-400 block">Inicio</span>
            <span className="text-gray-700">{fmt(history.saga.created_at || "")}</span>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {history.timeline.map((item, i) => {
          const meta = AGENT_META[item.agent] || { label: item.agent, icon: Cpu, color: "text-gray-600" };
          const StepIcon = meta.icon;
          const ok = item.status === "COMPLETED" || item.status === "VALIDATED";
          const failed = item.status === "FAILED" || item.status === "REJECTED" || item.status === "BLOCKED";
          return (
            <div key={`${item.step}-${i}`} className="flex gap-3 rounded-lg border border-gray-100 bg-gray-50/60 p-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                ok ? "bg-emerald-100" : failed ? "bg-red-100" : "bg-amber-100"
              }`}>
                <StepIcon size={15} className={meta.color} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-800">{item.title}</span>
                  <span className="text-xs text-gray-400">{meta.label}</span>
                  {item.timestamp && <span className="text-xs text-gray-400">{new Date(item.timestamp).toLocaleTimeString("es-PE")}</span>}
                </div>
                <p className="text-xs text-gray-600 mt-1 leading-relaxed">{item.summary}</p>
                {item.output_ref && <p className="text-xs text-gray-400 font-mono mt-1">ref: {item.output_ref}</p>}
                {item.error && <p className="text-xs text-red-600 mt-1">{item.error}</p>}
              </div>
              <StatusBadge variant={ok ? "success" : failed ? "error" : "warning"}>{item.status}</StatusBadge>
            </div>
          );
        })}
      </div>

      {history.validation_logs.length > 0 && (
        <div className="border-t border-gray-100 pt-3">
          <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <Shield size={13} className="text-amber-600" />
            Reglas verificadas
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {history.validation_logs[0].rules_checked.map(rule => (
              <div key={rule.rule_id} className="rounded-lg border border-gray-100 p-2 text-xs bg-white flex items-start gap-2">
                {rule.passed
                  ? <CheckCircle size={13} className="text-emerald-600 mt-0.5 flex-shrink-0" />
                  : <AlertCircle size={13} className="text-red-600 mt-0.5 flex-shrink-0" />}
                <div>
                  <p className="font-medium text-gray-800">{rule.rule_id} · {rule.severity}</p>
                  <p className="text-gray-500">{rule.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AgentTimeline({ saga, onViewList }: { saga: SagaState; onViewList: () => void }) {
  const isRunning = saga.status === "RUNNING";
  const isCompleted = saga.status === "COMPLETED";
  const isFailed = saga.status === "FAILED";

  const elapsed = (() => {
    const start = new Date(saga.created_at).getTime();
    const end = saga.completed_at ? new Date(saga.completed_at).getTime() : Date.now();
    return ((end - start) / 1000).toFixed(1);
  })();

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className={`rounded-2xl p-4 ring-1 ${
        isCompleted ? "bg-emerald-50/50 ring-emerald-200" :
        isFailed ? "bg-red-50/50 ring-red-200" :
        "bg-purple-50/50 ring-purple-200"
      }`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 size={16} className="animate-spin text-purple-600" />}
            {isCompleted && <CheckCircle size={16} className="text-emerald-600" />}
            {isFailed && <XCircle size={16} className="text-red-600" />}
            <span className={`font-semibold text-sm ${
              isCompleted ? "text-emerald-800" : isFailed ? "text-red-800" : "text-purple-800"
            }`}>
              {isRunning ? "Agentes procesando..." : isCompleted ? "Cotizacion generada" : "Error en el procesamiento"}
            </span>
          </div>
          <StatusBadge variant={isCompleted ? "success" : isFailed ? "error" : "purple"}>
            {elapsed}s
          </StatusBadge>
        </div>
        <p className="text-xs text-gray-500 font-mono">Saga: {saga.saga_id.slice(0, 24)}</p>
      </div>

      {/* Steps timeline */}
      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
        <h3 className="text-sm font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Zap size={14} className="text-purple-500"/> Actividad de los agentes
        </h3>

        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[15px] top-2 bottom-2 w-px bg-gray-200" />

          <div className="space-y-0">
            {saga.steps.length === 0 && isRunning && (
              <div className="flex items-center gap-3 py-3 pl-1">
                <div className="relative z-10 w-[30px] h-[30px] rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                  <Loader2 size={14} className="animate-spin text-purple-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-700 font-medium">Orchestrator Agent</p>
                  <p className="text-xs text-gray-400">Recibiendo solicitud y enrutando a los agentes...</p>
                </div>
              </div>
            )}

            {saga.steps.map((step, i) => {
              const meta = AGENT_META[step.agent] || { label: step.agent, icon: Cpu, color: "text-gray-600" };
              const StepIcon = meta.icon;
              const isLast = i === saga.steps.length - 1;
              const stepLabel = STEP_LABELS[step.step] || step.step.replace(/_/g, " ");
              const stepTime = new Date(step.timestamp).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
              const isStepOk = step.status === "COMPLETED";
              const isStepFail = step.status === "FAILED" || step.status === "BLOCKED";

              return (
                <div key={i} className="flex items-start gap-3 py-2.5 pl-1 group">
                  {/* Node */}
                  <div className={`relative z-10 w-[30px] h-[30px] rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
                    isStepOk ? "bg-emerald-100" :
                    isStepFail ? "bg-red-100" :
                    "bg-amber-100"
                  }`}>
                    {isStepOk ? <CheckCircle size={14} className="text-emerald-600" /> :
                     isStepFail ? <XCircle size={14} className="text-red-500" /> :
                     <Clock size={14} className="text-amber-500" />}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <StepIcon size={13} className={meta.color} />
                      <span className="text-sm font-medium text-gray-800">{meta.label}</span>
                      <span className="text-xs text-gray-400">{stepTime}</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">{stepLabel}</p>
                    {step.output_ref && (
                      <p className="text-xs text-gray-400 font-mono mt-0.5">ref: {step.output_ref}</p>
                    )}
                    {step.error && (
                      <p className="text-xs text-red-600 mt-0.5">{step.error}</p>
                    )}
                  </div>

                  {/* Status */}
                  <div className="flex-shrink-0">
                    <StatusBadge variant={isStepOk ? "success" : isStepFail ? "error" : "warning"}>
                      {step.status}
                    </StatusBadge>
                  </div>
                </div>
              );
            })}

            {/* Active indicator when running and has steps */}
            {isRunning && saga.steps.length > 0 && (
              <div className="flex items-center gap-3 py-2.5 pl-1">
                <div className="relative z-10 w-[30px] h-[30px] rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                  <Loader2 size={14} className="animate-spin text-purple-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Procesando siguiente paso...</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Result actions */}
      {(isCompleted || isFailed) && (
        <div className={`rounded-2xl p-4 ring-1 flex items-center justify-between ${
          isCompleted ? "bg-emerald-50/50 ring-emerald-200" : "bg-red-50/50 ring-red-200"
        }`}>
          <div className="flex items-center gap-2">
            {isCompleted ? <CheckCircle size={16} className="text-emerald-600"/> : <AlertCircle size={16} className="text-red-600"/>}
            <span className={`text-sm font-medium ${isCompleted ? "text-emerald-800" : "text-red-800"}`}>
              {isCompleted
                ? `Procesado en ${elapsed}s -- ${saga.steps.length} pasos completados`
                : saga.error_message || "Error durante el procesamiento"}
            </span>
          </div>
          <button onClick={onViewList}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium transition-colors ${
              isCompleted ? "bg-emerald-600 text-white hover:bg-emerald-700" : "bg-gray-600 text-white hover:bg-gray-700"
            }`}>
            Ver cotizaciones <ArrowRight size={12}/>
          </button>
        </div>
      )}
    </div>
  );
}

/* ═══ AGENT INFO PANEL (before submission) ═══ */

function AgentInfoPanel() {
  const [recentSagas, setRecentSagas] = useState<SagaState[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const agents = [
    { icon: Cpu,        color: "bg-blue-100 text-blue-600",    label: "Orchestrator", desc: "Recibe la solicitud y coordina el flujo entre agentes. Decide la ruta optima." },
    { icon: Sparkles,   color: "bg-purple-100 text-purple-600", label: "Sales Agent",  desc: "Busca en el catalogo y selecciona el mejor paquete usando Qwen3." },
    { icon: Calculator, color: "bg-emerald-100 text-emerald-600", label: "Quotation Agent", desc: "Calcula precio con desglose: base + margen (20%) + IGV (18%)." },
    { icon: Shield,     color: "bg-amber-100 text-amber-600",  label: "Validation Agent", desc: "Verifica margenes, fechas, limites y reglas de negocio (R001-R012)." },
  ];

  useEffect(() => {
    const loadRecentSagas = async () => {
      setLoadingRecent(true);
      try {
        const r = await fetch(`${API}/api/v1/sagas`, { headers: authHeaders() });
        if (r.ok) {
          const data = await r.json();
          setRecentSagas((data.sagas || []).filter((s: SagaState) => s.steps?.length > 0).slice(0, 4));
        }
      } catch {}
      setLoadingRecent(false);
    };
    loadRecentSagas();
  }, []);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-4">
          <Zap size={16} className="text-purple-500"/>
          <h3 className="font-semibold text-gray-800 text-sm">Pipeline multiagente</h3>
        </div>
        <div className="space-y-3">
          {agents.map((a, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="relative">
                <div className={`w-9 h-9 rounded-xl ${a.color} flex items-center justify-center flex-shrink-0`}>
                  <a.icon size={16} />
                </div>
                {i < agents.length - 1 && (
                  <div className="absolute left-1/2 -translate-x-1/2 top-full w-px h-3 bg-gray-200" />
                )}
              </div>
              <div className="pt-0.5">
                <p className="text-sm font-medium text-gray-800">{a.label}</p>
                <p className="text-xs text-gray-500 leading-relaxed">{a.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-indigo-500" />
            <h3 className="font-semibold text-gray-800 text-sm">Historial reciente de agentes</h3>
          </div>
          {loadingRecent && <Loader2 size={14} className="animate-spin text-indigo-500" />}
        </div>

        {recentSagas.length === 0 && !loadingRecent ? (
          <p className="text-xs text-gray-400">Aun no hay ejecuciones multiagente registradas.</p>
        ) : (
          <div className="space-y-3">
            {recentSagas.map(run => {
              const lastStep = run.steps[run.steps.length - 1];
              const quoteRef = run.steps.find(step => step.output_ref?.startsWith("quote:"))?.output_ref;
              return (
                <div key={run.saga_id} className="rounded-xl border border-gray-100 bg-gray-50/60 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {run.saga_type || "PackageInquiry"}
                      </p>
                      <p className="text-xs text-gray-400 font-mono">
                        {run.saga_id.slice(0, 18)}
                      </p>
                    </div>
                    <StatusBadge variant={run.status === "COMPLETED" ? "success" : run.status === "FAILED" ? "error" : "warning"}>
                      {run.status}
                    </StatusBadge>
                  </div>

                  <div className="mt-3 space-y-2">
                    {run.steps.slice(-4).map((step, index) => {
                      const meta = AGENT_META[step.agent] || { label: step.agent, icon: Cpu, color: "text-gray-600" };
                      const StepIcon = meta.icon;
                      return (
                        <div key={`${run.saga_id}-${step.step}-${index}`} className="flex items-start gap-2">
                          <div className="w-6 h-6 rounded-lg bg-white border border-gray-100 flex items-center justify-center flex-shrink-0">
                            <StepIcon size={12} className={meta.color} />
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-gray-700">{meta.label}</p>
                            <p className="text-xs text-gray-500 truncate">
                              {STEP_LABELS[step.step] || step.step.replace(/_/g, " ")}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
                    <span>{fmt(run.created_at)}</span>
                    <span>{quoteRef ? quoteRef.replace("quote:", "").slice(0, 13) : lastStep?.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-2xl p-4 ring-1 ring-purple-100">
        <div className="flex items-start gap-2.5">
          <Server size={14} className="text-purple-500 mt-0.5 flex-shrink-0"/>
          <div className="text-xs text-purple-700 space-y-1">
            <p className="font-medium">Motor de IA: Qwen3 8B via OpenRouter</p>
            <p className="text-purple-600">Modelo open-source gratuito. Si la API no esta disponible, los agentes usan logica de fallback deterministica.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
