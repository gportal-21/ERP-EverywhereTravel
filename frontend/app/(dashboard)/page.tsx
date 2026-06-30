"use client";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, TrendingUp, Users, DollarSign, BookOpen, Package } from "lucide-react";
import { useRouter } from "next/navigation";
import { API, WS, authHeaders, fetchJson } from "@/lib/fetch-api";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { KpiSkeleton, Skeleton } from "@/components/ui/skeleton";
import { DataState } from "@/components/ui/data-state";

interface Alert { type: string; message: string; timestamp: string }

export default function DashboardPage() {
  const router = useRouter();
  const [health, setHealth]   = useState<any>(null);
  const [stats, setStats]     = useState<any>(null);
  const [alerts, setAlerts]   = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const loadAll = async () => {
    setLoadError("");
    try {
      const h = authHeaders();
      const [hRes, sRes] = await Promise.all([
        fetchJson<any>(`${API}/api/v1/monitoring/health`, { headers: h }),
        fetchJson<any>(`${API}/api/v1/stats/`, { headers: h }),
      ]);
      if (hRes.data) setHealth(hRes.data);
      if (sRes.data) setStats(sRes.data);
      if (hRes.error || sRes.error) setLoadError(hRes.error || sRes.error || "No se pudo cargar el resumen");
    } catch {
      setLoadError("No se pudo cargar el resumen del sistema");
    }
    setLoading(false);
  };

  useEffect(() => {
    loadAll();
    let ws: WebSocket;
    try {
      ws = new WebSocket(`${WS}/ws/system:alerts`);
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          setAlerts(p => [{ type: d.type, message: d.message || d.type, timestamp: new Date().toISOString() }, ...p.slice(0, 9)]);
        } catch {}
      };
    } catch {}
    const t = setInterval(loadAll, 20000);
    return () => { try { ws?.close(); } catch {} clearInterval(t); };
  }, []);

  const healthPct  = health ? Math.round((health.healthy_count / health.total_agents) * 100) : 0;
  const isHealthy  = healthPct >= 80;

  if (loading) return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-8 w-36 rounded-full" />
      </div>
      <KpiSkeleton />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {[1, 2, 3].map(i => (
          <div key={i} className="bg-white rounded-xl shadow p-5 space-y-3">
            <Skeleton className="h-5 w-32" />
            <div className="space-y-2">{Array.from({ length: 4 }).map((_, j) => <Skeleton key={j} className="h-8 w-full" />)}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Everywhere Travel -- Sistema Multiagente v1.0</p>
        </div>
        <StatusBadge variant={isHealthy ? "success" : "error"}>
          <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
          {isHealthy ? "Sistema operativo" : "Sistema degradado"}
        </StatusBadge>
      </div>

      {loadError && (
        <DataState
          kind="error"
          title="No se pudo refrescar toda la informacion"
          description={`${loadError}. Se muestran los ultimos datos disponibles o placeholders.`}
          actionLabel="Reintentar"
          onAction={loadAll}
        />
      )}

      {/* KPI grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={<Users size={20} className="text-blue-500"/>}   label="Clientes"   value={stats?.clients?.total ?? "--"} sub="registrados"           color="blue"   onClick={() => router.push("/clients")} />
        <KpiCard icon={<BookOpen size={20} className="text-indigo-500"/>} label="Reservas" value={stats?.reservations?.total ?? "--"} sub={`${stats?.reservations?.confirmed ?? 0} confirmadas`} color="indigo" onClick={() => router.push("/reservations")} />
        <KpiCard icon={<DollarSign size={20} className="text-emerald-500"/>} label="Revenue" value={`S/. ${(stats?.finance?.total_revenue ?? 0).toLocaleString("es-PE", { minimumFractionDigits: 0 })}`} sub="cobrado total" color="green" />
        <KpiCard icon={<AlertTriangle size={20} className="text-amber-500"/>} label="Por cobrar" value={`S/. ${(stats?.finance?.pending_balance ?? 0).toLocaleString("es-PE", { minimumFractionDigits: 0 })}`} sub="balance pendiente" color="yellow" onClick={() => router.push("/finance")} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agentes */}
        <div className="bg-white rounded-xl shadow-sm ring-1 ring-gray-100 p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm">
            <Activity size={16} className="text-blue-500"/>
            Agentes ({health?.healthy_count ?? 0}/{health?.total_agents ?? 9})
          </h2>
          <div className="space-y-1">
            {health?.agents ? Object.entries(health.agents as Record<string,string>).map(([agent, status]) => (
              <div key={agent} className="flex items-center justify-between py-2 px-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                <span className="text-xs font-mono text-gray-600 truncate pr-2">{agent.replace("-agent","")}</span>
                <StatusBadge variant={status === "HEALTHY" ? "success" : "warning"}>
                  {status}
                </StatusBadge>
              </div>
            )) : (
              <DataState kind="placeholder" title="Esperando heartbeats" description="El backend aun no envio el estado de agentes." />
            )}
          </div>
        </div>

        {/* Reservas por estado */}
        <div className="bg-white rounded-xl shadow-sm ring-1 ring-gray-100 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800 flex items-center gap-2 text-sm">
            <BookOpen size={16} className="text-indigo-500"/> Reservas
          </h2>
          {stats?.reservations ? (
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Pendientes",  val: stats.reservations.pending,   bg: "bg-amber-50",   text: "text-amber-700" },
                { label: "Confirmadas", val: stats.reservations.confirmed, bg: "bg-emerald-50",  text: "text-emerald-700" },
                { label: "Canceladas",  val: stats.reservations.cancelled, bg: "bg-red-50",      text: "text-red-600" },
              ].map(({label, val, bg, text}) => (
                <div key={label} className={`rounded-xl p-3 text-center ${bg}`}>
                  <p className={`text-xl font-bold ${text}`}>{val ?? 0}</p>
                  <p className={`text-xs font-medium mt-0.5 ${text} opacity-70`}>{label}</p>
                </div>
              ))}
            </div>
          ) : <DataState kind="placeholder" title="Sin resumen de reservas" description="Cuando el backend envie estadisticas se mostraran aqui." />}
          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Recientes</p>
            {!stats?.recent_reservations?.length && <p className="text-xs text-gray-400 py-3 text-center">Sin reservas aun</p>}
            {stats?.recent_reservations?.map((r: any) => (
              <div key={r.code} className="flex items-center justify-between text-xs py-2 px-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                <span className="font-mono text-gray-600">{r.code}</span>
                <StatusBadge variant={
                  r.status === "CONFIRMED" ? "success" :
                  r.status === "CANCELLED" ? "error" : "warning"
                }>
                  {r.status}
                </StatusBadge>
              </div>
            ))}
          </div>
        </div>

        {/* Alertas + Sagas */}
        <div className="bg-white rounded-xl shadow-sm ring-1 ring-gray-100 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800 flex items-center gap-2 text-sm">
            <TrendingUp size={16} className="text-purple-500"/> Sagas
          </h2>
          {stats?.sagas ? (
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "En curso",    val: stats.sagas.running,   bg: "bg-blue-50",     text: "text-blue-700" },
                { label: "Completadas", val: stats.sagas.completed, bg: "bg-emerald-50",  text: "text-emerald-700" },
                { label: "Fallidas",    val: stats.sagas.failed,    bg: "bg-red-50",      text: "text-red-600" },
              ].map(({label, val, bg, text}) => (
                <div key={label} className={`rounded-xl p-3 text-center ${bg}`}>
                  <p className={`text-xl font-bold ${text}`}>{val ?? 0}</p>
                  <p className={`text-xs font-medium mt-0.5 ${text} opacity-70`}>{label}</p>
                </div>
              ))}
            </div>
          ) : <DataState kind="placeholder" title="Sin resumen de sagas" description="Aparecera cuando existan ejecuciones registradas." />}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Alertas recientes</p>
            {alerts.length === 0
              ? <p className="text-xs text-gray-400 text-center py-3">Sin alertas activas</p>
              : alerts.slice(0,5).map((a,i) => (
                <div key={i} className="flex items-start gap-2 py-2 px-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                  <AlertTriangle size={12} className="text-amber-500 mt-0.5 flex-shrink-0"/>
                  <p className="text-xs text-gray-600 leading-relaxed">{a.message}</p>
                </div>
              ))
            }
          </div>
        </div>
      </div>

      {/* Resumen de paquetes */}
      <div className="bg-white rounded-xl shadow-sm ring-1 ring-gray-100 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-800 flex items-center gap-2 text-sm">
            <Package size={16} className="text-blue-500"/> Resumen general
          </h2>
          <button onClick={() => router.push("/packages")} className="text-xs text-blue-600 hover:text-blue-700 font-medium transition-colors">
            Ver paquetes
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Paquetes disponibles", val: stats?.packages?.active ?? "--", from: "from-blue-50",  to: "to-indigo-50", text: "text-blue-700",    ring: "ring-blue-100" },
            { label: "Clientes registrados", val: stats?.clients?.total ?? "--",   from: "from-emerald-50", to: "to-teal-50", text: "text-emerald-700", ring: "ring-emerald-100" },
            { label: "Sagas totales",        val: stats?.sagas?.total ?? "--",     from: "from-purple-50",  to: "to-violet-50", text: "text-purple-700",  ring: "ring-purple-100" },
            { label: "Capacidad operativa",  val: `${healthPct}%`,                 from: "from-amber-50",   to: "to-orange-50", text: "text-amber-700",   ring: "ring-amber-100" },
          ].map(({ label, val, from, to, text, ring }) => (
            <div key={label} className={`bg-gradient-to-br ${from} ${to} rounded-xl p-4 text-center ring-1 ${ring}`}>
              <p className={`text-2xl sm:text-3xl font-bold ${text}`}>{val}</p>
              <p className={`text-xs ${text} mt-1 font-medium opacity-70`}>{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, color, onClick }: {
  icon: React.ReactNode; label: string; value: any; sub: string; color: string; onClick?: () => void
}) {
  const colors: Record<string, string> = {
    blue: "ring-blue-100 hover:ring-blue-200",
    indigo: "ring-indigo-100 hover:ring-indigo-200",
    green: "ring-emerald-100 hover:ring-emerald-200",
    yellow: "ring-amber-100 hover:ring-amber-200",
  };
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-xl shadow-sm p-4 sm:p-5 ring-1 ${colors[color] || ""} ${onClick ? "cursor-pointer hover:shadow-md transition-all" : ""}`}
    >
      <div className="flex items-center justify-between mb-3">
        {icon}
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-xl sm:text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-1">{sub}</p>
    </div>
  );
}
