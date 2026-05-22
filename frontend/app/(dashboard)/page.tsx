"use client";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, TrendingUp, Users, DollarSign, BookOpen, Package } from "lucide-react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS  = process.env.NEXT_PUBLIC_WS_URL  || "ws://localhost:8000";

const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = {};
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

interface Alert { type: string; message: string; timestamp: string }

export default function DashboardPage() {
  const router = useRouter();
  const [health, setHealth]   = useState<any>(null);
  const [stats, setStats]     = useState<any>(null);
  const [alerts, setAlerts]   = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAll = async () => {
    try {
      const [h, s] = await Promise.all([
        fetch(`${API}/api/v1/monitoring/health`,  { headers: authH() }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/api/v1/stats/`,             { headers: authH() }).then(r => r.ok ? r.json() : null),
      ]);
      if (h) setHealth(h);
      if (s) setStats(s);
    } catch {}
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

  if (loading) return (
    <div className="flex items-center justify-center h-screen">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
    </div>
  );

  const healthPct  = health ? Math.round((health.healthy_count / health.total_agents) * 100) : 0;
  const isHealthy  = healthPct >= 80;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-0.5">Everywhere Travel — Sistema Multiagente v1.0</p>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${isHealthy ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
          <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          {isHealthy ? "Sistema operativo" : "Sistema degradado"}
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={<Users size={20} className="text-blue-500"/>}   label="Clientes"   value={stats?.clients?.total ?? "—"} sub="registrados"           color="blue"   onClick={() => router.push("/clients")} />
        <KpiCard icon={<BookOpen size={20} className="text-indigo-500"/>} label="Reservas" value={stats?.reservations?.total ?? "—"} sub={`${stats?.reservations?.confirmed ?? 0} confirmadas`} color="indigo" onClick={() => router.push("/reservations")} />
        <KpiCard icon={<DollarSign size={20} className="text-green-500"/>} label="Revenue" value={`S/. ${(stats?.finance?.total_revenue ?? 0).toLocaleString("es-PE", { minimumFractionDigits: 0 })}`} sub="cobrado total" color="green" />
        <KpiCard icon={<AlertTriangle size={20} className="text-yellow-500"/>} label="Por cobrar" value={`S/. ${(stats?.finance?.pending_balance ?? 0).toLocaleString("es-PE", { minimumFractionDigits: 0 })}`} sub="balance pendiente" color="yellow" onClick={() => router.push("/finance")} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agentes */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold text-gray-700 mb-4 flex items-center gap-2"><Activity size={16}/> Agentes ({health?.healthy_count ?? 0}/{health?.total_agents ?? 9})</h2>
          <div className="space-y-1.5">
            {health && Object.entries(health.agents as Record<string,string>).map(([agent, status]) => (
              <div key={agent} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                <span className="text-xs font-mono text-gray-500 truncate pr-2">{agent.replace("-agent","")}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0 ${status === "HEALTHY" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>{status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Reservas por estado + últimas */}
        <div className="bg-white rounded-xl shadow p-5 space-y-4">
          <h2 className="font-semibold text-gray-700 flex items-center gap-2"><BookOpen size={16}/> Reservas</h2>
          {stats?.reservations && (
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                { label: "Pendientes", val: stats.reservations.pending,   cls: "bg-yellow-50 text-yellow-700" },
                { label: "Confirmadas", val: stats.reservations.confirmed, cls: "bg-green-50 text-green-700" },
                { label: "Canceladas",  val: stats.reservations.cancelled, cls: "bg-red-50 text-red-600" },
              ].map(({label,val,cls}) => (
                <div key={label} className={`rounded-lg p-2 ${cls}`}>
                  <p className="text-xl font-bold">{val ?? 0}</p>
                  <p className="text-[10px] font-medium mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Últimas reservas</p>
            {stats?.recent_reservations?.length === 0 && <p className="text-xs text-gray-400 py-2 text-center">Sin reservas aún</p>}
            {stats?.recent_reservations?.map((r: any) => (
              <div key={r.code} className="flex items-center justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                <span className="font-mono text-gray-600">{r.code}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                  r.status==="CONFIRMED" ? "bg-green-100 text-green-700" :
                  r.status==="CANCELLED" ? "bg-red-100 text-red-600" :
                  "bg-yellow-100 text-yellow-700"}`}>{r.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Alertas + Sagas */}
        <div className="bg-white rounded-xl shadow p-5 space-y-4">
          <h2 className="font-semibold text-gray-700 flex items-center gap-2"><TrendingUp size={16}/> Sagas</h2>
          {stats?.sagas && (
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                { label: "En curso",    val: stats.sagas.running,   cls: "bg-blue-50 text-blue-700" },
                { label: "Completadas", val: stats.sagas.completed,  cls: "bg-green-50 text-green-700" },
                { label: "Fallidas",    val: stats.sagas.failed,     cls: "bg-red-50 text-red-600" },
              ].map(({label,val,cls}) => (
                <div key={label} className={`rounded-lg p-2 ${cls}`}>
                  <p className="text-xl font-bold">{val ?? 0}</p>
                  <p className="text-[10px] font-medium mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          )}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Alertas recientes</p>
            {alerts.length === 0
              ? <p className="text-xs text-gray-400 text-center py-3">Sin alertas activas</p>
              : alerts.slice(0,5).map((a,i) => (
                <div key={i} className="flex items-start gap-2 py-1.5 border-b border-gray-50 last:border-0">
                  <AlertTriangle size={11} className="text-yellow-500 mt-0.5 flex-shrink-0"/>
                  <p className="text-xs text-gray-600 truncate">{a.message}</p>
                </div>
              ))
            }
          </div>
        </div>
      </div>

      {/* Paquetes activos */}
      <div className="bg-white rounded-xl shadow p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-700 flex items-center gap-2"><Package size={16}/> Paquetes activos</h2>
          <button onClick={() => router.push("/packages")} className="text-xs text-blue-600 hover:underline">Ver todos →</button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 text-center border border-blue-100">
            <p className="text-3xl font-bold text-blue-700">{stats?.packages?.active ?? "—"}</p>
            <p className="text-xs text-blue-500 mt-1 font-medium">Paquetes disponibles</p>
          </div>
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl p-4 text-center border border-green-100">
            <p className="text-3xl font-bold text-green-700">{stats?.clients?.total ?? "—"}</p>
            <p className="text-xs text-green-500 mt-1 font-medium">Clientes registrados</p>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-violet-50 rounded-xl p-4 text-center border border-purple-100">
            <p className="text-3xl font-bold text-purple-700">{stats?.sagas?.total ?? "—"}</p>
            <p className="text-xs text-purple-500 mt-1 font-medium">Sagas totales</p>
          </div>
          <div className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-xl p-4 text-center border border-orange-100">
            <p className="text-3xl font-bold text-orange-700">{healthPct}%</p>
            <p className="text-xs text-orange-500 mt-1 font-medium">Capacidad operativa</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, color, onClick }: {
  icon: React.ReactNode; label: string; value: any; sub: string; color: string; onClick?: () => void
}) {
  const colors: Record<string, string> = {
    blue: "border-blue-100 hover:border-blue-200", indigo: "border-indigo-100 hover:border-indigo-200",
    green: "border-green-100 hover:border-green-200", yellow: "border-yellow-100 hover:border-yellow-200",
  };
  return (
    <div onClick={onClick} className={`bg-white rounded-xl shadow p-5 border ${colors[color] || ""} ${onClick ? "cursor-pointer hover:shadow-md transition-all" : ""}`}>
      <div className="flex items-center justify-between mb-3">{icon}<span className="text-xs font-medium text-gray-400 uppercase tracking-wide">{label}</span></div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-400 mt-1">{sub}</p>
    </div>
  );
}
